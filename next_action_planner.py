from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
import re


class SelectionStrategy(StrEnum):
    """How next-action labels are selected at one hierarchy level.

    Sequential labels only the first eligible item at that level. Parallel
    labels every eligible item at that level.
    """

    SEQUENTIAL = 's'
    PARALLEL = 'p'


@dataclass(frozen=True, slots=True)
class LabelStrategy:
    """Explicit next-action label strategy across project, section, and task levels."""

    project_selection: SelectionStrategy | None = None
    section_selection: SelectionStrategy | None = None
    task_selection: SelectionStrategy | None = None


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    next_action_label: str


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    id: str
    name: str
    order: int
    is_inbox_project: bool


@dataclass(frozen=True, slots=True)
class SectionSnapshot:
    id: str | None
    name: str | None
    project_id: str
    order: int
    is_collapsed: bool = False
    is_labeling_disabled: bool = False


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    id: str
    content: str
    project_id: str
    section_id: str | None
    parent_id: str | None
    labels: tuple[str, ...]
    order: int
    is_completed: bool = False
    due_date: date | None = None
    is_header: bool = False


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    projects: tuple[ProjectSnapshot, ...] = ()
    sections: tuple[SectionSnapshot, ...] = ()
    tasks: tuple[TaskSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class AutodoistMetadataSnapshot:
    project_strategies: Mapping[str, LabelStrategy | None] = field(default_factory=dict)
    section_strategies: Mapping[str, LabelStrategy | None] = field(default_factory=dict)
    task_strategies: Mapping[str, LabelStrategy | None] = field(default_factory=dict)
    task_parent_strategies: Mapping[str, SelectionStrategy | None] = field(default_factory=dict)


def _selection_for_suffix(args, suffix):
    if suffix == args.s_suffix:
        return SelectionStrategy.SEQUENTIAL
    if suffix == args.p_suffix:
        return SelectionStrategy.PARALLEL
    return None


def _strategy_from_selections(selections, num):
    expanded = list(selections)
    if len(expanded) < num:
        expanded.extend([expanded[-1]] * (num - len(expanded)))

    if num == 3:
        return LabelStrategy(
            project_selection=expanded[0],
            section_selection=expanded[1],
            task_selection=expanded[2],
        )
    if num == 2:
        return LabelStrategy(
            section_selection=expanded[0],
            task_selection=expanded[1],
        )
    if num == 1:
        return LabelStrategy(task_selection=expanded[0])
    return None


def legacy_type_to_label_strategy(legacy_type):
    if not legacy_type:
        return None

    padded_type = legacy_type
    if len(padded_type) == 2:
        padded_type = 'x' + padded_type
    elif len(padded_type) == 1:
        padded_type = 'xx' + padded_type

    def parse_selection(value):
        if value == SelectionStrategy.SEQUENTIAL.value:
            return SelectionStrategy.SEQUENTIAL
        if value == SelectionStrategy.PARALLEL.value:
            return SelectionStrategy.PARALLEL
        return None

    return LabelStrategy(
        project_selection=parse_selection(padded_type[0]),
        section_selection=parse_selection(padded_type[1]),
        task_selection=parse_selection(padded_type[2]),
    )


def label_strategy_to_legacy_type(strategy):
    if strategy is None:
        return None

    legacy_type = ''.join(
        selection.value if selection is not None else 'x'
        for selection in (
            strategy.project_selection,
            strategy.section_selection,
            strategy.task_selection,
        )
    )
    if legacy_type == 'xxx':
        return None
    return legacy_type


def parse_label_strategy(args, string, num):
    if string is None:
        return None
    if string == 'Inbox':
        return None

    suffix_chars = re.escape(args.s_suffix + args.p_suffix)
    regex = '[%s]{1,%s}$' % (suffix_chars, str(num))
    re_ind = re.search(regex, string)

    is_ignored_all_projects_project = (
        args.all_projects
        and num == 3
        and args.ignore_suffix
        and string.endswith("_ignore")
    )

    if is_ignored_all_projects_project and not re_ind:
        return None

    if args.all_projects and num == 3 and not re_ind:
        return LabelStrategy(
            project_selection=SelectionStrategy.SEQUENTIAL,
            section_selection=SelectionStrategy.SEQUENTIAL,
            task_selection=SelectionStrategy.SEQUENTIAL,
        )

    if not re_ind:
        return None

    selections = [
        _selection_for_suffix(args, suffix)
        for suffix in re_ind[0]
    ]
    selections = [selection for selection in selections if selection is not None]
    if not selections:
        return None

    return _strategy_from_selections(selections, num)
