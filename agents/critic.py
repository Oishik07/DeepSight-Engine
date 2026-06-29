import json
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from agents.llm import get_llm
from agents.json_output import parse_json_model
from agents.text_budget import compact_text, final_stage_char_budget

class CriticDecision(BaseModel):
    decision: str = Field(description="Must be exactly 'PASS', 'REVISE', or 'RESEARCH'. Use 'PASS' if the report is complete. Use 'REVISE' if the report needs text formatting, editing, or restructuring. Use 'RESEARCH' if the report lacks critical factual information that requires new search queries.")
    feedback: str = Field(description="Constructive feedback explaining why it needs revision or research, or praise if it passed.")
    suggested_search_task: str = Field(default="", description="Only if decision is RESEARCH, provide a concrete, single-sentence search task. Otherwise output an empty string.")
    score: float = Field(default=7.0, description="A quality score from 0.0 to 10.0 assessing completeness, accuracy, structure, and adherence to the prompt.")

async def evaluate_report(state: dict):
    """
    Evaluates the final drafted report against the research goal and custom system prompt.
    """
    llm = get_llm(state["llm_provider"], state["llm_model"], state["llm_api_key"])
    
    system_prompt = state.get("system_prompt", "You are an expert Research Assistant.")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are a strict, expert Quality Assurance Critic. Your job is to evaluate the drafted research report.\n"
                   f"The user provided this overarching custom System Prompt that the report MUST adhere to: '{system_prompt}'\n"
                   "Evaluate the report to ensure it meets the User's Research Goal, adheres strictly to the System Prompt, and is high quality.\n"
                   "Provide a quality score (0.0 to 10.0) reflecting the standard of the draft.\n"
                   "Select one of the following decisions:\n"
                   "- PASS: The report is perfect, accurate, comprehensive and complies with context.\n"
                   "- REVISE: The report contains the necessary info, but needs formatting, layout adjustments, better transitions, or copy-editing.\n"
                   "- RESEARCH: The report is missing critical factual information that requires new Google/web searches.\n"
                   "Output feedback in all cases. If decision is RESEARCH, also output a suggested_search_task.\n"
                   "Do not call tools or functions. Return plain text only.\n"
                   "CRITICAL: NEVER output `null` for any field. If suggested_search_task is not needed, output an empty string `\"\"`.\n"
                   "CRITICAL JSON FORMATTING: Output exactly ONE valid JSON object, with no markdown code fence and no prose outside JSON. "
                   "Use exactly this shape: {{\"decision\":\"PASS\",\"feedback\":\"...\",\"suggested_search_task\":\"\",\"score\":8.5}}."),
        ("human", "Research Goal: {goal}\n\nDrafted Report:\n{report}\n\nEvaluate the report as JSON.")
    ])
    
    chain = prompt | llm
    
    # Serialize the report to string for the prompt
    char_budget = final_stage_char_budget(state["llm_provider"], state["llm_model"])
    report_text = compact_text(json.dumps(state.get("final_report", {}), indent=2), char_budget)
    
    response = await chain.ainvoke({
        "goal": state["research_goal"],
        "report": report_text
    })
    result: CriticDecision = parse_json_model(response, CriticDecision)
    result.decision = result.decision.strip().upper()
    if result.decision not in {"PASS", "REVISE", "RESEARCH"}:
        result.decision = "REVISE"
        
    # Standardize score
    raw_score = getattr(result, "score", 7.0)
    try:
        score = float(raw_score)
    except (ValueError, TypeError):
        score = 7.0
    score = max(0.0, min(10.0, score))
    
    revision_count = state.get("revision_count", 0)
    
    # Apply user guidelines:
    # 1. If score >= 8.5, accept immediately (PASS).
    # 2. If revision_count >= 1 (exactly one revision cycle was already executed), accept immediately.
    # 3. If score < 8.5 and revision_count is 0, trigger one revision (REVISE or RESEARCH).
    
    final_decision = result.decision
    if score >= 8.5 or revision_count >= 1:
        final_decision = "PASS"
    else:
        # Override to REVISE to force a revision if the LLM output PASS but score was low
        if final_decision == "PASS":
            final_decision = "REVISE"
            
    plan = state.get("research_plan")
    
    # If RESEARCH, append a new task to the plan so the researcher picks it up
    if final_decision == "RESEARCH" and plan:
        task_str = result.suggested_search_task or f"Research missing info: {result.feedback}"
        plan.tasks.append(task_str)
        
    return {
        "critic_feedback": result.feedback,
        "critic_decision": final_decision,
        "critic_score": score,
        "revision_count": revision_count + 1
    }
