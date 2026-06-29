from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

from database.session import get_db
from database.models import ResearchJob
from schemas.job import ResearchRequest, ResearchResponse, ResearchStatusResponse
from services.research import run_research_background, subscribe, unsubscribe

from sqlalchemy import select
from typing import List, Optional
from core.config import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok", "app": "DeepSight Engine"}

async def get_current_user_email(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = None
) -> str:
    """
    Dependency to authenticate users using Google OAuth ID tokens or a Demo Token.
    Returns the user's verified email.
    """
    auth_token = None
    if authorization and authorization.startswith("Bearer "):
        auth_token = authorization.split(" ")[1]
    elif token:
        auth_token = token
        
    if not auth_token or auth_token == "null" or auth_token == "undefined":
        raise HTTPException(status_code=401, detail="Missing authorization token")
        
    # Check for presentation/demo token (e.g. mock:demo@deepsight.ai)
    if auth_token.startswith("mock:"):
        return auth_token.split("mock:")[1]
        
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        # If client ID is not configured in .env, we allow using the token directly as email
        # to ensure the LinkedIn live demo works out-of-the-box.
        return auth_token
        
    try:
        idinfo = id_token.verify_oauth2_token(auth_token, google_requests.Request(), client_id)
        return idinfo['email']
    except Exception as e:
        # Fallback for local demo run if Client ID is configured but token is local email
        if not auth_token.strip().startswith("AIza") and "@" in auth_token: 
            return auth_token
        raise HTTPException(status_code=401, detail=f"Invalid Google Token: {str(e)}")

@router.get("/config")
async def get_app_config():
    return {
        "google_client_id": settings.GOOGLE_CLIENT_ID
    }

@router.get("/research", response_model=List[ResearchResponse])
async def list_research_jobs(
    db: AsyncSession = Depends(get_db),
    email: str = Depends(get_current_user_email)
):
    # Filter jobs: show user's own jobs, or legacy jobs with no email (public fallback)
    result = await db.execute(
        select(ResearchJob)
        .where((ResearchJob.user_email == email) | (ResearchJob.user_email == None))
        .order_by(ResearchJob.created_at.desc())
    )
    jobs = result.scalars().all()
    return jobs

@router.post("/research", response_model=ResearchResponse)
async def create_research_job(
    request: ResearchRequest, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    email: str = Depends(get_current_user_email)
):
    # Safety Check Guardrails
    sensitive_keywords = [
        'race', 'sex', 'nudity', 'adult content', 'pornography', 'porn', 
        'hate speech', 'discrimination', 'discriminate', 'discriminatory', 
        'explicit content', 'nude', 'sexual'
    ]
    import re
    goal_lower = request.goal.lower()
    has_sensitive = any(re.search(rf"\b{kw}\b", goal_lower) for kw in sensitive_keywords)
    if has_sensitive:
        raise HTTPException(
            status_code=400,
            detail="I cannot answer this query due to safety guidelines."
        )

    # Create job in DB
    new_job = ResearchJob(
        goal=request.goal,
        status="PENDING",
        user_email=email
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
async def get_research_status(
    job_id: str, 
    db: AsyncSession = Depends(get_db),
    email: str = Depends(get_current_user_email)
):
    job = await db.get(ResearchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Check ownership
    if job.user_email and job.user_email != email:
        raise HTTPException(status_code=403, detail="Not authorized to view this research job")
        
    return ResearchStatusResponse(
        id=job.id,
        goal=job.goal,
        status=job.status,
        final_report=job.final_report,
        created_at=job.created_at
    )

@router.get("/research/{job_id}/stream")
async def stream_research_status(
    job_id: str, 
    request: Request,
    email: str = Depends(get_current_user_email)
):
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
