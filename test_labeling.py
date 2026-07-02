"""Tests for Todoist label update helpers in autodoist.

These tests mock Todoist models and verify that add_label/remove_label keep
the overview update maps consistent. Next-action propagation behavior is
covered through the planner interface in test_autodoist.py.

Run with: python -m pytest test_labeling.py -v
"""

import sys
import types
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import Optional

# We need to mock the todoist imports before importing autodoist
# Create minimal mock models that behave like the real ones


@dataclass
class FakeTask:
    id: str
    content: str
    project_id: str
    section_id: Optional[str]
    parent_id: Optional[str]
    labels: list
    order: int
    is_completed: bool = False
    description: str = ""
    priority: int = 1
    due: None = None
    deadline: None = None
    duration: None = None
    is_collapsed: bool = False
    assignee_id: None = None
    assigner_id: None = None
    completed_at: None = None
    creator_id: str = "1"
    created_at: str = "2024-01-01"
    updated_at: str = "2024-01-01"
    meta: None = None
    r_tag: int = 0


@dataclass
class FakeSection:
    id: Optional[str]
    name: Optional[str]
    project_id: str
    is_collapsed: bool = False
    order: int = 0


@dataclass
class FakeProject:
    id: str
    name: str
    is_inbox_project: bool = False
    order: int = 0


# ---------------------------------------------------------------------------
# Import only the functions we need from autodoist, patching heavy deps
# ---------------------------------------------------------------------------

# Patch the todoist_api_python imports so autodoist.py can be loaded
_models = types.ModuleType("todoist_api_python.models")
_models.Task = FakeTask
_models.Section = FakeSection
_models.Project = FakeProject

_api_mod = types.ModuleType("todoist_api_python.api")
_api_mod.TodoistAPI = MagicMock

sys.modules["todoist_api_python"] = types.ModuleType("todoist_api_python")
sys.modules["todoist_api_python.models"] = _models
sys.modules["todoist_api_python.api"] = _api_mod

# Now we can import the functions
from autodoist import add_label, remove_label


# ---------------------------------------------------------------------------
# Tests for add_label / remove_label
# ---------------------------------------------------------------------------

class TestAddLabel:
    def test_adds_label_when_missing(self):
        task = FakeTask(id="1", content="Test", project_id="p1",
                        section_id=None, parent_id=None, labels=[], order=0)
        ids, labels_map = {}, {}

        add_label(task, "next_action", ids, labels_map)

        assert "next_action" in task.labels, "label should be added to task.labels in-place"
        assert ids["1"] == 1
        assert labels_map["1"] == task.labels

    def test_skips_when_already_present(self):
        task = FakeTask(id="1", content="Test", project_id="p1",
                        section_id=None, parent_id=None,
                        labels=["next_action"], order=0)
        ids, labels_map = {}, {}

        add_label(task, "next_action", ids, labels_map)

        assert task.labels == ["next_action"], "should not duplicate"
        assert "1" not in ids

    def test_mutates_task_labels_in_place(self):
        """The sequential propagation algorithm relies on add_label mutating
        task.labels directly (not a copy). After add_label, checking
        `label in task.labels` must return True."""
        task = FakeTask(id="1", content="Test", project_id="p1",
                        section_id=None, parent_id=None, labels=[], order=0)
        ids, labels_map = {}, {}

        add_label(task, "next_action", ids, labels_map)

        # This is the critical check — line 1412 in autodoist.py depends on this
        assert "next_action" in task.labels


class TestRemoveLabel:
    def test_removes_label_when_present(self):
        task = FakeTask(id="1", content="Test", project_id="p1",
                        section_id=None, parent_id=None,
                        labels=["next_action"], order=0)
        ids, labels_map = {}, {}

        remove_label(task, "next_action", ids, labels_map)

        assert "next_action" not in task.labels
        assert ids["1"] == -1

    def test_skips_when_not_present(self):
        task = FakeTask(id="1", content="Test", project_id="p1",
                        section_id=None, parent_id=None, labels=[], order=0)
        ids, labels_map = {}, {}

        remove_label(task, "next_action", ids, labels_map)

        assert task.labels == []
        assert "1" not in ids

    def test_mutates_task_labels_in_place(self):
        """remove_label must also mutate in-place so that within the same
        iteration, subsequent checks see the label as removed."""
        task = FakeTask(id="1", content="Test", project_id="p1",
                        section_id=None, parent_id=None,
                        labels=["next_action", "other"], order=0)
        ids, labels_map = {}, {}

        remove_label(task, "next_action", ids, labels_map)

        assert "next_action" not in task.labels
        assert "other" in task.labels


class TestOverviewNetEffect:
    """Tests that the overview_task_ids net effect is correct for commit_labels_update."""

    def _make_task(self, id, labels=None):
        return FakeTask(
            id=id, content="Test", project_id="p1", section_id=None,
            parent_id=None, labels=labels or [], order=0,
        )

    def test_add_then_remove_cancels_out(self):
        """When a parent gets labeled then immediately un-labeled (propagated to child),
        the net effect for the parent should be 0 → filtered out in commit_labels_update."""
        parent = self._make_task("100")
        child = self._make_task("201")
        ids, labels_map = {}, {}

        add_label(parent, "next_action", ids, labels_map)
        # ... propagation happens ...
        add_label(child, "next_action", ids, labels_map)
        remove_label(parent, "next_action", ids, labels_map)

        # Parent: +1 (add) -1 (remove) = 0 → should be filtered
        assert ids["100"] == 0
        # Child: +1 → should be synced
        assert ids["201"] == 1

        # Simulate commit_labels_update filtering
        filtered = [k for k, v in ids.items() if v != 0]
        assert "100" not in filtered
        assert "201" in filtered
