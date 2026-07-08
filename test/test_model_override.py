"""Tests for model override behaviour."""

from unittest.mock import patch

import agent.config as agent_config
from api_view import model_override
from api_view.model_override import apply_model_overrides


def test_apply_model_overrides_enables_main_thinking():
    with patch.object(model_override, "ENABLE_MODEL_THINKING", True):
        info = apply_model_overrides()

    assert info["main_thinking"] is True
    assert info["summary_thinking"] is False
    assert info["thinking_type"] == "enabled"
    assert agent_config.MAIN_MODEL is not None
    assert agent_config.SUMMARY_MODEL is not None


def test_apply_model_overrides_can_disable_thinking():
    with patch.object(model_override, "ENABLE_MODEL_THINKING", False):
        info = apply_model_overrides()

    assert info["main_thinking"] is False
    assert info["thinking_type"] == "disabled"
