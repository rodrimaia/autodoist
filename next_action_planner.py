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
    s_suffix: str = '-'
    p_suffix: str = '='
    inbox: str | None = None
    all_projects: bool = False
    ignore_suffix: bool = False


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


@dataclass(frozen=True, slots=True)
class LabelChange:
    task_id: str
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecordProjectStrategy:
    project_id: str
    strategy: LabelStrategy | None


@dataclass(frozen=True, slots=True)
class RecordSectionStrategy:
    section_id: str
    strategy: LabelStrategy | None


@dataclass(frozen=True, slots=True)
class RecordTaskStrategy:
    task_id: str
    strategy: LabelStrategy | None


@dataclass(frozen=True, slots=True)
class PlanningResult:
    label_changes: tuple[LabelChange, ...] = ()
    metadata_commands: tuple[object, ...] = ()


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


def plan_parentless_next_action_labels(workspace, config, metadata):
    projects_by_id = {project.id: project for project in workspace.projects}
    sections_by_project = _sections_by_project(workspace.sections)
    tasks_by_section = _tasks_by_project_section(workspace.tasks)

    project_strategies = {
        project.id: parse_label_strategy(config, project.name, 3)
        for project in workspace.projects
    }
    section_strategies = {
        section.id: parse_label_strategy(config, section.name, 2)
        for section in workspace.sections
        if section.id is not None
    }
    task_strategies = {
        task.id: parse_label_strategy(config, task.content, 1)
        for task in workspace.tasks
        if task.parent_id is None
    }

    label_changes = []
    metadata_commands = []
    metadata_commands.extend(
        _strategy_metadata_commands(project_strategies, metadata.project_strategies, RecordProjectStrategy)
    )
    metadata_commands.extend(
        _strategy_metadata_commands(section_strategies, metadata.section_strategies, RecordSectionStrategy)
    )
    metadata_commands.extend(
        _strategy_metadata_commands(task_strategies, metadata.task_strategies, RecordTaskStrategy)
    )

    for project in sorted(projects_by_id.values(), key=lambda item: item.order):
        if project.is_inbox_project:
            continue

        first_project_section_seen = False
        project_sections = _sections_for_project(
            project,
            sections_by_project.get(project.id, ()),
            tasks_by_section,
        )

        for section in sorted(project_sections, key=lambda item: item.order):
            section_tasks = sorted(
                tasks_by_section.get((project.id, section.id), ()),
                key=lambda item: item.order,
            )
            first_section_task_seen = False

            for task in section_tasks:
                if task.parent_id is not None:
                    continue
                if task.is_completed:
                    continue

                final_labels = _plan_parentless_task_labels(
                    task=task,
                    next_action_label=config.next_action_label,
                    dominant_strategy=_dominant_strategy(
                        task_strategies.get(task.id),
                        section_strategies.get(section.id),
                        project_strategies.get(project.id),
                    ),
                    section_labeling_disabled=section.is_labeling_disabled,
                    first_project_section_seen=first_project_section_seen,
                    first_section_task_seen=first_section_task_seen,
                )
                if final_labels != task.labels:
                    label_changes.append(LabelChange(task_id=task.id, labels=final_labels))

                if not section.is_labeling_disabled and not task.is_header:
                    first_section_task_seen = True

            if section_tasks:
                first_project_section_seen = True

    return PlanningResult(
        label_changes=tuple(label_changes),
        metadata_commands=tuple(metadata_commands),
    )


def _sections_by_project(sections):
    result = {}
    for section in sections:
        result.setdefault(section.project_id, []).append(section)
    return result


def _tasks_by_project_section(tasks):
    result = {}
    for task in tasks:
        result.setdefault((task.project_id, task.section_id), []).append(task)
    return result


def _sections_for_project(project, project_sections, tasks_by_section):
    sections = list(project_sections)
    has_none_section = any(section.id is None for section in sections)
    has_none_section_tasks = (project.id, None) in tasks_by_section
    if not has_none_section and (has_none_section_tasks or not sections):
        sections.insert(
            0,
            SectionSnapshot(
                id=None,
                name=None,
                project_id=project.id,
                order=0,
            ),
        )
    return tuple(sections)


def _strategy_metadata_commands(current_strategies, stored_strategies, command_type):
    return [
        command_type(item_id, strategy)
        for item_id, strategy in current_strategies.items()
        if stored_strategies.get(item_id) != strategy
    ]


def _dominant_strategy(task_strategy, section_strategy, project_strategy):
    if task_strategy is not None:
        return task_strategy
    if section_strategy is not None:
        return section_strategy
    return project_strategy


def _plan_parentless_task_labels(
    task,
    next_action_label,
    dominant_strategy,
    section_labeling_disabled,
    first_project_section_seen,
    first_section_task_seen,
):
    labels = tuple(task.labels)

    if task.is_header or section_labeling_disabled:
        return _without_label(labels, next_action_label)

    dominant_type = label_strategy_to_legacy_type(dominant_strategy)
    if dominant_type is None:
        return _without_label(labels, next_action_label)

    should_have_label = False
    should_remove_stale_label = False

    if dominant_type[0] == 's':
        if not first_project_section_seen:
            if dominant_type[1] == 's':
                should_have_label = not first_section_task_seen
                should_remove_stale_label = first_section_task_seen
            elif dominant_type[1] == 'p':
                should_have_label = True

    elif dominant_type[0] == 'p':
        if dominant_type[1] == 's':
            should_have_label = not first_section_task_seen
            should_remove_stale_label = first_section_task_seen
        elif dominant_type[1] == 'p':
            should_have_label = True

    if dominant_type[0] == 'x' and dominant_type[1] == 's':
        should_have_label = not first_section_task_seen
        should_remove_stale_label = first_section_task_seen
    elif dominant_type[0] == 'x' and dominant_type[1] == 'p':
        should_have_label = True

    if dominant_type[1] == 'x' and dominant_type[2] == 's':
        should_have_label = not first_section_task_seen
        should_remove_stale_label = first_section_task_seen
    elif dominant_type[1] == 'x' and dominant_type[2] == 'p':
        should_have_label = True

    if should_have_label:
        return _with_label(labels, next_action_label)
    if should_remove_stale_label:
        return _without_label(labels, next_action_label)
    return labels


def _with_label(labels, label):
    if label in labels:
        return labels
    return labels + (label,)


def _without_label(labels, label):
    return tuple(existing_label for existing_label in labels if existing_label != label)
