"""Conservative overdue rollover; recurring tasks require completion verification."""

from datetime import date, datetime, timedelta, timezone
import json
import logging
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests


def verified_recurrence(due):
    """Only rules whose future dates do not depend on the moved occurrence."""
    if getattr(due, "lang", None) != "en":
        return False
    rule = due.string.strip().lower()
    return re.fullmatch(
        r"every (?:day|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
        r"every! (?:[1-9][0-9]* )?days?", rule) is not None


class OverdueRescheduler:
    def __init__(self, token, end=None):
        self.headers = {"Authorization": f"Bearer {token}"}
        self.end = end or 0
        self.user = None
        self.sync_token = "*"

    def reschedule(self, tasks, now=None):
        try:
            response = requests.post(
                "https://api.todoist.com/api/v1/sync", headers=self.headers,
                data={"sync_token": self.sync_token, "resource_types": '["user"]'}, timeout=20)
            response.raise_for_status()
            account = response.json()
            if account.get("user"):
                self.user = account["user"]
            self.sync_token = account["sync_token"]
            account_zone = ZoneInfo(self.user["tz_info"]["timezone"])
            user_id = str(self.user["id"])
            local_now = (now or datetime.now(timezone.utc)).astimezone(account_zone)
            today = local_now.date()
            if local_now.hour < self.end:
                today -= timedelta(days=1)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            logging.warning("Overdue rollover skipped: could not read account timezone and identity.")
            return 0

        pending = []
        for task in tasks:
            if task.is_completed or task.due is None:
                continue
            if task.assignee_id is not None and str(task.assignee_id) != user_id:
                continue
            try:
                original = task.due.date
                if isinstance(original, str):
                    original = (datetime.fromisoformat(original.replace("Z", "+00:00"))
                                if "T" in original else date.fromisoformat(original))
                timed = isinstance(original, datetime)
                task_zone = ZoneInfo(task.due.timezone) if getattr(task.due, "timezone", None) else account_zone
                local_due = original.astimezone(task_zone) if timed and original.tzinfo else original
                due_day = local_due.date() if timed else local_due
                if due_day >= today:
                    continue
                # Fixed intervals can lose their original cadence even when the repeat text survives.
                if task.due.is_recurring and not verified_recurrence(task.due):
                    logging.warning("Overdue task %s unchanged: recurrence preservation is not verified.", task.id)
                    continue
                if timed:
                    moved = local_due.replace(year=today.year, month=today.month, day=today.day)
                    if moved.tzinfo:
                        # Reject nonexistent/ambiguous wall times rather than changing the user's time.
                        alternate = moved.replace(fold=1 - moved.fold)
                        if (alternate.utcoffset() != moved.utcoffset() or
                                moved.astimezone(timezone.utc).astimezone(task_zone).replace(tzinfo=None) != moved.replace(tzinfo=None)):
                            raise ValueError("ambiguous or nonexistent time")
                        moved = moved.astimezone(timezone.utc)
                else:
                    moved = today
                due = {"date": moved.isoformat().replace("+00:00", "Z"), "timezone": getattr(task.due, "timezone", None),
                       "is_recurring": False}
                if task.due.is_recurring:
                    due.update(string=task.due.string, lang=task.due.lang, is_recurring=True)
                command = {"type": "item_update", "uuid": str(uuid4()),
                           "args": {"id": task.id, "due": due}}
                pending.append((command, task, moved))
            except (ValueError, TypeError, KeyError, AttributeError):
                logging.warning("Overdue task %s unchanged: date cannot be safely moved.", task.id)

        count = 0
        for start in range(0, len(pending), 100):
            batch = pending[start:start + 100]
            try:
                response = requests.post(
                    "https://api.todoist.com/api/v1/sync", headers=self.headers,
                    data={"commands": json.dumps([entry[0] for entry in batch])}, timeout=20)
                response.raise_for_status()
                statuses = response.json()["sync_status"]
                for command, task, moved in batch:
                    if statuses.get(command["uuid"]) == "ok":
                        task.due.date = moved
                        count += 1
                    else:
                        logging.warning("Overdue rollover not confirmed for task %s.", task.id)
            except (requests.RequestException, ValueError, KeyError, TypeError):
                logging.warning("Overdue rollover batch not confirmed; tasks will be re-read next sync.")
        return count
