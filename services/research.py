import asyncio
import traceback
from database.models import ResearchJob
from database.session import AsyncSessionLocal
from graph.workflow import compile_workflow
from core.config import settings

# -------------------------------------------------------------------
# In-memory pub/sub with replay buffer (solves the race condition
# where the SSE client connects after events have already fired)
# -------------------------------------------------------------------
# Structure:  job_id -> {"queues": [...], "history": [...]}
_state: dict[str, dict] = {}


def _ensure_job(job_id: str):
    if job_id not in _state:
        _state[job_id] = {"queues": [], "history": []}


async def publish_event(job_id: str, event_data: dict):
    _ensure_job(job_id)
    _state[job_id]["history"].append(event_data)
    for q in _state[job_id]["queues"]:
        await q.put(event_data)


async def subscribe(job_id: str) -> asyncio.Queue:
    _ensure_job(job_id)
    q: asyncio.Queue = asyncio.Queue()
    # Replay any events that already happened before the client connected
    for past_event in _state[job_id]["history"]:
        await q.put(past_event)
    _state[job_id]["queues"].append(q)
    return q


def unsubscribe(job_id: str, q: asyncio.Queue):
    if job_id in _state and q in _state[job_id]["queues"]:
        _state[job_id]["queues"].remove(q)


import os
import json
import re
from agents.report_postprocess import normalize_report_markdown

PROVIDER_API_KEY_ENV_VARS = {
    "groq": ("GROQ_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "claude": ("ANTHROPIC_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def _env_value(name: str) -> str:
    value = getattr(settings, name, None) or os.environ.get(name, "")
    return value.strip()


def _resolve_llm_api_key(provider: str, request_api_key: str | None) -> str:
    request_api_key = (request_api_key or "").strip()
    if request_api_key:
        return request_api_key

    env_names = PROVIDER_API_KEY_ENV_VARS.get(provider, ("OPENAI_API_KEY",))
    for env_name in env_names:
        value = _env_value(env_name)
        if value:
            return value

    expected = " or ".join(env_names)
    raise ValueError(
        f"LLM API key is missing. Set {expected} in your environment/.env file "
        "or provide a key in the Configuration panel."
    )


def _resolve_search_api_key(request_api_key: str | None) -> str:
    request_api_key = (request_api_key or "").strip()
    if request_api_key:
        return request_api_key

    value = _env_value("TAVILY_API_KEY")
    if value:
        return value

    raise ValueError(
        "Search API key is missing. Set TAVILY_API_KEY in your environment/.env file "
        "or provide a key in the Configuration panel."
    )

async def run_research_background(
    job_id: str,
    goal: str,
    system_prompt: str,
    llm_provider: str,
    llm_model: str,
    llm_api_key: str,
    search_api_key: str,
):
    try:
        await publish_event(job_id, {"status": "Starting research process...", "node": "start"})

        # Mark job IN_PROGRESS
        async with AsyncSessionLocal() as session:
            job = await session.get(ResearchJob, job_id)
            if job:
                job.status = "IN_PROGRESS"
                await session.commit()

        app = compile_workflow()

        provider = (llm_provider or "").strip().lower() or "groq"
        model = (llm_model or "").strip() or "llama-3.1-8b-instant"
        resolved_llm_api_key = _resolve_llm_api_key(provider, llm_api_key)
        resolved_search_api_key = _resolve_search_api_key(search_api_key)

        initial_state = {
            "job_id": job_id,
            "research_goal": goal,
            "system_prompt": system_prompt,
            "llm_provider": provider,
            "llm_model": model,
            "llm_api_key": resolved_llm_api_key,
            "search_api_key": resolved_search_api_key,
            "current_task_index": 0,
            "findings": [],
            "revision_count": 0,
            "report_outline": None,
            "report_sections": None,
        }

        latest_report = None
        accumulated_findings = []
        revision_count = 0
        critic_decision = None
        critic_feedback = None

        async for event in app.astream(initial_state):
            for node_name, state_updates in event.items():
                if "final_report" in state_updates and state_updates["final_report"]:
                    latest_report = state_updates["final_report"]
                if "findings" in state_updates and state_updates["findings"]:
                    accumulated_findings.extend(state_updates["findings"])
                if "revision_count" in state_updates:
                    revision_count = state_updates["revision_count"]
                if "critic_decision" in state_updates:
                    critic_decision = state_updates["critic_decision"]
                if "critic_feedback" in state_updates:
                    critic_feedback = state_updates["critic_feedback"]

                if node_name == "planner":
                    plan = state_updates.get("research_plan")
                    tasks_preview = ""
                    if plan and hasattr(plan, "tasks"):
                        tasks_preview = " → ".join(plan.tasks[:3])
                    msg = f"Planning research... Tasks: {tasks_preview}" if tasks_preview else "Planning research..."
                elif node_name == "researcher":
                    idx = len(accumulated_findings)
                    msg = f"Researching task {idx} completed."
                elif node_name == "reporter":
                    msg = "Generating initial report draft..."
                elif node_name == "critic":
                    if critic_decision == "REVISE":
                        msg = f"Critic requested REVISION: {critic_feedback}"
                    elif critic_decision == "RESEARCH":
                        msg = f"Critic requested MORE RESEARCH: {critic_feedback}"
                    else:
                        msg = "Critic Approved Draft! 🎉"
                elif node_name == "editor":
                    msg = "Editor is refining the draft..."
                else:
                    msg = f"Running {node_name}..."

                await publish_event(job_id, {
                    "status": msg,
                    "node": node_name,
                    "findings": accumulated_findings,
                    "critic_decision": critic_decision,
                    "critic_feedback": critic_feedback,
                    "revision_count": revision_count
                })

        report = latest_report
        if report and report.get("report_markdown"):
            cleaned_markdown, cleaned_sources = normalize_report_markdown(
                report.get("report_markdown", ""),
                report.get("sources_used", []),
            )
            report = dict(report)
            report["report_markdown"] = cleaned_markdown
            report["sources_used"] = cleaned_sources
        
        # Save report to File System
        file_path = f"results/{job_id}.md"
        if report:
            os.makedirs("results", exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                title = report.get('title', 'Research Report')
                report_markdown = report.get('report_markdown')
                if report_markdown:
                    saved_markdown = report_markdown.strip()
                    if not re.match(r"^\s*#\s+", saved_markdown):
                        saved_markdown = f"# {title}\n\n{saved_markdown}"
                    f.write(f"{saved_markdown}\n\n")
                else:
                    f.write(f"# {title}\n\n")
                    if report.get('introduction'):
                        f.write(f"{report.get('introduction')}\n\n")
                    for section in report.get('sections', []):
                        if isinstance(section, dict):
                            f.write(f"## {section.get('title')}\n\n{section.get('content')}\n\n")
                        else:
                            # Pydantic model fallback
                            f.write(f"## {section.title}\n\n{section.content}\n\n")
                    if report.get('conclusion'):
                        f.write(f"## Conclusion\n\n{report.get('conclusion')}\n\n")

                if not report_markdown and report.get('sources_used'):
                    f.write(f"### Sources\n\n")
                    for s in report.get('sources_used'):
                        f.write(f"- {s}\n")
                        
        await publish_event(job_id, {
            "status": "Research complete! ✅",
            "node": "end",
            "report": report,
            "file_path": file_path,
            "findings": accumulated_findings
        })

        # Persist to DB
        async with AsyncSessionLocal() as session:
            job = await session.get(ResearchJob, job_id)
            if job:
                job.status = "COMPLETED"
                job.final_report = report
                await session.commit()

    except Exception as e:
        err_msg = f"Error: {str(e)}"
        print(f"[research background] {err_msg}\n{traceback.format_exc()}")
        await publish_event(job_id, {"status": err_msg, "node": "error"})
        async with AsyncSessionLocal() as session:
            job = await session.get(ResearchJob, job_id)
            if job:
                job.status = "FAILED"
                await session.commit()
