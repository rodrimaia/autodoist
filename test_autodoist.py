"""Comprehensive tests for autodoist core functionality.

Covers: suffix parsing (check_name), hierarchy type resolution,
child task propagation, first_found tracking, and integration tests.

Run with: python -m pytest test_autodoist.py -v
"""

import sys
import types
import argparse
import io
import json
import logging
import sqlite3
import requests
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Mock Todoist models (same pattern as test_labeling.py)
# ---------------------------------------------------------------------------

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


@dataclass
class FakeLabel:
    id: str
    name: str


@dataclass
class FakeDue:
    date: object
    is_recurring: bool = False


# Patch todoist imports before importing autodoist
_models = types.ModuleType("todoist_api_python.models")
_models.Task = FakeTask
_models.Section = FakeSection
_models.Project = FakeProject

_api_mod = types.ModuleType("todoist_api_python.api")
_api_mod.TodoistAPI = MagicMock

sys.modules["todoist_api_python"] = types.ModuleType("todoist_api_python")
sys.modules["todoist_api_python.models"] = _models
sys.modules["todoist_api_python.api"] = _api_mod

from autodoist import (
    check_name, add_label, remove_label,
    get_type, get_project_type, get_section_type, get_task_type,
    db_check_existance, db_read_value, db_update_value,
    execute_query, execute_read_query, get_labels_with_startup_retry,
    initialise_api, verify_label_existance, configure_logging,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_args(**overrides):
    """Create a minimal args namespace for check_name."""
    defaults = dict(
        s_suffix='-',
        p_suffix='=',
        inbox=None,
        all_projects=False,
        ignore_suffix=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def make_task(id, content="Task", parent_id=None, order=0, labels=None,
              is_completed=False, section_id=None, project_id="p1"):
    return FakeTask(
        id=id, content=content, project_id=project_id,
        section_id=section_id, parent_id=parent_id,
        labels=labels if labels is not None else [], order=order,
        is_completed=is_completed,
    )


def create_test_db():
    """Create an in-memory SQLite database with the autodoist schema."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            project_type TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER,
            section_type TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            task_type TEXT,
            parent_type TEXT,
            due_date TEXT,
            r_tag INTEGER
        )
    """)
    conn.commit()
    return conn


def http_error(status_code):
    response = requests.Response()
    response.status_code = status_code
    error = requests.exceptions.HTTPError(
        f"{status_code} error", response=response)
    return error


def apply_parentless_task_logic(task, next_action_label, dominant_type, first_found,
                                overview_task_ids, overview_task_labels):
    """Replicate the parentless task labeling logic from autodoist.py lines 1197-1258.

    This is a direct copy of the branching logic so we can test it in isolation.
    """
    # If indicated on project level
    if dominant_type[0] == 's':
        if not first_found[0]:

            if dominant_type[1] == 's':
                if not first_found[1]:
                    add_label(task, next_action_label, overview_task_ids, overview_task_labels)

                elif next_action_label in task.labels:
                    remove_label(task, next_action_label, overview_task_ids, overview_task_labels)

            elif dominant_type[1] == 'p':
                add_label(task, next_action_label, overview_task_ids, overview_task_labels)

    elif dominant_type[0] == 'p':

        if dominant_type[1] == 's':
            if not first_found[1]:
                add_label(task, next_action_label, overview_task_ids, overview_task_labels)

            elif next_action_label in task.labels:
                remove_label(task, next_action_label, overview_task_ids, overview_task_labels)

        elif dominant_type[1] == 'p':
            add_label(task, next_action_label, overview_task_ids, overview_task_labels)

    # If indicated on section level
    if dominant_type[0] == 'x' and dominant_type[1] == 's':
        if not first_found[1]:
            add_label(task, next_action_label, overview_task_ids, overview_task_labels)

        elif next_action_label in task.labels:
            remove_label(task, next_action_label, overview_task_ids, overview_task_labels)

    elif dominant_type[0] == 'x' and dominant_type[1] == 'p':
        add_label(task, next_action_label, overview_task_ids, overview_task_labels)

    # If indicated on parentless task level
    if dominant_type[1] == 'x' and dominant_type[2] == 's':
        if not first_found[1]:
            add_label(task, next_action_label, overview_task_ids, overview_task_labels)

        elif next_action_label in task.labels:
            remove_label(task, next_action_label, overview_task_ids, overview_task_labels)

    elif dominant_type[1] == 'x' and dominant_type[2] == 'p':
        add_label(task, next_action_label, overview_task_ids, overview_task_labels)


# ---------------------------------------------------------------------------
# Group 0: TestStartupVerification - Required label startup checks
# ---------------------------------------------------------------------------

class TestLoggingConfiguration:
    def teardown_method(self):
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.WARNING)

    def test_configures_console_and_file_handlers_for_json_logs(self, tmp_path):
        log_file = tmp_path / "debug.log"
        console = io.StringIO()

        configure_logging(logging.INFO, log_path=log_file, stream=console)
        logging.info(
            "Todoist temporary failure while verifying required label",
            extra={
                "component": "startup_verification",
                "operation": "verify_required_label",
                "label": "next_action",
            },
        )

        console_log = json.loads(console.getvalue())
        file_log = json.loads(log_file.read_text())

        assert console_log["level"] == "INFO"
        assert console_log["message"] == "Todoist temporary failure while verifying required label"
        assert console_log["component"] == "startup_verification"
        assert console_log["operation"] == "verify_required_label"
        assert console_log["label"] == "next_action"
        assert "timestamp" in console_log
        assert file_log == console_log

    def test_preserves_configured_log_level(self, tmp_path):
        console = io.StringIO()

        configure_logging(logging.WARNING, log_path=tmp_path / "debug.log", stream=console)
        logging.info("hidden")
        logging.warning("visible")

        log = json.loads(console.getvalue())

        assert log["level"] == "WARNING"
        assert log["message"] == "visible"

    def test_startup_retry_logs_structured_operational_fields(self, tmp_path):
        api = MagicMock()
        labels = [FakeLabel(id="1", name="next_action")]
        api.get_labels.side_effect = [
            http_error(429),
            [labels],
        ]
        console = io.StringIO()

        configure_logging(logging.WARNING, log_path=tmp_path / "debug.log", stream=console)
        get_labels_with_startup_retry(
            api,
            "next_action",
            sleep=MagicMock(),
            monotonic=MagicMock(side_effect=[0, 0]),
        )

        log = json.loads(console.getvalue())

        assert log["level"] == "WARNING"
        assert log["component"] == "startup_verification"
        assert log["operation"] == "verify_required_label"
        assert log["label"] == "next_action"
        assert log["error_type"] == "rate_limited"
        assert log["retry_in_seconds"] == 5
        assert log["retry_window_remaining_seconds"] == 600

class TestStartupVerification:
    LABEL = "next_action"

    def test_get_labels_retries_temporary_error_then_returns_labels(self):
        api = MagicMock()
        labels = [FakeLabel(id="1", name=self.LABEL)]
        api.get_labels.side_effect = [
            http_error(429),
            [labels],
        ]
        sleep = MagicMock()
        monotonic = MagicMock(side_effect=[0, 0])

        result = get_labels_with_startup_retry(
            api, self.LABEL, sleep=sleep, monotonic=monotonic)

        assert result == labels
        assert api.get_labels.call_count == 2
        sleep.assert_called_once_with(5)

    def test_get_labels_uses_exponential_backoff_until_success(self):
        api = MagicMock()
        labels = [FakeLabel(id="1", name=self.LABEL)]
        api.get_labels.side_effect = [
            http_error(429),
            http_error(500),
            [labels],
        ]
        sleep = MagicMock()
        monotonic = MagicMock(side_effect=[0, 0, 5])

        result = get_labels_with_startup_retry(
            api, self.LABEL, sleep=sleep, monotonic=monotonic)

        assert result == labels
        assert [call.args[0] for call in sleep.call_args_list] == [5, 10]

    def test_get_labels_fails_fast_for_auth_error(self):
        api = MagicMock()
        api.get_labels.side_effect = http_error(401)
        sleep = MagicMock()

        with pytest.raises(requests.exceptions.HTTPError):
            get_labels_with_startup_retry(api, self.LABEL, sleep=sleep)

        assert api.get_labels.call_count == 1
        sleep.assert_not_called()

    def test_get_labels_exits_after_retry_window_expires(self):
        api = MagicMock()
        api.get_labels.side_effect = http_error(429)
        sleep = MagicMock()
        monotonic = MagicMock(side_effect=[0, 601])

        with pytest.raises(SystemExit) as error:
            get_labels_with_startup_retry(
                api, self.LABEL, sleep=sleep, monotonic=monotonic)

        assert error.value.code == 1
        assert api.get_labels.call_count == 1
        sleep.assert_not_called()

    def test_initialise_api_verifies_label_with_startup_retry(self):
        args = argparse.Namespace(
            api_key="fake",
            label=self.LABEL,
            regeneration=None,
            end=None,
        )
        api = MagicMock()

        with patch("autodoist.TodoistAPI", return_value=api), \
                patch("autodoist.verify_label_existance") as verify_label:
            result = initialise_api(args)

        assert result is api
        verify_label.assert_called_once_with(api, self.LABEL, 1)

    def test_label_creation_errors_are_not_retried(self):
        api = MagicMock()
        api.get_labels.return_value = [[]]
        api.add_label.side_effect = http_error(429)

        with patch("autodoist.query_yes_no", return_value=True), \
                pytest.raises(requests.exceptions.HTTPError):
            verify_label_existance(api, self.LABEL, 1)

        api.add_label.assert_called_once_with(name=self.LABEL)
        assert api.get_labels.call_count == 1


# ---------------------------------------------------------------------------
# Group 1: TestCheckName - Suffix parsing
# ---------------------------------------------------------------------------

class TestCheckName:
    """Tests for check_name() - parses project/section/task name suffixes."""

    def test_none_returns_none(self):
        assert check_name(make_args(), None, 3) is None

    def test_inbox_returns_args_inbox_none(self):
        assert check_name(make_args(inbox=None), 'Inbox', 3) is None

    def test_inbox_returns_args_inbox_value(self):
        assert check_name(make_args(inbox='sss'), 'Inbox', 3) == 'sss'

    def test_no_suffix_returns_none(self):
        assert check_name(make_args(), 'My Project', 3) is None

    # Project-level (num=3)
    def test_project_single_dash(self):
        assert check_name(make_args(), 'Project -', 3) == 'sss'

    def test_project_double_dash(self):
        assert check_name(make_args(), 'Project --', 3) == 'sss'

    def test_project_triple_dash(self):
        assert check_name(make_args(), 'Project ---', 3) == 'sss'

    def test_project_single_equal(self):
        assert check_name(make_args(), 'Project =', 3) == 'ppp'

    def test_project_double_equal(self):
        assert check_name(make_args(), 'Project ==', 3) == 'ppp'

    def test_project_triple_equal(self):
        assert check_name(make_args(), 'Project ===', 3) == 'ppp'

    def test_project_equal_dash(self):
        # '=-' -> expand last '-' -> '=--' -> 'pss'
        assert check_name(make_args(), 'Project =-', 3) == 'pss'

    def test_project_dash_equal(self):
        # '-=' -> expand last '=' -> '-==' -> 'spp'
        assert check_name(make_args(), 'Project -=', 3) == 'spp'

    def test_project_three_mixed(self):
        assert check_name(make_args(), 'Project -=-', 3) == 'sps'

    def test_project_three_mixed_psp(self):
        assert check_name(make_args(), 'Project =-=', 3) == 'psp'

    # Section-level (num=2)
    def test_section_single_dash(self):
        # '-' -> expand to '--' -> 'ss' -> pad to 'xss'
        assert check_name(make_args(), 'Section -', 2) == 'xss'

    def test_section_double_dash(self):
        assert check_name(make_args(), 'Section --', 2) == 'xss'

    def test_section_single_equal(self):
        assert check_name(make_args(), 'Section =', 2) == 'xpp'

    def test_section_mixed_dash_equal(self):
        assert check_name(make_args(), 'Section -=', 2) == 'xsp'

    def test_section_mixed_equal_dash(self):
        assert check_name(make_args(), 'Section =-', 2) == 'xps'

    # Task-level (num=1)
    def test_task_dash(self):
        # '-' -> 's' -> pad to 'xxs'
        assert check_name(make_args(), 'Task -', 1) == 'xxs'

    def test_task_equal(self):
        assert check_name(make_args(), 'Task =', 1) == 'xxp'

    # --all_projects behavior
    def test_all_projects_no_suffix_defaults_sequential(self):
        args = make_args(all_projects=True)
        assert check_name(args, 'Project', 3) == 'sss'

    def test_all_projects_with_suffix_respects_suffix(self):
        args = make_args(all_projects=True)
        assert check_name(args, 'Project =', 3) == 'ppp'

    def test_all_projects_only_affects_projects(self):
        args = make_args(all_projects=True)
        # num=2 (section) should not get default
        assert check_name(args, 'Section', 2) is None

    def test_all_projects_ignore_suffix_no_suffix(self):
        args = make_args(all_projects=True, ignore_suffix=True)
        assert check_name(args, 'Project_ignore', 3) is None

    def test_all_projects_ignore_suffix_with_suffix(self):
        args = make_args(all_projects=True, ignore_suffix=True)
        assert check_name(args, 'Project_ignore -', 3) == 'sss'

    # Edge cases
    def test_empty_string(self):
        assert check_name(make_args(), '', 3) is None

    def test_only_dashes(self):
        assert check_name(make_args(), '---', 3) == 'sss'

    def test_custom_suffix_chars(self):
        args = make_args(s_suffix='#', p_suffix='@')
        assert check_name(args, 'Project ##', 3) == 'sss'

    def test_custom_suffix_parallel(self):
        args = make_args(s_suffix='#', p_suffix='@')
        assert check_name(args, 'Project @', 3) == 'ppp'

    def test_suffix_without_space(self):
        # 'Project-' should match since regex looks at end of string
        assert check_name(make_args(), 'Project-', 3) == 'sss'

    def test_suffix_in_middle_ignored(self):
        # Only suffix at end matters
        assert check_name(make_args(), 'My - Project', 3) is None


# ---------------------------------------------------------------------------
# Group 2: TestHierarchyTypeResolution - Parentless task labeling logic
# ---------------------------------------------------------------------------

class TestHierarchyTypeResolution:
    """Tests for the parentless task labeling logic (lines 1197-1258).

    Uses apply_parentless_task_logic() which replicates the exact branching
    from autodoist_magic.
    """

    LABEL = "next_action"

    def _run(self, dominant_type, first_found, has_label=False):
        labels = [self.LABEL] if has_label else []
        task = make_task("t1", labels=labels)
        ids, labels_map = {}, {}
        apply_parentless_task_logic(
            task, self.LABEL, dominant_type, first_found, ids, labels_map)
        return self.LABEL in task.labels

    # --- Project-level sequential sections (dominant_type[0]='s') ---

    def test_sss_first_section_first_task(self):
        assert self._run('sss', [False, False, False]) is True

    def test_sss_first_section_second_task(self):
        # second task (first_found[1]=True), had label from manual move
        labels = [self.LABEL]
        task = make_task("t1", labels=labels)
        ids, labels_map = {}, {}
        apply_parentless_task_logic(
            task, self.LABEL, 'sss', [False, True, False], ids, labels_map)
        assert self.LABEL not in task.labels

    def test_sss_second_section(self):
        # second section (first_found[0]=True) - no label
        assert self._run('sss', [True, False, False]) is False

    def test_sps_first_section_first_task(self):
        assert self._run('sps', [False, False, False]) is True

    def test_sps_first_section_second_task(self):
        # parallel tasks - second task also gets label
        assert self._run('sps', [False, True, False]) is True

    def test_sps_second_section(self):
        assert self._run('sps', [True, False, False]) is False

    # --- Project-level parallel sections (dominant_type[0]='p') ---

    def test_pss_first_task(self):
        assert self._run('pss', [False, False, False]) is True

    def test_pss_second_task(self):
        labels = [self.LABEL]
        task = make_task("t1", labels=labels)
        ids, labels_map = {}, {}
        apply_parentless_task_logic(
            task, self.LABEL, 'pss', [False, True, False], ids, labels_map)
        assert self.LABEL not in task.labels

    def test_pps_any_task(self):
        assert self._run('pps', [False, False, False]) is True

    def test_pps_second_task(self):
        assert self._run('pps', [False, True, False]) is True

    # --- Section-level (dominant_type[0]='x') ---

    def test_xss_first_task(self):
        assert self._run('xss', [False, False, False]) is True

    def test_xss_second_task(self):
        labels = [self.LABEL]
        task = make_task("t1", labels=labels)
        ids, labels_map = {}, {}
        apply_parentless_task_logic(
            task, self.LABEL, 'xss', [False, True, False], ids, labels_map)
        assert self.LABEL not in task.labels

    def test_xpp_any_task(self):
        assert self._run('xpp', [False, True, False]) is True

    def test_xps_first_task(self):
        assert self._run('xps', [False, False, False]) is True

    # --- Task-level (dominant_type[1]='x') - BUG ZONE ---

    def test_xxs_first_task_gets_label(self):
        """First parentless task with task-level sequential should get label."""
        assert self._run('xxs', [False, False, False]) is True

    def test_xxs_second_task_no_label(self):
        assert self._run('xxs', [False, True, False]) is False

    def test_xxp_any_task(self):
        assert self._run('xxp', [False, True, False]) is True

    def test_xxp_first_task(self):
        assert self._run('xxp', [False, False, False]) is True


# ---------------------------------------------------------------------------
# Group 3: TestChildTaskPropagation - Sequential/parallel child labeling
# ---------------------------------------------------------------------------

class TestChildTaskPropagation:
    """Tests for child task label propagation (lines 1279-1319)."""

    LABEL = "next_action"

    def _run_sequential(self, parent, children):
        ids, labels_map = {}, {}
        for child in children:
            if child.content.startswith('*'):
                continue
            remove_label(child, self.LABEL, ids, labels_map)
            if not child.is_completed and self.LABEL in parent.labels:
                add_label(child, self.LABEL, ids, labels_map)
                remove_label(parent, self.LABEL, ids, labels_map)
        return ids, labels_map

    def _run_parallel(self, parent, children):
        ids, labels_map = {}, {}
        if self.LABEL in parent.labels:
            remove_label(parent, self.LABEL, ids, labels_map)
            for child in children:
                if child.content.startswith('*'):
                    continue
                if not child.is_completed:
                    add_label(child, self.LABEL, ids, labels_map)
        return ids, labels_map

    def test_sequential_first_child_gets_label(self):
        parent = make_task("p", labels=[self.LABEL])
        c1 = make_task("c1", parent_id="p", order=0)
        c2 = make_task("c2", parent_id="p", order=1)
        c3 = make_task("c3", parent_id="p", order=2)
        self._run_sequential(parent, [c1, c2, c3])

        assert self.LABEL in c1.labels
        assert self.LABEL not in c2.labels
        assert self.LABEL not in c3.labels
        assert self.LABEL not in parent.labels

    def test_sequential_skips_completed_first_child(self):
        parent = make_task("p", labels=[self.LABEL])
        c1 = make_task("c1", parent_id="p", order=0, is_completed=True)
        c2 = make_task("c2", parent_id="p", order=1)
        self._run_sequential(parent, [c1, c2])

        assert self.LABEL not in c1.labels
        assert self.LABEL in c2.labels
        assert self.LABEL not in parent.labels

    def test_sequential_skips_headered_first_child(self):
        parent = make_task("p", labels=[self.LABEL])
        c1 = make_task("c1", content="* Header", parent_id="p", order=0)
        c2 = make_task("c2", parent_id="p", order=1)
        self._run_sequential(parent, [c1, c2])

        assert self.LABEL not in c1.labels
        assert self.LABEL in c2.labels
        assert self.LABEL not in parent.labels

    def test_sequential_parent_without_label_no_propagation(self):
        parent = make_task("p", labels=[])
        c1 = make_task("c1", parent_id="p", order=0)
        c2 = make_task("c2", parent_id="p", order=1)
        self._run_sequential(parent, [c1, c2])

        assert self.LABEL not in c1.labels
        assert self.LABEL not in c2.labels

    def test_parallel_all_children_get_label(self):
        parent = make_task("p", labels=[self.LABEL])
        c1 = make_task("c1", parent_id="p", order=0)
        c2 = make_task("c2", parent_id="p", order=1)
        c3 = make_task("c3", parent_id="p", order=2)
        self._run_parallel(parent, [c1, c2, c3])

        assert self.LABEL in c1.labels
        assert self.LABEL in c2.labels
        assert self.LABEL in c3.labels
        assert self.LABEL not in parent.labels

    def test_parallel_skips_completed(self):
        parent = make_task("p", labels=[self.LABEL])
        c1 = make_task("c1", parent_id="p", order=0)
        c2 = make_task("c2", parent_id="p", order=1, is_completed=True)
        self._run_parallel(parent, [c1, c2])

        assert self.LABEL in c1.labels
        assert self.LABEL not in c2.labels
        assert self.LABEL not in parent.labels

    def test_parallel_skips_headered(self):
        parent = make_task("p", labels=[self.LABEL])
        c1 = make_task("c1", parent_id="p", order=0)
        c2 = make_task("c2", content="* Done", parent_id="p", order=1)
        self._run_parallel(parent, [c1, c2])

        assert self.LABEL in c1.labels
        assert self.LABEL not in c2.labels

    def test_no_children_parent_keeps_label(self):
        parent = make_task("p", labels=[self.LABEL])
        self._run_sequential(parent, [])
        assert self.LABEL in parent.labels


# ---------------------------------------------------------------------------
# Group 4: TestGetType - Type resolution with DB
# ---------------------------------------------------------------------------

class TestGetType:
    """Tests for get_type() with real in-memory SQLite."""

    def setup_method(self):
        self.conn = create_test_db()
        self.args = make_args()

    def teardown_method(self):
        self.conn.close()

    def test_project_type_new(self):
        project = FakeProject(id="p1", name="Work --")
        db_check_existance(self.conn, project)
        ptype, changed = get_project_type(self.args, self.conn, project)
        assert ptype == 'sss'
        assert changed == 1

    def test_project_type_unchanged(self):
        project = FakeProject(id="p1", name="Work --")
        db_check_existance(self.conn, project)
        # First call sets it
        get_project_type(self.args, self.conn, project)
        # Second call - unchanged
        ptype, changed = get_project_type(self.args, self.conn, project)
        assert ptype == 'sss'
        assert changed == 0

    def test_project_type_changed(self):
        project = FakeProject(id="p1", name="Work --")
        db_check_existance(self.conn, project)
        get_project_type(self.args, self.conn, project)
        # Change name to parallel
        project.name = "Work =="
        ptype, changed = get_project_type(self.args, self.conn, project)
        assert ptype == 'ppp'
        assert changed == 1

    def test_section_type(self):
        section = FakeSection(id="s1", name="Todo -", project_id="p1")
        project = FakeProject(id="p1", name="Work")
        db_check_existance(self.conn, section)
        stype, changed = get_section_type(self.args, self.conn, section, project)
        assert stype == 'xss'
        assert changed == 1

    def test_task_type(self):
        task = make_task("t1", content="Parent -")
        section = FakeSection(id="s1", name="Todo", project_id="p1")
        project = FakeProject(id="p1", name="Work")
        db_check_existance(self.conn, task)
        ttype, changed = get_task_type(self.args, self.conn, task, section, project)
        assert ttype == 'xxs'
        assert changed == 1

    def test_no_suffix_returns_none(self):
        project = FakeProject(id="p1", name="Work")
        db_check_existance(self.conn, project)
        ptype, changed = get_project_type(self.args, self.conn, project)
        assert ptype is None


# ---------------------------------------------------------------------------
# Group 5: TestIntegration - End-to-end autodoist_magic
# ---------------------------------------------------------------------------

class TestIntegration:
    """Integration tests for autodoist_magic with mocked API and in-memory DB.

    These test the full label assignment pipeline end-to-end.
    """

    LABEL = "next_action"

    def _make_args(self, **overrides):
        defaults = dict(
            api_key="fake",
            label=self.LABEL,
            s_suffix='-',
            p_suffix='=',
            inbox=None,
            all_projects=False,
            ignore_suffix=False,
            regeneration=None,
            regen_label_names=None,
            end=None,
            hide_future=0,
            dateformat="%d-%m-%Y",
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def _make_api(self, projects, sections, tasks):
        api = MagicMock()
        api.get_projects.return_value = [projects]
        api.get_sections.return_value = [sections]
        api.get_tasks.return_value = [tasks]
        api.update_task = MagicMock()
        return api

    def _run(self, projects, sections, tasks, **args_overrides):
        from autodoist import autodoist_magic
        args = self._make_args(**args_overrides)
        api = self._make_api(projects, sections, tasks)
        conn = create_test_db()
        try:
            result = autodoist_magic(args, api, conn)
            return result, tasks
        finally:
            conn.close()

    def test_project_single_dash_sequential(self):
        """Project with '-' suffix: only first parentless task gets label."""
        project = FakeProject(id="p1", name="Work -")
        tasks = [
            make_task("t1", project_id="p1", order=0),
            make_task("t2", project_id="p1", order=1),
            make_task("t3", project_id="p1", order=2),
        ]
        (ids, labels, _), _ = self._run([project], [], tasks)

        assert self.LABEL in tasks[0].labels
        assert self.LABEL not in tasks[1].labels
        assert self.LABEL not in tasks[2].labels

    def test_project_double_dash_sequential(self):
        """Project with '--' suffix: same as '-', only first task labeled."""
        project = FakeProject(id="p1", name="Work --")
        tasks = [
            make_task("t1", project_id="p1", order=0),
            make_task("t2", project_id="p1", order=1),
        ]
        (ids, labels, _), _ = self._run([project], [], tasks)

        assert self.LABEL in tasks[0].labels
        assert self.LABEL not in tasks[1].labels

    def test_project_equal_parallel(self):
        """Project with '=' suffix: all parentless tasks get label."""
        project = FakeProject(id="p1", name="Work =")
        tasks = [
            make_task("t1", project_id="p1", order=0),
            make_task("t2", project_id="p1", order=1),
            make_task("t3", project_id="p1", order=2),
        ]
        (ids, labels, _), _ = self._run([project], [], tasks)

        assert self.LABEL in tasks[0].labels
        assert self.LABEL in tasks[1].labels
        assert self.LABEL in tasks[2].labels

    def test_completed_tasks_skipped(self):
        """Completed tasks should not get the label."""
        project = FakeProject(id="p1", name="Work -")
        tasks = [
            make_task("t1", project_id="p1", order=0, is_completed=True),
            make_task("t2", project_id="p1", order=1),
        ]
        (ids, labels, _), _ = self._run([project], [], tasks)

        assert self.LABEL not in tasks[0].labels
        assert self.LABEL in tasks[1].labels

    def test_hide_future_skips_task_with_sdk_date_object(self):
        """Future tasks should not get the label when SDK returns a date object."""
        project = FakeProject(id="p1", name="Work -")
        task = make_task("t1", project_id="p1", order=0)
        task.due = FakeDue(date=date.today() + timedelta(days=365))

        (ids, labels, _), _ = self._run([project], [], [task], hide_future=14)

        assert self.LABEL not in task.labels
        assert ids == {"t1": 0}
        assert labels == {"t1": []}

    def test_hide_future_skips_task_with_sdk_datetime_object(self):
        """Future tasks should not get the label when SDK returns a datetime object."""
        project = FakeProject(id="p1", name="Work -")
        task = make_task("t1", project_id="p1", order=0)
        task.due = FakeDue(date=datetime.now() + timedelta(days=365))

        (ids, labels, _), _ = self._run([project], [], [task], hide_future=14)

        assert self.LABEL not in task.labels
        assert ids == {"t1": 0}
        assert labels == {"t1": []}

    def test_relative_start_due_with_sdk_date_object_removes_child_labels(self, caplog):
        """start=due-* should understand SDK date objects and hide children until start."""
        project = FakeProject(id="p1", name="Work =")
        parent = make_task(
            "t1", content="Declarar IR start=due-0d", project_id="p1", order=0)
        parent.due = FakeDue(date=date.today() + timedelta(days=365))
        child = make_task(
            "c1", project_id="p1", parent_id="t1", order=0,
            labels=[self.LABEL])

        with caplog.at_level(logging.WARNING):
            (ids, labels, _), _ = self._run([project], [], [parent, child])

        assert self.LABEL not in parent.labels
        assert self.LABEL not in child.labels
        assert ids == {"t1": 0, "c1": -1}
        assert labels == {"t1": [], "c1": []}
        assert "Wrong start-date format" not in caplog.text

    def test_headered_tasks_skipped(self):
        """Tasks starting with '*' should not get the label."""
        project = FakeProject(id="p1", name="Work -")
        tasks = [
            make_task("t1", content="* Header", project_id="p1", order=0),
            make_task("t2", project_id="p1", order=1),
        ]
        (ids, labels, _), _ = self._run([project], [], tasks)

        assert self.LABEL not in tasks[0].labels
        assert self.LABEL in tasks[1].labels

    def test_no_suffix_no_labels(self):
        """Project without suffix: no tasks should be labeled."""
        project = FakeProject(id="p1", name="Work")
        tasks = [
            make_task("t1", project_id="p1", order=0),
            make_task("t2", project_id="p1", order=1),
        ]
        (ids, labels, _), _ = self._run([project], [], tasks)

        assert self.LABEL not in tasks[0].labels
        assert self.LABEL not in tasks[1].labels

    def test_inbox_skipped(self):
        """Inbox project should always be skipped."""
        project = FakeProject(id="p1", name="Inbox", is_inbox_project=True)
        tasks = [
            make_task("t1", project_id="p1", order=0),
        ]
        (ids, labels, _), _ = self._run([project], [], tasks)

        assert self.LABEL not in tasks[0].labels

    def test_sequential_with_subtasks(self):
        """Sequential project: parent with children - label cascades to first child."""
        project = FakeProject(id="p1", name="Work -")
        parent = make_task("t1", project_id="p1", order=0)
        child1 = make_task("c1", project_id="p1", parent_id="t1", order=0)
        child2 = make_task("c2", project_id="p1", parent_id="t1", order=1)
        tasks = [parent, child1, child2]

        (ids, labels, _), _ = self._run([project], [], tasks)

        # Parent gets labeled first, then propagates to first child
        assert self.LABEL in child1.labels
        assert self.LABEL not in child2.labels

    def test_parallel_with_subtasks(self):
        """Parallel project (ppp): parent labeled, then all children get label."""
        project = FakeProject(id="p1", name="Work =")
        parent = make_task("t1", project_id="p1", order=0)
        child1 = make_task("c1", project_id="p1", parent_id="t1", order=0)
        child2 = make_task("c2", project_id="p1", parent_id="t1", order=1)
        tasks = [parent, child1, child2]

        (ids, labels, _), _ = self._run([project], [], tasks)

        assert self.LABEL in child1.labels
        assert self.LABEL in child2.labels

    def test_section_sequential(self):
        """Section with '-' suffix controls task labeling within that section."""
        project = FakeProject(id="p1", name="Work ---")
        section = FakeSection(id="s1", name="Todo --", project_id="p1")
        tasks = [
            make_task("t1", project_id="p1", section_id="s1", order=0),
            make_task("t2", project_id="p1", section_id="s1", order=1),
        ]
        (ids, labels, _), _ = self._run([project], [section], tasks)

        assert self.LABEL in tasks[0].labels
        assert self.LABEL not in tasks[1].labels

    def test_all_projects_labels_unsuffixed_project(self):
        """--all_projects flag makes unsuffixed projects default to sequential."""
        project = FakeProject(id="p1", name="Work")
        tasks = [
            make_task("t1", project_id="p1", order=0),
            make_task("t2", project_id="p1", order=1),
        ]
        (ids, labels, _), _ = self._run([project], [], tasks, all_projects=True)

        assert self.LABEL in tasks[0].labels
        assert self.LABEL not in tasks[1].labels

    def test_task_level_sequential_suffix(self):
        """Task with '-' suffix: subtasks should be processed sequentially."""
        project = FakeProject(id="p1", name="Work ---")
        parent = make_task("t1", content="Parent -", project_id="p1", order=0)
        child1 = make_task("c1", project_id="p1", parent_id="t1", order=0)
        child2 = make_task("c2", project_id="p1", parent_id="t1", order=1)
        tasks = [parent, child1, child2]

        (ids, labels, _), _ = self._run([project], [], tasks)

        # The task-level '-' should make subtasks sequential
        assert self.LABEL in child1.labels
        assert self.LABEL not in child2.labels


# ---------------------------------------------------------------------------
# Group 6: TestParentIdHandling
# ---------------------------------------------------------------------------

class TestParentIdHandling:
    """Tests for parent_id coercion (lines 1050-1053) and comparison (line 1180)."""

    def test_none_parent_id_is_falsy(self):
        task = make_task("t1", parent_id=None)
        assert not task.parent_id

    def test_zero_parent_id_is_falsy(self):
        # After coercion at line 1052, parent_id becomes 0
        task = make_task("t1", parent_id=None)
        if not task.parent_id:
            task.parent_id = 0
        assert task.parent_id == 0

    def test_string_parent_id_is_truthy(self):
        task = make_task("t1", parent_id="12345")
        assert task.parent_id


# ---------------------------------------------------------------------------
# Group 7: TestSortingOrder
# ---------------------------------------------------------------------------

class TestSortingOrder:
    """Tests for task sorting behavior (lines 1059-1060)."""

    def test_parentless_sorted_before_children(self):
        """parent_id=0 is falsy -> maps to "" which sorts before string IDs."""
        tasks = [
            make_task("c1", parent_id="t1", order=0),
            make_task("t1", parent_id=0, order=0),
            make_task("c2", parent_id="t1", order=1),
        ]
        # Apply the same coercion as autodoist
        for t in tasks:
            if not t.parent_id:
                t.parent_id = 0

        sorted_tasks = sorted(tasks, key=lambda x: (
            x.parent_id if x.parent_id else "", x.order))

        assert sorted_tasks[0].id == "t1"  # parentless first

    def test_children_sorted_by_order(self):
        tasks = [
            make_task("c2", parent_id="t1", order=2),
            make_task("c1", parent_id="t1", order=0),
            make_task("c3", parent_id="t1", order=1),
        ]

        sorted_tasks = sorted(tasks, key=lambda x: (
            x.parent_id if x.parent_id else "", x.order))

        assert [t.id for t in sorted_tasks] == ["c1", "c3", "c2"]
