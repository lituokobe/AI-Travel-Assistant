"""
Human-in-the-Loop (HITL) Toolset.

Provides tools required for runtime human interaction, including travel data
supplementation, etc.
Tools pause execution via langgraph.types.interrupt(), waiting for human
input before resuming.

Usage:
    from agent.tools.hitl_tools import request_travel_info
"""

from __future__ import annotations
import json
from langchain_core.tools import tool
from langgraph.types import interrupt

@tool
def request_travel_info(missing_fields: str, collected_data: str) -> str:
    """Request human input to supplement missing fields when travel data is incomplete.

    Calling this tool pauses execution, displays the missing fields and
    collected data in the terminal, and waits for human input to supplement
    the information before resuming.

    Args:
        missing_fields: List of missing fields and their descriptions
                        (e.g., 'destination (travel destination name, required)')
        collected_data: Already collected data (structured description,
                        e.g., 'destination=Paris')

    Returns:
        Data supplemented by the human (JSON string)
    """
    response = interrupt({
        "type": "travel_info_request",
        "missing_fields": missing_fields,
        "collected_data": collected_data,
    })  # interrupt the workflow and send the payload the frontend

    return json.dumps(response, ensure_ascii=False)
