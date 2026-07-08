"""Tests for data/data_base package."""

from pathlib import Path

from data.data_base import backup_file, db, local_file


def test_database_paths_exist():
    assert Path(backup_file).exists(), "travel2.sqlite backup must exist"
    assert Path(local_file).exists(), "travel_new.sqlite must exist"
    assert db == local_file


def test_backup_and_local_share_directory():
    assert Path(backup_file).parent == Path(local_file).parent
