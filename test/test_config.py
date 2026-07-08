"""Tests for api_view configuration."""

from api_view.config import API_PREFIX, PROJECT_DIR


def test_project_dir_points_to_repo_root():
    assert PROJECT_DIR.name == "AI-Travel-Assistant"
    assert (PROJECT_DIR / "agent").is_dir()
    assert (PROJECT_DIR / "data" / "data_base").is_dir()


def test_api_prefix():
    assert API_PREFIX == "/api/v1"
