from langchain_core.prompts import ChatPromptTemplate
from graph.state import AgentState, FinalReport
from agents.llm import get_llm
from agents.json_output import message_to_text, parse_json_model
from agents.text_budget import compact_text, final_stage_char_budget
import json


def _collect_sources(findings, current_report) -> list[str]:
    sources: list[str] = []
    seen = set()
    for source in current_report.get("sources_used", []) if isinstance(current_report, dict) else []:
        if source and source not in seen:
            seen.add(source)
            sources.append(source)
    for finding in findings:
        for source in finding.get("sources", []):
            if source and source not in seen:
                seen.add(source)
                sources.append(source)
    return sources

async def edit_report(state: AgentState):
    """
    Editor Agent: Takes the current draft report, critic feedback, and accumulated findings,
    then rewrites/edits the report to make it meet standards.
    """
    llm = get_llm(state["llm_provider"], state["llm_model"], state["llm_api_key"])
    
    findings = state.get("findings", [])
    current_report = state.get("final_report", {})
    sources = _collect_sources(findings, current_report)
    findings_text = ""
    for f in findings:
        findings_text += f"Task: {f['task']}\n"
        findings_text += f"Findings: {' '.join(f['findings'])}\n\n"
        
    system_prompt = state.get("system_prompt", "You are an expert Research Assistant.")
    critic_feedback = state.get("critic_feedback", "None")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are an expert Report Editor.\n"
                   f"The user provided this overarching custom System Prompt: '{system_prompt}'\n"
                   f"The Quality Assurance Critic rejected the report with the following feedback: '{critic_feedback}'\n"
                   "You must revise the drafted report based on the Critic's feedback.\n"
                   "Ensure the final output is polished, accurate, and properly formatted.\n"
                   "Do not call tools or functions. Return plain text only.\n"
                   "CRITICAL JSON FORMATTING: You MUST output exactly ONE valid JSON root object, with no markdown code fence and no prose outside JSON. "
                   "Use exactly this shape: {{\"title\":\"...\",\"report_markdown\":\"...\",\"sources_used\":[\"https://...\"]}}. "
                   "The report_markdown value must be one JSON string with newlines escaped as \\n.\n"
                   "Optimize for readability, tone, layout, flow, and exact completeness. Maintain all factual data and step-by-step instructions. "
                   "Output a restructured and polished final report adhering to the schema."),
        ("human", "Research Goal: {goal}\n\nCurrent Draft Report:\n{current_report}\n\nFindings:\n{findings}\n\nAvailable source URLs:\n{sources}\n\nProduce the revised report.")
    ])
    
    chain = prompt | llm
    
    char_budget = final_stage_char_budget(state["llm_provider"], state["llm_model"])
    current_report_text = compact_text(json.dumps(current_report, indent=2), char_budget)
    response = await chain.ainvoke({
        "goal": state["research_goal"],
        "current_report": current_report_text,
        "findings": compact_text(findings_text, char_budget),
        "sources": "\n".join(sources[:30])
    })

    try:
        result = parse_json_model(response, FinalReport)
    except Exception as exc:
        raw_report = message_to_text(response).strip()
        print(f"[editor] JSON parsing failed, returning markdown fallback: {exc}")
        result = FinalReport(
            title=current_report.get("title") or state["research_goal"][:120] or "Research Report",
            report_markdown=raw_report or current_report.get("report_markdown", "The model returned an empty revised report."),
            sources_used=sources,
        )
    
    return {
        "final_report": result.model_dump()
    }
