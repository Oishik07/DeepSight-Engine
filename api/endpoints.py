from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

from database.session import get_db
from database.models import ResearchJob
from schemas.job import ResearchRequest, ResearchResponse, ResearchStatusResponse
from services.research import run_research_background, subscribe, unsubscribe

from sqlalchemy import select
from typing import List

router = APIRouter()

@router.get("/research", response_model=List[ResearchResponse])
async def list_research_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ResearchJob).order_by(ResearchJob.created_at.desc()))
    jobs = result.scalars().all()
    return jobs

@router.post("/research", response_model=ResearchResponse)
async def create_research_job(
    request: ResearchRequest, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # Create job in DB
    new_job = ResearchJob(
        goal=request.goal,
        status="PENDING"
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    
    # Start background task
    asyncio.create_task(
        run_research_background(
            job_id=new_job.id,
            goal=request.goal,
            system_prompt=request.system_prompt,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model,
            llm_api_key=request.llm_api_key,
            search_api_key=request.search_api_key
        )
    )
    
    return ResearchResponse(
        id=new_job.id,
        goal=new_job.goal,
        status=new_job.status,
        created_at=new_job.created_at
    )

@router.get("/research/{job_id}", response_model=ResearchStatusResponse)
async def get_research_status(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(ResearchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return ResearchStatusResponse(
        id=job.id,
        goal=job.goal,
        status=job.status,
        final_report=job.final_report,
        created_at=job.created_at
    )

@router.get("/research/{job_id}/stream")
async def stream_research_status(job_id: str, request: Request):
    """
    Server Sent Events endpoint for streaming research progress.
    """
    async def event_generator():
        q = await subscribe(job_id)
        try:
            while True:
                # If client closes connection, request.is_disconnected() will be True eventually
                if await request.is_disconnected():
                    break
                    
                try:
                    # Wait for an event with a timeout to check for disconnects
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield {
                        "event": "message",
                        "data": json.dumps(event)
                    }
                    if event.get("node") in ["end", "error"]:
                        break
                except asyncio.TimeoutError:
                    pass
        finally:
            unsubscribe(job_id, q)

    return EventSourceResponse(event_generator())
