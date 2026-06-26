from langchain_core.prompts import ChatPromptTemplate
from graph.state import AgentState, FinalReport
from agents.llm import get_llm
from agents.json_output import message_to_text, parse_json_model
from agents.text_budget import compact_text, final_stage_char_budget


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
    Report Agent: Combines all findings and generates a final structured report.
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
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are an expert Report Writer. Synthesize the research findings into a final report.\n"
                   f"User's Custom System Context: '{system_prompt}'\n"
                   "CRITICAL INSTRUCTION: You must be concise, but write a complete, beautifully formatted Markdown report. Do not abruptly stop mid-sentence. "
                   "Only include the absolute core facts needed to answer the user's goal. Use brief bullet points.\n"
                   "Do not call tools or functions. Return plain text only.\n"
                   "CRITICAL JSON FORMATTING: You MUST output exactly ONE valid JSON object, with no markdown code fence and no prose outside JSON. "
                   "Use exactly this shape: {{\"title\":\"...\",\"report_markdown\":\"...\",\"sources_used\":[\"https://...\"]}}. "
                   "The report_markdown value must be one JSON string with newlines escaped as \\n."),
        ("human", "Research Goal: {goal}\n\nFindings:\n{findings}\n\nAvailable source URLs:\n{sources}\n\nGenerate the highly concise final report.")
    ])
    
    chain = prompt | llm
    
    char_budget = final_stage_char_budget(state["llm_provider"], state["llm_model"])
    response = await chain.ainvoke({
        "goal": state["research_goal"],
        "findings": compact_text(findings_text, char_budget),
        "sources": "\n".join(sources[:30])
    })

    try:
        result = parse_json_model(response, FinalReport)
    except Exception as exc:
        raw_report = message_to_text(response).strip()
        print(f"[reporter] JSON parsing failed, returning markdown fallback: {exc}")
        result = FinalReport(
            title=state["research_goal"][:120] or "Research Report",
            report_markdown=raw_report or "The model returned an empty report.",
            sources_used=sources,
        )
    
    # Return as dict for JSON serializability
    return {
        "final_report": result.model_dump()
    }
