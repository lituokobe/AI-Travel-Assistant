"""Tests for LangChain → API message conversion."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from api_view.services.message_converter import langchain_to_api_message, state_messages_to_api


def test_human_message_conversion():
    msg = langchain_to_api_message(HumanMessage(content="Hello"))
    assert msg.role == "user"
    assert msg.content == "Hello"


def test_ai_message_with_tool_calls():
    msg = langchain_to_api_message(
        AIMessage(
            content="Searching...",
            tool_calls=[{"id": "tc1", "name": "web_search", "args": {"q": "flights"}}],
        )
    )
    assert msg.role == "assistant"
    assert msg.tool_calls is not None
    assert msg.tool_calls[0]["name"] == "web_search"


def test_tool_message_conversion():
    msg = langchain_to_api_message(
        ToolMessage(content="result", tool_call_id="tc1", name="flights_search")
    )
    assert msg.role == "tool"
    assert msg.tool_name == "flights_search"
    assert msg.tool_status == "done"


def test_state_messages_to_api():
    messages = state_messages_to_api(
        [HumanMessage(content="Hi"), AIMessage(content="Hello!")]
    )
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
