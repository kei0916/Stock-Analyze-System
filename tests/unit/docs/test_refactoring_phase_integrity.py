"""Refactoring tracker integrity tests."""

from scripts.verify_refactoring_phase import (
    find_history_label_violations,
    find_master_markdown_link_violations,
)


def test_refactoring_tracker_links_resolve_to_tracked_files():
    violations = find_master_markdown_link_violations()

    assert violations == []


def test_source_files_do_not_contain_history_labels():
    violations = find_history_label_violations()

    assert violations == []
