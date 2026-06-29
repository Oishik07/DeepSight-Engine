from langgraph.graph import StateGraph, START, END
from graph.state import AgentState
from agents.planner import plan_research
from agents.researcher import execute_research
from agents.reporter import write_report

from agents.critic import evaluate_report

def should_continue(state: AgentState):
    """
    Edge router to decide whether to continue researching or go to report.
    """
    plan = state.get("research_plan")
    current_index = state.get("current_task_index", 0)
    
    if plan and current_index < len(plan.tasks):
        return "researcher"
    else:
        return "reporter"

def should_reflect(state: AgentState):
    """
    Edge router from Critic.
    """
    decision = state.get("critic_decision")
    revision_count = state.get("revision_count", 0)
    
    if revision_count >= 3:
        return "end"
        
    if decision == "RESEARCH":
        return "researcher"
    elif decision == "REVISE":
        return "editor"
    else:
        return "end"

def compile_workflow():
    workflow = StateGraph(AgentState)
    from agents.editor import edit_report
    
    # Add nodes
    workflow.add_node("planner", plan_research)
    workflow.add_node("researcher", execute_research)
    workflow.add_node("reporter", write_report)
    workflow.add_node("critic", evaluate_report)
    workflow.add_node("editor", edit_report)
    
    # Add edges
    workflow.add_edge(START, "planner")
    
    # Conditional edge from planner to either researcher or reporter (if no tasks)
    workflow.add_conditional_edges(
        "planner",
        should_continue,
        {
            "researcher": "researcher",
            "reporter": "reporter"
        }
    )
    
    # Conditional edge from researcher loop
    workflow.add_conditional_edges(
        "researcher",
        should_continue,
        {
            "researcher": "researcher",
            "reporter": "reporter"
        }
    )
    
    workflow.add_edge("reporter", "critic")
    workflow.add_edge("editor", "critic")
    
    workflow.add_conditional_edges(
        "critic",
        should_reflect,
        {
            "researcher": "researcher",
            "editor": "editor",
            "end": END
        }
    )
    
    
    return workflow.compile()
