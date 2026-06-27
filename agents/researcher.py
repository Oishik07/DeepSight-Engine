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
    Research Agent: Executes all pending tasks in the research plan concurrently,
    managing sub-query expansion, web searches, and synthesis for each task,
    while streaming real-time task progress.
    """
    current_index = state.get("current_task_index", 0)
    plan = state.get("research_plan")
    
    if not plan or current_index >= len(plan.tasks):
        return {}
        
    tasks_to_run = plan.tasks[current_index:]
    
    search_api_key = state.get("search_api_key")
    if not search_api_key:
        raise ValueError("Tavily API key is required for search.")
        
    os.environ["TAVILY_API_KEY"] = search_api_key
    search_tool = TavilySearchResults(max_results=5)
    
    llm = get_llm(state["llm_provider"], state["llm_model"], state["llm_api_key"])
    system_prompt = state.get("system_prompt", "You are an expert Research Assistant.")
    
    # Dynamically import publish_event to prevent circular imports
    from services.research import publish_event
    
    completed_findings = []
    completed_lock = asyncio.Lock()
    
    async def run_single_task(task: str, task_idx: int):
        # Step 1: Sub-query expansion
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
            print(f"[researcher] Sub-query expansion failed for task '{task}': {e}. Falling back.")
            sub_queries = [task, f"{task} tutorial", f"{task} details"]
            
        # Step 2: Concurrency search execution (with retry protection for Tavily)
        async def search_with_retry(query: str):
            max_retries = 3
            base_delay = 4.0
            for attempt in range(max_retries):
                try:
                    return await search_tool.ainvoke({"query": query})
                except Exception as e:
                    err_str = str(e)
                    is_rate_limit = "429" in err_str or "rate limit" in err_str.lower()
                    if is_rate_limit and attempt < max_retries - 1:
                        sleep_time = (base_delay * (2 ** attempt)) + (random.random() * 2)
                        print(f"[Search Retry] Rate limit hit. Waiting {sleep_time:.2f}s before retry (attempt {attempt + 1}/{max_retries})...")
                        await asyncio.sleep(sleep_time)
                    else:
                        raise e
                        
        search_tasks = [search_with_retry(q) for q in sub_queries]
        search_results_batches = await asyncio.gather(*search_tasks)
        
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
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"You are an expert Research Assistant. Perform a deep, exhaustive analysis of the aggregated search results and compile a massive, highly detailed raw research log to answer this task.\n"
                       f"User's Custom System Context: '{system_prompt}'\n"
                       "CRITICAL INSTRUCTION: Do NOT summarize. Provide a deep-dive breakdown containing every piece of actionable information, technical specification, stat, quote, date, and method found. "
                       "Your findings for this task must be extremely long (at least 800-1200 words), highly granular, and structured with clear subsections. Cite sources directly where appropriate."),
            ("human", "Research Goal: {goal}\nTask: {task}\n\nSearch Results:\n{results}\n\nProvide the exhaustive, detailed findings based on these sources.")
        ])
        
        chain = prompt | llm
        result = await chain.ainvoke({
            "goal": plan.goal,
            "task": task,
            "results": str(deduped_results)[:10000]
        })
        
        finding = {
            "task": task,
            "sources": list(seen_urls),
            "findings": [result.content],
            "sub_queries": sub_queries
        }
        
        async with completed_lock:
            completed_findings.append(finding)
            # Send live event to the frontend client
            await publish_event(state["job_id"], {
                "status": f"Completed research on task {len(completed_findings)}/{len(tasks_to_run)}: '{task[:60]}...'",
                "node": "researcher",
                "findings": state.get("findings", []) + completed_findings
            })
            
        return finding

    # We use a semaphore to avoid rate limit issues (e.g. max 2 parallel tasks to be gentle on free tiers)
    sem = asyncio.Semaphore(2)
    async def run_with_sem(t, idx):
        # Stagger task startup by 4.5 seconds per task index to spread load and avoid TPM spikes
        delay = (idx - current_index) * 4.5
        await asyncio.sleep(delay)
        async with sem:
            return await run_single_task(t, idx)
            
    tasks = [run_with_sem(t, current_index + i) for i, t in enumerate(tasks_to_run)]
    new_findings = await asyncio.gather(*tasks)
    
    # Filter out empty/failed findings
    new_findings = [f for f in new_findings if f]
    
    return {
        "findings": new_findings,
        "current_task_index": len(plan.tasks)
    }
