from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class ResearchRequest(BaseModel):
    goal: str
    system_prompt: Optional[str] = "You are an expert Research Assistant."
    llm_provider: Optional[str] = "openrouter" # openrouter, groq, openai, etc
    llm_model: Optional[str] = "qwen/qwen-2.5-72b-instruct"
    llm_api_key: Optional[str] = None
    search_api_key: Optional[str] = None

class ResearchResponse(BaseModel):
    id: str
    goal: str
    status: str
    created_at: datetime

class ResearchStatusResponse(BaseModel):
    id: str
    goal: str
    status: str
    final_report: Optional[Dict[str, Any]] = None
    created_at: datetime
