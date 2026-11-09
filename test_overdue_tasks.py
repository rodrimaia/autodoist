"""Rollover safety checks without making live Todoist changes."""
from datetime import date, datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from overdue_tasks import OverdueRescheduler

NOW = datetime(2026, 11, 8, 15, tzinfo=timezone.utc)


def task(value='2026-11-07', recurring=False, assignee=None, zone=None, **extra):
    due = SimpleNamespace(date=value, is_recurring=recurring, timezone=zone)
    return SimpleNamespace(id='t1', due=due, assignee_id=assignee, is_completed=False, **extra)


@pytest.fixture
def server(monkeypatch):
    commands = []
    calls = []

    def post(url, *, data, **kwargs):
        calls.append(data)
        response = Mock()
        if 'commands' in data:
            batch = json.loads(data['commands'])
            commands.extend(batch)
            response.json.return_value = {'sync_status': {c['uuid']: 'ok' for c in batch}}
        else:
            response.json.return_value = {'user': {'id': 'me', 'tz_info': {'timezone': 'America/Sao_Paulo'}}, 'sync_token': 'next'}
        return response

    monkeypatch.setattr('overdue_tasks.requests.post', post)
    return commands, calls


def test_moves_all_projects_and_subtasks_and_is_idempotent(server):
    commands, _ = server
    tasks = [task(project_id='inbox'), task(project_id='ignored', parent_id='parent')]
    tasks[1].id = 't2'
    rollover = OverdueRescheduler('fake')
    assert rollover.reschedule(tasks, NOW) == 2
    assert rollover.reschedule(tasks, NOW) == 0
    assert len(commands) == 2
    assert all(t.due.date == date(2026, 11, 8) for t in tasks)


@pytest.mark.parametrize('rule,lang', [
    ('every 3 days', 'en'), ('every 2 weeks', 'en'), ('every month', 'en'),
    ('a cada 3 dias', 'pt'), ('toda semana', 'pt'), ('todo mês', 'pt'),
    ('every day starting 7 Nov 2026', 'en'),
    ('todo dia começando em 7 de nov de 2026', 'pt'),
    ('every day until 7 Nov 2026', 'en'),
    ('todo dia até 7 de nov de 2026', 'pt'),
    ('a cada! 3 dias até 7 de nov de 2026', 'pt'),
    ('every day at 9am', 'en'), ('todo dia às 9h', 'pt'),
    ('a cada! 0 dias', 'pt'), ('every! 0 days', 'en'),
    ('every day', 'pt'), ('todo dia', 'en'),
    ('todo dia', 'pt_BR'), ('every day', None), (None, 'pt'),
])
def test_unverified_recurrence_is_never_written(server, caplog, rule, lang):
    t = task(recurring=True)
    t.due.string = rule
    t.due.lang = lang
    assert OverdueRescheduler('fake').reschedule([t], NOW) == 0
    assert not server[0]
    assert t.due.date == '2026-11-07'
    assert 'recurrence preservation is not verified' in caplog.text
    assert f'rule={rule!r}' in caplog.text
    assert f'lang={lang!r}' in caplog.text
    assert 'may change the original cadence or recurrence boundaries' in caplog.text


@pytest.mark.parametrize('rule,lang', [
    ('every Monday', 'en'), ('every day', 'en'), ('every! 3 days', 'en'),
    ('todo dia', 'pt'), ('toda segunda-feira', 'pt'), ('toda terça-feira', 'pt'),
    ('toda quarta-feira', 'pt'), ('toda quinta-feira', 'pt'), ('toda sexta-feira', 'pt'),
    ('todo sábado', 'pt'), ('todo domingo', 'pt'),
    ('a cada! dia', 'pt'), ('a cada! 1 dia', 'pt'), ('a cada! 3 dias', 'pt'),
    ('  TODO DIA  ', 'pt'),
])
def test_verified_recurrence_retains_complete_metadata(server, rule, lang):
    t = task(recurring=True)
    t.due.string = rule
    t.due.lang = lang
    assert OverdueRescheduler('fake').reschedule([t], NOW) == 1
    assert server[0][0]['args']['due'] == {
        'date': '2026-11-08', 'timezone': None, 'is_recurring': True,
        'string': rule, 'lang': lang}


def test_missing_recurrence_metadata_is_reported_as_unverified(server, caplog):
    t = task(recurring=True)
    assert OverdueRescheduler('fake').reschedule([t], NOW) == 0
    assert not server[0]
    assert 'recurrence preservation is not verified (rule=None, lang=None)' in caplog.text


@pytest.mark.parametrize('value', ['2026-11-08', '2026-11-08T09:00:00', '2026-11-09'])
def test_today_and_future_are_untouched(server, value):
    assert OverdueRescheduler('fake').reschedule([task(value)], NOW) == 0
    assert not server[0]


@pytest.mark.parametrize('value,zone,expected', [
    ('2026-11-07T09:00:00', None, '2026-11-08T09:00:00'),
    ('2026-11-07T14:00:00Z', 'America/New_York', '2026-11-08T14:00:00Z'),
    ('2026-10-30T13:00:00Z', 'America/New_York', '2026-11-08T14:00:00Z'),
])
def test_times_and_timezone_preserved_including_dst(server, value, zone, expected):
    t = task(value, zone=zone)
    assert OverdueRescheduler('fake').reschedule([t], NOW) == 1
    due = server[0][0]['args']['due']
    assert due == {'date': expected, 'timezone': zone, 'is_recurring': False}


def test_skips_nonexistent_and_ambiguous_dst_times(server):
    rollover = OverdueRescheduler('fake')
    assert rollover.reschedule([task('2026-10-30T05:30:00Z', zone='America/New_York')],
                               datetime(2026, 11, 1, 16, tzinfo=timezone.utc)) == 0
    assert rollover.reschedule([task('2026-03-07T07:30:00Z', zone='America/New_York')],
                               datetime(2026, 3, 8, 16, tzinfo=timezone.utc)) == 0
    assert not server[0]


def test_ownership_completion_and_no_due(server):
    tasks = [task(assignee='other'), task(), task()]
    tasks[1].is_completed = True
    tasks[2].due = None
    assert OverdueRescheduler('fake').reschedule(tasks, NOW) == 0
    assert OverdueRescheduler('fake').reschedule([task(assignee='me')], NOW) == 1


@pytest.mark.parametrize('end,hour,expected', [(4, 6, '2026-11-07'), (4, 7, '2026-11-08'), (24, 15, '2026-11-07')])
def test_account_timezone_and_shifted_day(server, end, hour, expected):
    now = NOW.replace(hour=hour)
    assert OverdueRescheduler('fake', end).reschedule([task('2026-11-06')], now) == 1
    assert server[0][0]['args']['due']['date'] == expected


def test_batches_and_incremental_account_sync(server):
    tasks = [task() for _ in range(101)]
    rollover = OverdueRescheduler('fake')
    assert rollover.reschedule(tasks, NOW) == 101
    assert rollover.reschedule([], NOW) == 0
    calls = server[1]
    assert calls[0]['sync_token'] == '*'
    assert len(json.loads(calls[1]['commands'])) == 100
    assert len(json.loads(calls[2]['commands'])) == 1
    assert calls[3]['sync_token'] == 'next'


def test_network_failure_leaves_tasks_unchanged(monkeypatch):
    monkeypatch.setattr('overdue_tasks.requests.post', Mock(side_effect=requests.Timeout))
    t = task()
    assert OverdueRescheduler('fake').reschedule([t], NOW) == 0
    assert t.due.date == '2026-11-07'


def test_unconfirmed_command_is_not_counted(monkeypatch, server):
    original = requests.post

    def failed_write(url, *, data, **kwargs):
        if 'commands' in data:
            return Mock(json=lambda: {'sync_status': {}})
        return original(url, data=data, **kwargs)

    monkeypatch.setattr('overdue_tasks.requests.post', failed_write)
    t = task()
    assert OverdueRescheduler('fake').reschedule([t], NOW) == 0
    assert t.due.date == '2026-11-07'
