"""Tests for the label propagation logic in autodoist.

These tests mock Todoist models and verify that add_label/remove_label
and the sequential propagation logic work correctly.

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


# ---------------------------------------------------------------------------
# Tests for sequential propagation behavior
# ---------------------------------------------------------------------------

class TestSequentialPropagation:
    """Simulates the sequential labeling loop from autodoist_magic (lines 1395-1416).

    In sequential mode, only the FIRST non-completed child should get the label.
    This relies on:
    1. add_label mutating task.labels in-place (so the parent "has" the label)
    2. remove_label mutating task.labels in-place (so after removing from parent,
       subsequent children don't see it)
    """

    def _make_task(self, id, content, parent_id, order, labels=None):
        return FakeTask(
            id=id, content=content, project_id="p1", section_id=None,
            parent_id=parent_id, labels=labels or [], order=order,
        )

    def test_first_child_gets_label_on_first_iteration(self):
        """On the first iteration, the parent gets labeled at line 1342,
        then the label propagates to the first child within the same iteration."""
        parent = self._make_task("100", "Parent", None, 0)
        child1 = self._make_task("201", "Child 1", "100", 0)
        child2 = self._make_task("202", "Child 2", "100", 1)

        ids, labels_map = {}, {}
        next_action_label = "next_action"

        # Step 1: Parent gets labeled (simulates line 1342)
        add_label(parent, next_action_label, ids, labels_map)
        assert next_action_label in parent.labels

        # Step 2: Sequential propagation loop (simulates lines 1397-1416)
        child_tasks = [child1, child2]
        for child_task in child_tasks:
            if child_task.content.startswith('*'):
                continue
            remove_label(child_task, next_action_label, ids, labels_map)
            if not child_task.is_completed and next_action_label in parent.labels:
                add_label(child_task, next_action_label, ids, labels_map)
                remove_label(parent, next_action_label, ids, labels_map)

        # Verify: only child1 has label, parent lost it
        assert next_action_label in child1.labels, "first child should have label"
        assert next_action_label not in child2.labels, "second child should NOT have label"
        assert next_action_label not in parent.labels, "parent should have lost label"

    def test_second_iteration_propagates_deeper(self):
        """On the second iteration, child1 (now labeled from API) propagates
        to its own first child."""
        child1 = self._make_task("201", "Child 1", "100", 0,
                                 labels=["next_action"])  # has label from previous sync
        grandchild1 = self._make_task("301", "Grandchild 1", "201", 0)
        grandchild2 = self._make_task("302", "Grandchild 2", "201", 1)

        ids, labels_map = {}, {}
        next_action_label = "next_action"

        # child1 already has the label (from API), so add_label is a no-op
        add_label(child1, next_action_label, ids, labels_map)

        # Sequential propagation for child1's children
        grandchildren = [grandchild1, grandchild2]
        for gc in grandchildren:
            remove_label(gc, next_action_label, ids, labels_map)
            if not gc.is_completed and next_action_label in child1.labels:
                add_label(gc, next_action_label, ids, labels_map)
                remove_label(child1, next_action_label, ids, labels_map)

        assert next_action_label in grandchild1.labels, "first grandchild should have label"
        assert next_action_label not in grandchild2.labels, "second grandchild should NOT"
        assert next_action_label not in child1.labels, "child1 should have lost label"

    def test_reordering_moves_label(self):
        """When tasks are reordered, the label should move to the new first child."""
        parent = self._make_task("100", "Parent", None, 0,
                                 labels=["next_action"])  # from previous sync
        # child2 is now first (order=0), child1 second (order=1) — swapped
        child1 = self._make_task("201", "Child 1 (was first)", "100", 1,
                                 labels=["next_action"])  # still has old label
        child2 = self._make_task("202", "Child 2 (now first)", "100", 0)

        ids, labels_map = {}, {}
        next_action_label = "next_action"

        # add_label on parent — already has it, no-op
        add_label(parent, next_action_label, ids, labels_map)

        # Sequential propagation — children sorted by order
        child_tasks = sorted([child1, child2], key=lambda x: x.order)
        for child_task in child_tasks:
            remove_label(child_task, next_action_label, ids, labels_map)
            if not child_task.is_completed and next_action_label in parent.labels:
                add_label(child_task, next_action_label, ids, labels_map)
                remove_label(parent, next_action_label, ids, labels_map)

        assert next_action_label in child2.labels, "new first child should have label"
        assert next_action_label not in child1.labels, "old first child should lose label"
        assert next_action_label not in parent.labels, "parent should lose label"

    def test_parallel_propagation(self):
        """In parallel mode, all children get the label and parent loses it."""
        parent = self._make_task("100", "Parent", None, 0,
                                 labels=["next_action"])
        child1 = self._make_task("201", "Child 1", "100", 0)
        child2 = self._make_task("202", "Child 2", "100", 1)

        ids, labels_map = {}, {}
        next_action_label = "next_action"

        # Parallel logic (simulates lines 1419-1434)
        if next_action_label in parent.labels:
            remove_label(parent, next_action_label, ids, labels_map)
            for child_task in [child1, child2]:
                if child_task.content.startswith('*'):
                    continue
                if not child_task.is_completed:
                    add_label(child_task, next_action_label, ids, labels_map)

        assert next_action_label in child1.labels
        assert next_action_label in child2.labels
        assert next_action_label not in parent.labels


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
