"""Node implementations for the LangGraph workflow.

Each function returns a partial state update. Do not mutate the input state in place.
"""

from __future__ import annotations

import re

from .state import AgentState, ApprovalDecision, Route, make_event


def intake_node(state: AgentState) -> dict:
    """Normalize raw query into state fields."""
    raw_query = state.get("query", "")
    normalized = re.sub(r"\s+", " ", raw_query.strip())
    return {
        "query": normalized,
        "messages": [f"intake:{normalized[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using keyword heuristics."""
    query = state.get("query", "").lower()
    tokens = re.findall(r"\b[\w']+\b", query)
    route = Route.SIMPLE
    risk_level = "low"

    risk_keywords = {
        "refund",
        "delete",
        "remove",
        "revoke",
        "cancel",
        "terminate",
        "close",
        "send",
    }
    tool_keywords = {
        "status",
        "order",
        "lookup",
        "check",
        "track",
        "find",
        "search",
        "account",
        "shipping",
        "billing",
    }
    error_keywords = {
        "timeout",
        "fail",
        "failed",
        "failure",
        "error",
        "crash",
        "unavailable",
        "exception",
    }
    vague_keywords = {"it", "this", "that", "something", "anything"}

    if any(token in risk_keywords for token in tokens):
        route = Route.RISKY
        risk_level = "high"
    elif any(token in tool_keywords for token in tokens):
        route = Route.TOOL
    elif len(tokens) < 5 and any(token in vague_keywords for token in tokens):
        route = Route.MISSING_INFO
    elif any(token in error_keywords for token in tokens):
        route = Route.ERROR

    return {
        "route": route.value,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route.value}")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating."""
    query = state.get("query", "").strip()
    question = (
        f"I need more details to help with '{query}'. "
        "Please provide an order number, account info, or the exact issue."
    )
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "missing information requested")],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool and simulate transient failures for error scenarios."""
    attempt = int(state.get("attempt", 0))
    route = state.get("route")
    scenario_id = state.get("scenario_id", "unknown")
    query = state.get("query", "").strip()

    if route == Route.ERROR.value and attempt < int(state.get("max_attempts", 3)):
        result = f"ERROR: transient failure attempt={attempt + 1} scenario={scenario_id}"
    else:
        result = f"SUCCESS: processed '{query}' for scenario={scenario_id}"

    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", f"tool executed attempt={attempt + 1}")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for approval and capture the proposed action."""
    query = state.get("query", "").strip()
    proposed_action = f"Authorize risky operation for query: '{query}'."
    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "pending_approval", "approval required")],
    }


def approval_node(state: AgentState) -> dict:
    """Human approval step with optional LangGraph interrupt()."""
    import os

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        value = interrupt(
            {
                "proposed_action": state.get("proposed_action"),
                "risk_level": state.get("risk_level"),
            }
        )
        if isinstance(value, dict):
            decision = ApprovalDecision(**value)
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        decision = ApprovalDecision(approved=True, comment="mock approval for lab")

    return {
        "approval": decision.model_dump(),
        "events": [make_event("approval", "completed", f"approved={decision.approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt and capture the retry event."""
    attempt = int(state.get("attempt", 0)) + 1
    return {
        "attempt": attempt,
        "errors": [f"transient failure attempt={attempt}"],
        "events": [make_event("retry", "completed", "retry attempt recorded", attempt=attempt)],
    }


def answer_node(state: AgentState) -> dict:
    """Produce a final response grounded in tool results, pending questions, or approvals."""
    route = state.get("route")
    if state.get("pending_question"):
        answer = state["pending_question"]
    elif state.get("tool_results"):
        answer = f"Final answer: {state['tool_results'][-1]}"
    elif route == Route.RISKY.value and state.get("approval"):
        approval = state["approval"]
        approved = approval.get("approved", False)
        answer = (
            "Risky operation approved and ready to execute." if approved else "Risky operation was rejected."
        )
    else:
        answer = "I’m ready to help when more details are provided."

    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "answer generated")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results and decide if retry is needed."""
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    if "ERROR" in latest:
        return {
            "evaluation_result": "needs_retry",
            "events": [make_event("evaluate", "completed", "tool result indicates failure, retry needed")],
        }

    return {
        "evaluation_result": "success",
        "events": [make_event("evaluate", "completed", "tool result satisfactory")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failure after retry exhaustion."""
    answer = (
        "Request could not be completed after maximum retry attempts. Logged for manual review."
    )
    return {
        "final_answer": answer,
        "events": [
            make_event(
                "dead_letter",
                "completed",
                f"max retries exceeded, attempt={state.get('attempt', 0)}",
                route=state.get("route"),
            )
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Finalize the run and emit a final audit event."""
    return {"events": [make_event("finalize", "completed", "workflow finished")]}

