"""Booking sub-agent middleware limits parallel HITL book calls."""

from langchain.agents.middleware import ToolCallLimitMiddleware

from agent.middleware_config import create_booking_sub_agent_middleware


def test_flights_agent_middleware_limits_one_book_per_run():
    stack = create_booking_sub_agent_middleware(book_tool="flights_book")
    book_limits = [
        m
        for m in stack
        if isinstance(m, ToolCallLimitMiddleware)
        and getattr(m, "tool_name", None) == "flights_book"
    ]
    assert len(book_limits) == 1
    assert book_limits[0].run_limit == 1
