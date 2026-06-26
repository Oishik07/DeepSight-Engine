from langchain_core.prompts import ChatPromptTemplate
from graph.state import AgentState
from agents.llm import get_llm
from agents.json_output import parse_json_model
from langchain_community.tools.tavily_search import TavilySearchResults
import os

from pydantic import BaseModel, Field
import asyncio

class SubQueries(BaseModel):
    queries: list[str] = Field(description="Exactly 3 specific, distinct search queries to retrieve comprehensive information for the task.")

async def execute_research(state: AgentState):
    """
    Research Agent: Generates 3 deep-dive sub-queries for the current task,
    runs them concurrently, dedupes findings, and synthesizes them.
    """
    current_index = state.get("current_task_index", 0)
    plan = state["research_plan"]
    
    if current_index >= len(plan.tasks):
        return {}
        
    task = plan.tasks[current_index]
    
    search_api_key = state.get("search_api_key")
    if not search_api_key:
        raise ValueError("Tavily API key is required for search.")
        
    os.environ["TAVILY_API_KEY"] = search_api_key
    search_tool = TavilySearchResults(max_results=3)
    
    llm = get_llm(state["llm_provider"], state["llm_model"], state["llm_api_key"])
    
    # Step 1: Sub-query expansion (V4)
    sub_query_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert search architect. Break down the research task into exactly 3 distinct, specific search queries to retrieve thorough details from Google/Tavily. Make them varied and technical.\n"
                   "Do not call tools or functions. Return plain text only.\n"
                   "CRITICAL JSON FORMATTING: Output exactly ONE valid JSON object, with no markdown code fence and no prose outside JSON. "
                   "Use exactly this shape: {{\"queries\":[\"query 1\",\"query 2\",\"query 3\"]}}."),
        ("human", "Research Goal: {goal}\nTask to expand: {task}\n\nReturn the search queries as JSON.")
    ])
    
    sub_queries = [task]
    try:
        sq_chain = sub_query_prompt | llm
        sq_response = await sq_chain.ainvoke({"goal": state["research_goal"], "task": task})
        sq_res = parse_json_model(sq_response, SubQueries)
        if sq_res and sq_res.queries:
            sub_queries = sq_res.queries
    except Exception as e:
        print(f"[researcher] Sub-query expansion failed: {e}. Falling back to default queries.")
        sub_queries = [task, f"{task} tutorial", f"{task} step by step"]

    # Step 2: Concurrency search execution (V3)
    search_tasks = [search_tool.ainvoke({"query": q}) for q in sub_queries]
    search_results_batches = await asyncio.gather(*search_tasks)
    
    # Deduplicate results by URL
    seen_urls = set()
    deduped_results = []
    for batch in search_results_batches:
        if isinstance(batch, list):
            for res in batch:
                url = res.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    deduped_results.append(res)

    # Step 3: Synthesis
    system_prompt = state.get("system_prompt", "You are an expert Research Assistant.")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are an expert Research Assistant. Analyze the aggregated search results and extract detailed findings to answer the current research task.\n"
                   f"User's Custom System Context: '{system_prompt}'\n"
                   "CRITICAL INSTRUCTION: Do NOT just write a generic summary. If the goal requires step-by-step instructions, processes, exact numbers, or technical details, extract them EXACTLY as found in the text. "
                   "Preserve all actionable information, tutorials, and specific instructions."),
        ("human", "Research Goal: {goal}\nTask: {task}\n\nSearch Results:\n{results}\n\nProvide the detailed findings based on these sources.")
    ])
    
    chain = prompt | llm
    result = await chain.ainvoke({
        "goal": plan.goal,
        "task": task,
        "results": str(deduped_results)[:10000]
    })
    
    sources = list(seen_urls)
    
    finding = {
        "task": task,
        "sources": sources,
        "findings": [result.content],
        "sub_queries": sub_queries # Pass sub_queries back to state so frontend can show them!
    }
    
    return {
        "findings": [finding],
        "current_task_index": current_index + 1
    }
