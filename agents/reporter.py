import re
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from graph.state import AgentState
from agents.llm import get_llm
from agents.json_output import parse_json_model, message_to_text
from agents.report_postprocess import normalize_report_markdown
from agents.text_budget import compact_text, final_stage_char_budget

class ReportSectionOutline(BaseModel):
    title: str = Field(description="Title of the section, e.g. '1. Introduction' or '2. Historical Context'")
    purpose: str = Field(description="Detailed purpose outlining exactly what facts and sub-topics this section must cover based on task findings.")
    target_words: int = Field(default=600, description="Target word count for this section (e.g. 500 to 700 words).")

class ReportOutline(BaseModel):
    title: str = Field(description="The overall title of the research report.")
    sections: list[ReportSectionOutline] = Field(description="Exactly 6 to 8 detailed report sections covering all findings sequentially.")

class SectionOutput(BaseModel):
    content: str = Field(description="The full body content of this section in Markdown. Must be highly detailed, comprehensive and target 500-700 words.")
    summary: str = Field(description="A concise 100-150 word summary of this section, to be used as context for transitioning into the next section.")

def _collect_sources(findings) -> list[str]:
    sources: list[str] = []
    seen = set()
    for finding in findings:
        for source in finding.get("sources", []):
            if source and source not in seen:
                seen.add(source)
                sources.append(source)
    return sources

async def write_report(state: AgentState):
    """
    Report Agent:
    1. Generates a structured outline of 6-8 sections.
    2. Sequentially writes each section, using only the previous section's title and summary
       as transition context to keep input token counts low and stable.
    3. Merges sections into the final report.
    """
    llm = get_llm(state["llm_provider"], state["llm_model"], state["llm_api_key"])
    
    findings = state.get("findings", [])
    sources = _collect_sources(findings)
    findings_text = ""
    for f in findings:
        findings_text += f"Task: {f['task']}\n"
        findings_text += f"Sources: {', '.join(f['sources'])}\n"
        findings_text += f"Findings: {' '.join(f['findings'])}\n\n"
        
    system_prompt = state.get("system_prompt", "You are an expert Research Assistant.")
    char_budget = final_stage_char_budget(state["llm_provider"], state["llm_model"])
    compacted_findings = compact_text(findings_text, char_budget)
    
    # ----------------------------------------------------
    # Step 1: Generate Outline (6-8 sections)
    # ----------------------------------------------------
    outline_prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are a Senior Principal Research Analyst.\n"
                   f"User's Custom System Context: '{system_prompt}'\n"
                   "INSTRUCTIONS:\n"
                   "1. Design a report outline containing exactly 6 to 8 sections covering the research goal and task findings.\n"
                   "2. For each section, provide a descriptive title, purpose (sub-topics, facts to include), and a target word count of 500 to 700 words.\n"
                   "Do not call tools or functions. Return plain text only.\n"
                   "CRITICAL JSON FORMATTING: Output exactly ONE valid JSON object, with no markdown code fence and no prose outside JSON. "
                   "Use exactly this shape: {{\"title\":\"Report Title\",\"sections\":[{{\"title\":\"1. Section Title\",\"purpose\":\"Explain...\",\"target_words\":600}}]}}."),
        ("human", "Research Goal: {goal}\n\nResearch Findings Logs:\n{findings}\n\nGenerate the structured report outline as JSON.")
    ])
    
    outline_chain = outline_prompt | llm
    outline_response = await outline_chain.ainvoke({
        "goal": state["research_goal"],
        "findings": compacted_findings
    })
    
    outline: ReportOutline = parse_json_model(outline_response, ReportOutline)
    outline_dict = outline.model_dump()
    
    # ----------------------------------------------------
    # Step 2: Sequentially Generate Sections
    # ----------------------------------------------------
    from services.research import publish_event
    
    sections_dict = {}
    prev_section_title = "N/A (This is the first section)"
    prev_section_summary = "N/A"
    
    for idx, sec in enumerate(outline.sections, 1):
        await publish_event(state["job_id"], {
            "status": f"Writing section {idx}/{len(outline.sections)}: '{sec.title}'...",
            "node": "reporter"
        })
        
        section_prompt = ChatPromptTemplate.from_messages([
            ("system", f"You are a Senior Principal Research Analyst writing a specific section of a deep research report.\n"
                       f"User's Custom System Context: '{system_prompt}'\n"
                       "INSTRUCTIONS:\n"
                       "1. Write the section titled '{section_title}' based on the provided research logs.\n"
                       "2. Focus strictly on the purpose of this section: {section_purpose}\n"
                       "3. Aim for approximately {target_words} words (must be between 500 and 700 words). Make it detailed, professional, and research-grade.\n"
                       "4. Do NOT add any inline numerical citations like [1] or [2] inside the text.\n"
                       "5. Transition smoothly from the previous section. Preceding Section: '{prev_title}' | Preceding Summary: '{prev_summary}'\n"
                       "Do not write the overall report title, references, or outline. Just write the body text for this specific section in Markdown.\n"
                       "Do not call tools or functions. Return plain text only.\n"
                       "CRITICAL JSON FORMATTING: Output exactly ONE valid JSON object, with no markdown code fence and no prose outside JSON. "
                       "Use exactly this shape: {{\"content\":\"Markdown body text here...\",\"summary\":\"100-150 word summary here...\"}}."),
            ("human", "Research Goal: {goal}\n\nSection: {section_title}\n\nResearch Logs:\n{findings}\n\nAvailable Source URLs:\n{sources}\n\nWrite the section as JSON.")
        ])
        
        section_chain = section_prompt | llm
        section_response = await section_chain.ainvoke({
            "goal": state["research_goal"],
            "section_title": sec.title,
            "section_purpose": sec.purpose,
            "target_words": sec.target_words,
            "prev_title": prev_section_title,
            "prev_summary": prev_section_summary,
            "findings": compacted_findings,
            "sources": "\n".join(sources[:25])
        })
        
        sec_out: SectionOutput = parse_json_model(section_response, SectionOutput)
        sections_dict[sec.title] = sec_out.content.strip()
        
        # Update transition context for next section
        prev_section_title = sec.title
        prev_section_summary = sec_out.summary.strip()
        
    # ----------------------------------------------------
    # Step 3: Merge Sections into Final Report
    # ----------------------------------------------------
    merged_markdown = f"# {outline.title}\n\n"
    for sec in outline.sections:
        content = sections_dict.get(sec.title, "")
        
        clean_title = sec.title.strip()
        if re.match(r'^\s*#+\s+' + re.escape(clean_title), content, re.IGNORECASE):
            merged_markdown += f"{content}\n\n"
        elif re.match(r'^\s*#+\s+', content):
            merged_markdown += f"{content}\n\n"
        else:
            merged_markdown += f"## {sec.title}\n\n{content}\n\n"
            
    merged_markdown, extracted_sources = normalize_report_markdown(merged_markdown, sources)
        
    final_report_dict = {
        "title": outline.title,
        "report_markdown": merged_markdown,
        "sources_used": extracted_sources
    }
    
    return {
        "report_outline": outline_dict,
        "report_sections": sections_dict,
        "final_report": final_report_dict
    }
