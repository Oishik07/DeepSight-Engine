from langchain_core.prompts import ChatPromptTemplate
from graph.state import AgentState, ResearchPlan
from agents.llm import get_llm
from agents.json_output import parse_json_model

async def plan_research(state: AgentState):
    """
    Planner Agent: Analyzes the user's research goal, breaks it into research tasks,
    and produces a structured research plan.
    """
    llm = get_llm(state["llm_provider"], state["llm_model"], state["llm_api_key"])
    
    system_prompt = state.get("system_prompt", "You are an expert Research Assistant.")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are an Elite Research Mastermind. Your objective is to architect a flawless, extremely rigorous research plan for the user's goal.\n"
                   f"User's Custom System Context: '{system_prompt}'\n\n"
                   "INSTRUCTIONS:\n"
                   "1. Break the goal down into 4-5 highly specific, mutually exclusive research tasks.\n"
                   "2. Ensure the tasks collectively cover all possible angles: historical context, recent breakthroughs, step-by-step technical guides, competitive landscape, and factual data.\n"
                   "3. Your tasks will be executed by parallel web-search agents, so make them concrete and search-engine friendly.\n"
                   "Ensure your tasks align perfectly with the user's custom context.\n"
                   "Do not call tools or functions. Return plain text only.\n"
                   "CRITICAL JSON FORMATTING: Output exactly ONE valid JSON object, with no markdown code fence and no prose outside JSON. "
                   "Use exactly this shape: {{\"goal\":\"...\",\"tasks\":[\"task 1\",\"task 2\",\"task 3\",\"task 4\"]}}."),
        ("human", "Research Goal: {goal}\n\nProvide the elite structured research plan as JSON.")
    ])
    
    chain = prompt | llm
    
    response = await chain.ainvoke({"goal": state["research_goal"]})
    result = parse_json_model(response, ResearchPlan)
    
    return {
        "research_plan": result,
        "current_task_index": 0
    }
