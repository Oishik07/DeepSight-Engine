from typing import Annotated, TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field
import operator

class ResearchTask(BaseModel):
    task: str = Field(description="The specific research task to be executed")

class ResearchPlan(BaseModel):
    goal: str = Field(description="The main research goal")
    tasks: List[str] = Field(description="List of tasks to execute")

class ResearchFinding(BaseModel):
    task: str
    sources: List[str]
    findings: List[str]

class FinalReport(BaseModel):
    title: str = Field(description="The overall title of the research report.")
    report_markdown: str = Field(description="The entire body of the report formatted beautifully in Markdown. Include headers, bullet points, introductions, and conclusions inside this single string.")
    sources_used: List[str] = Field(description="List of URLs used as evidence.")

class AgentState(TypedDict):
    job_id: str
    research_goal: str
    system_prompt: str
    llm_provider: str
    llm_model: str
    llm_api_key: str
    search_api_key: str
    
    # State fields
    research_plan: Optional[ResearchPlan]
    current_task_index: int
    findings: Annotated[List[Dict[str, Any]], operator.add]
    final_report: Optional[Dict[str, Any]]
    
    # Critic and Reflection fields
    critic_feedback: Optional[str]
    critic_decision: Optional[str]
    revision_count: int
