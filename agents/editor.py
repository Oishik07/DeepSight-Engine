import re
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from graph.state import AgentState
from agents.llm import get_llm
from agents.json_output import parse_json_model, message_to_text
from agents.report_postprocess import normalize_report_markdown
from agents.text_budget import compact_text, final_stage_char_budget

class RevisionPlan(BaseModel):
    sections_to_revise: list[str] = Field(description="Exact titles of the sections that need to be revised based on the critic feedback.")
    reasoning: str = Field(description="Brief explanation of why these sections need to be revised.")

class SectionOutput(BaseModel):
    content: str = Field(description="The revised markdown content for this section. Must be highly detailed, targeting 500-700 words.")
    summary: str = Field(description="A revised concise 100-150 word summary of this section, for transition context.")

def _collect_sources(findings) -> list[str]:
    sources: list[str] = []
    seen = set()
    for finding in findings:
        for source in finding.get("sources", []):
            if source and source not in seen:
                seen.add(source)
                sources.append(source)
    return sources

async def edit_report(state: AgentState):
    """
    Editor Agent:
    1. Analyzes the Critic's feedback and identifies which sections of the report need revision.
    2. Sequentially rewrites only those affected sections, keeping unaffected sections intact.
    3. Re-merges the sections into a final report.
    """
    llm = get_llm(state["llm_provider"], state["llm_model"], state["llm_api_key"])
    
    findings = state.get("findings", [])
    sources = _collect_sources(findings)
    findings_text = ""
    for f in findings:
        findings_text += f"Task: {f['task']}\n"
        findings_text += f"Findings: {' '.join(f['findings'])}\n\n"
        
    system_prompt = state.get("system_prompt", "You are an expert Research Assistant.")
    critic_feedback = state.get("critic_feedback", "None")
    
    report_sections = dict(state.get("report_sections") or {})
    report_outline = state.get("report_outline") or {}
    
    # Fallback to reporter if no sections or outline exist
    if not report_sections or not report_outline:
        from agents.reporter import write_report
        return await write_report(state)
        
    actual_section_titles = list(report_sections.keys())
    
    # ----------------------------------------------------
    # Step 1: Generate Revision Plan (Which sections to edit)
    # ----------------------------------------------------
    revision_prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are a Senior Principal Research Editor.\n"
                   f"The Quality Assurance Critic rejected the report with this feedback: '{critic_feedback}'\n"
                   "Analyze the feedback and identify which specific sections of the report must be revised to address the concerns.\n"
                   "Do not call tools or functions. Return plain text only.\n"
                   "CRITICAL JSON FORMATTING: Output exactly ONE valid JSON object, with no markdown code fence and no prose outside JSON. "
                   "Use exactly this shape: {{\"sections_to_revise\":[\"Section Title 1\"],\"reasoning\":\"...\"}}."),
        ("human", "Available Report Section Titles:\n{titles}\n\nDetermine which sections must be revised as JSON.")
    ])
    
    revision_chain = revision_prompt | llm
    revision_response = await revision_chain.ainvoke({
        "titles": "\n".join(actual_section_titles)
    })
    
    rev_plan: RevisionPlan = parse_json_model(revision_response, RevisionPlan)
    
    # Match candidate section titles with actual keys
    matched_sections = []
    for candidate in rev_plan.sections_to_revise:
        candidate_clean = candidate.strip().lower()
        for actual in actual_section_titles:
            actual_clean = actual.strip().lower()
            if candidate_clean in actual_clean or actual_clean in candidate_clean:
                if actual not in matched_sections:
                    matched_sections.append(actual)
                    break
                    
    # Fallback: if no matches or no sections specified, edit all sections to be safe
    if not matched_sections:
        matched_sections = actual_section_titles
        
    # ----------------------------------------------------
    # Step 2: Sequentially Revise Matched Sections
    # ----------------------------------------------------
    from services.research import publish_event
    char_budget = final_stage_char_budget(state["llm_provider"], state["llm_model"])
    compacted_findings = compact_text(findings_text, char_budget)
    
    for idx, section_title in enumerate(matched_sections, 1):
        await publish_event(state["job_id"], {
            "status": f"Revising section {idx}/{len(matched_sections)}: '{section_title}'...",
            "node": "editor"
        })
        
        # Get the purpose of this section from outline if available
        section_purpose = ""
        target_words = 600
        for outline_sec in report_outline.get("sections", []):
            if outline_sec.get("title") == section_title:
                section_purpose = outline_sec.get("purpose", "")
                target_words = outline_sec.get("target_words", 600)
                break
                
        current_draft = report_sections.get(section_title, "")
        
        edit_section_prompt = ChatPromptTemplate.from_messages([
            ("system", f"You are a Senior Principal Research Editor revising a specific section of a deep research report.\n"
                       f"User's Custom System Context: '{system_prompt}'\n"
                       f"The Quality Assurance Critic provided this feedback: '{critic_feedback}'\n"
                       "INSTRUCTIONS:\n"
                       "1. Revise the section titled '{section_title}' to fully address the Critic's concerns.\n"
                       "2. Focus strictly on the purpose of this section: {section_purpose}\n"
                       "3. Keep the word count between 500 and 700 words. Make it detailed, professional, and academic-grade.\n"
                       "4. Do NOT add any inline numerical citations like [1] or [2] inside the text.\n"
                       "5. Here is the current draft of this section:\n"
                       "-----\n"
                       "{current_draft}\n"
                       "-----\n"
                       "Rewrite the section in Markdown, incorporating all necessary improvements and edits.\n"
                       "Do not write the overall report title, references, or outline. Just write the body text for this specific section in Markdown.\n"
                       "Do not call tools or functions. Return plain text only.\n"
                       "CRITICAL JSON FORMATTING: Output exactly ONE valid JSON object, with no markdown code fence and no prose outside JSON. "
                       "Use exactly this shape: {{\"content\":\"Markdown body text here...\",\"summary\":\"100-150 word summary here...\"}}."),
            ("human", "Research Goal: {goal}\n\nSection to revise: {section_title}\n\nResearch Logs:\n{findings}\n\nAvailable Source URLs:\n{sources}\n\nRevise the section as JSON.")
        ])
        
        edit_chain = edit_section_prompt | llm
        edit_response = await edit_chain.ainvoke({
            "goal": state["research_goal"],
            "section_title": section_title,
            "section_purpose": section_purpose,
            "target_words": target_words,
            "current_draft": current_draft,
            "findings": compacted_findings,
            "sources": "\n".join(sources[:25])
        })
        
        sec_out: SectionOutput = parse_json_model(edit_response, SectionOutput)
        report_sections[section_title] = sec_out.content.strip()
        
    # ----------------------------------------------------
    # Step 3: Merge Sections into final_report dict
    # ----------------------------------------------------
    merged_markdown = f"# {report_outline.get('title', state['research_goal'])}\n\n"
    for outline_sec in report_outline.get("sections", []):
        sec_title = outline_sec.get("title")
        content = report_sections.get(sec_title, "")
        
        clean_title = sec_title.strip()
        if re.match(r'^\s*#+\s+' + re.escape(clean_title), content, re.IGNORECASE):
            merged_markdown += f"{content}\n\n"
        elif re.match(r'^\s*#+\s+', content):
            merged_markdown += f"{content}\n\n"
        else:
            merged_markdown += f"## {sec_title}\n\n{content}\n\n"
            
    merged_markdown, extracted_sources = normalize_report_markdown(merged_markdown, sources)
        
    final_report_dict = {
        "title": report_outline.get("title", state["research_goal"]),
        "report_markdown": merged_markdown,
        "sources_used": extracted_sources
    }
    
    return {
        "report_sections": report_sections,
        "final_report": final_report_dict
    }
