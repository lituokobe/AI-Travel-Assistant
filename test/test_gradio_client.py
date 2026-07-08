"""Tests for Gradio API client."""

from unittest.mock import MagicMock, patch

import httpx

from gradio_ui.client import TravelAPIClient


def test_agent_status_calls_correct_endpoint():
    client = TravelAPIClient(base_url="http://test")
    mock_response = MagicMock()
    mock_response.json.return_value = {"ready": True}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = client.agent_status()

    assert result["ready"] is True
    mock_client.get.assert_called_once_with("http://test/api/v1/agent/status")


def test_stream_chat_parses_sse_lines():
    client = TravelAPIClient(base_url="http://test")

    def fake_iter_lines():
        yield 'data: {"type":"token","content":"Hi"}'
        yield "ignored line"
        yield 'data: {"type":"done","thread_id":"t1","content":"Hi"}'

    mock_response = MagicMock()
    mock_response.iter_lines = fake_iter_lines
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.stream.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        events = list(client.stream_chat("hello", None))

    assert len(events) == 2
    assert events[0]["type"] == "token"
    assert events[1]["type"] == "done"
