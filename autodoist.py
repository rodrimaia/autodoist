#!/usr/bin/python3

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task
from todoist_api_python.models import Section
from todoist_api_python.models import Project
from urllib.parse import urljoin
from urllib.parse import quote
import sys
import time
import requests
import argparse
import logging
from datetime import datetime, timedelta
import time
import sqlite3
import os
import re
import json

# Connect to SQLite database


def create_connection(path):
    connection = None
    try:
        connection = sqlite3.connect(path)
        logging.debug("Connection to SQLite DB successful!")
    except Exception as e:
        logging.error(
            f"Could not connect to the SQLite database: the error '{e}' occurred")
        sys.exit(1)

    return connection

# Close conenction to SQLite database


def close_connection(connection):
    try:
        connection.close()
    except Exception as e:
        logging.error(
            f"Could not close the SQLite database: the error '{e}' occurred")
        sys.exit(1)

# Execute any SQLite query passed to it in the form of string


def execute_query(connection, query, *args):
    cursor = connection.cursor()
    try:
        value = args[0]
        # Useful to pass None/NULL value correctly
        cursor.execute(query, (value,))
    except:
        cursor.execute(query)

    try:
        connection.commit()
        logging.debug("Query executed: {}".format(query))
    except Exception as e:
        logging.debug(f"The error '{e}' occurred")

# Pass query to select and read record. Outputs a tuple.


def execute_read_query(connection, query):
    cursor = connection.cursor()
    result = None
    try:
        cursor.execute(query)
        result = cursor.fetchall()
        logging.debug("Query fetched: {}".format(query))
        return result
    except Exception as e:
        logging.debug(f"The error '{e}' occurred")

# Construct query and read a value


def db_read_value(connection, model, column):
    try:
        if isinstance(model, Task):
            db_name = 'tasks'
            goal = 'task_id'
        elif isinstance(model, Section):
            db_name = 'sections'
            goal = 'section_id'
        elif isinstance(model, Project):
            db_name = 'projects'
            goal = 'project_id'

        query = "SELECT %s FROM %s where %s=%r" % (
            column, db_name, goal, model.id)

        result = execute_read_query(connection, query)

    except Exception as e:
        logging.debug(f"The error '{e}' occurred")

    return result

# Construct query and update a value


def db_update_value(connection, model, column, value):

    try:
        if isinstance(model, Task):
            db_name = 'tasks'
            goal = 'task_id'

        elif isinstance(model, Section):
            db_name = 'sections'
            goal = 'section_id'

        elif isinstance(model, Project):
            db_name = 'projects'
            goal = 'project_id'

        query = """UPDATE %s SET %s = ? WHERE %s = %r""" % (
            db_name, column, goal, model.id)

        result = execute_query(connection, query, value)

        return result

    except Exception as e:
        logging.debug(f"The error '{e}' occurred")


# Check if the id of a model exists, if not, add to database


def db_check_existance(connection, model):
    try:
        if isinstance(model, Task):
            db_name = 'tasks'
            goal = 'task_id'
        elif isinstance(model, Section):
            db_name = 'sections'
            goal = 'section_id'
        elif isinstance(model, Project):
            db_name = 'projects'
            goal = 'project_id'

        q_check_existence = "SELECT EXISTS(SELECT 1 FROM %s WHERE %s=%r)" % (
            db_name, goal, model.id)
        existence_result = execute_read_query(connection, q_check_existence)

        if existence_result[0][0] == 0:
            if isinstance(model, Task):
                q_create = """
                INSERT INTO
                tasks (task_id, task_type, parent_type, due_date, r_tag)
                VALUES
                (%r, %s, %s, %s, %i);
                """ % (model.id, 'NULL', 'NULL', 'NULL', 0)

            if isinstance(model, Section):
                q_create = """
                INSERT INTO
                sections (section_id, section_type)
                VALUES
                (%r, %s);
                """ % (model.id, 'NULL')

            if isinstance(model, Project):
                q_create = """
                INSERT INTO
                projects (project_id, project_type)
                VALUES
                (%r, %s);
                """ % (model.id, 'NULL')

            execute_query(connection, q_create)

    except Exception as e:
        logging.debug(f"The error '{e}' occurred")


# Initialise new database tables

def initialise_sqlite():

    cwd = os.getcwdb()
    db_path = os.path.join(cwd, b'metadata.sqlite')

    connection = create_connection(db_path)

    q_create_projects_table = """
    CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    project_type TEXT
    );
    """

    q_create_sections_table = """
    CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER,
    section_type
    );
    """

    q_create_tasks_table = """
    CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    task_type TEXT,
    parent_type TEXT,
    due_date TEXT,
    r_tag INTEGER
    );
    """

    execute_query(connection, q_create_projects_table)
    execute_query(connection, q_create_sections_table)
    execute_query(connection, q_create_tasks_table)

    logging.info("SQLite DB has successfully initialized! \n")

    return connection


# Makes --help text wider


def make_wide(formatter, w=120, h=36):
    """Return a wider HelpFormatter, if possible."""
    try:
        # https://stackoverflow.com/a/5464440
        # beware: "Only the name of this class is considered a public API."
        kwargs = {'width': w, 'max_help_position': h}
        formatter(None, **kwargs)
        return lambda prog: formatter(prog, **kwargs)
    except TypeError:
        logging.error("Argparse help formatter failed, falling back.")
        return formatter

# Simple query for yes/no answer


def query_yes_no(question, default="yes"):
    # """Ask a yes/no question via raw_input() and return their answer.

    # "question" is a string that is presented to the user.
    # "default" is the presumed answer if the user just hits <Enter>.
    #     It must be "yes" (the default), "no" or None (meaning
    #     an answer is required of the user).

    # The "answer" return value is True for "yes" or False for "no".
    # """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")

# Check if label exists, if not, create it


def verify_label_existance(api, label_name, prompt_mode):
    # Check the regeneration label exists
    # In API v3, get_labels() returns a paginator that yields pages (lists)
    labels = [label for page in api.get_labels() for label in page]
    label = [x for x in labels if x.name == label_name]

    if len(label) > 0:
        next_action_label = label[0].id
        logging.debug('Label \'%s\' found as label id %s',
                      label_name, next_action_label)
    else:
        # Create a new label in Todoist
        logging.info(
            "\n\nLabel '{}' doesn't exist in your Todoist\n".format(label_name))
        # sys.exit(1)
        if prompt_mode == 1:
            response = query_yes_no(
                'Do you want to automatically create this label?')
        else:
            response = True

        if response:
            try:
                api.add_label(name=label_name)
            except Exception as error:
                logging.warning(error)

            # In API v3, get_labels() returns a paginator
            labels = [label for page in api.get_labels() for label in page]
            label = [x for x in labels if x.name == label_name]
            next_action_label = label[0].id

            logging.info("Label '{}' has been created!".format(label_name))
        else:
            logging.info('Exiting Autodoist.')
            exit(1)

    return labels

# Initialisation of Autodoist


def initialise_api(args):

    # Check we have a API key
    if not args.api_key:
        logging.error(
            "\n\nNo API key set. Run Autodoist with '-a <YOUR_API_KEY>' or set the environment variable TODOIST_API_KEY.\n")
        sys.exit(1)

    # Check if alternative end of day is used
    if args.end is not None:
        if args.end < 1 or args.end > 24:
            logging.error(
                "\n\nPlease choose a number from 1 to 24 to indicate which hour is used as alternative end-of-day time.\n")
            sys.exit(1)
    else:
        pass

    # Check if proper regeneration mode has been selected
    if args.regeneration is not None:
        if not set([0, 1, 2]) & set([args.regeneration]):
            logging.error(
                'Wrong regeneration mode. Please choose a number from 0 to 2. Check --help for more information on the available modes.')
            exit(1)

    # Show which modes are enabled:
    modes = []
    m_num = 0
    for x in [args.label, args.regeneration, args.end]:
        if x:
            modes.append('Enabled')
            m_num += 1
        else:
            modes.append('Disabled')

    logging.info("You are running with the following functionalities:\n\n   Next action labelling mode: {}\n   Regenerate sub-tasks mode: {}\n   Shifted end-of-day mode: {}\n".format(*modes))

    if m_num == 0:
        logging.info(
            "\n No functionality has been enabled. Please see --help for the available options.\n")
        exit(0)

    # Run the initial sync
    logging.debug('Connecting to the Todoist API')
    try:
        api_arguments = {'token': args.api_key}
        api = TodoistAPI(**api_arguments)
        sync_api = initialise_sync_api(api)
        # Save SYNC API token to enable partial syncs
        api.sync_token = sync_api['sync_token']

    except Exception as e:
        logging.error(
            f"Could not connect to Todoist: '{e}'")
        exit(0)

    logging.info("Autodoist has successfully connected to Todoist!")

    # Check if labels exist

    # If labeling argument is used
    if args.label is not None:

        # Verify that the next action label exists; ask user if it needs to be created
        verify_label_existance(api, args.label, 1)

    # TODO: Disabled for now
    # # If regeneration mode is used, verify labels
    # if args.regeneration is not None:

    #     # Verify the existance of the regeneraton labels; force creation of label
    #     regen_labels_id = [verify_label_existance(
    #         api, regen_label, 2) for regen_label in args.regen_label_names]

    # else:
    #     # Label functionality not needed
    #     regen_labels_id = [None, None, None]

    return api

# Check for Autodoist update


def check_for_update(current_version):
    updateurl = 'https://api.github.com/repos/Hoffelhas/autodoist/releases'

    try:
        r = requests.get(updateurl)
        r.raise_for_status()
        release_info_json = r.json()

        if not current_version == release_info_json[0]['tag_name']:
            logging.warning("\n\nYour version is not up-to-date! \nYour version: {}. Latest version: {}\nFind the latest version at: {}\n".format(
                current_version, release_info_json[0]['tag_name'], release_info_json[0]['html_url']))
            return 1
        else:
            return 0
    except requests.exceptions.ConnectionError as e:
        logging.error(
            "Error while checking for updates (Connection error): {}".format(e))
        return 1
    except requests.exceptions.HTTPError as e:
        logging.error(
            "Error while checking for updates (HTTP error): {}".format(e))
        return 1
    except requests.exceptions.RequestException as e:
        logging.error("Error while checking for updates: {}".format(e))
        return 1

# Get all data through the SYNC API. Needed to see e.g. any completed tasks.


def get_all_data(api):
    BASE_URL = "https://api.todoist.com"
    SYNC_VERSION = "v9"
    SYNC_API = urljoin(BASE_URL, f"/sync/{SYNC_VERSION}/")
    COMPLETED_GET_ALL = "completed/get_all"
    endpoint = urljoin(SYNC_API, COMPLETED_GET_ALL)
    data = get(api._session, endpoint, api._token)

    return data


def initialise_sync_api(api):
    bearer_token = 'Bearer %s' % api._token

    headers = {
        'Authorization': bearer_token,
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = 'sync_token=*&resource_types=["all"]'

    try:
        response = requests.post(
            'https://api.todoist.com/api/v1/sync', headers=headers, data=data)

        # Check status code before parsing JSON
        if response.status_code == 200:
            return response.json()

        # Log error details for debugging
        logging.error(f"Sync API error {response.status_code}: {response.text[:200]}")
        response.raise_for_status()

    except Exception as e:
        logging.error(f"Error during initialise_sync_api: '{e}'")
        raise

# Commit task content change to queue


def commit_content_update(api, task_id, content):
    uuid = str(time.perf_counter())  # Create unique request id
    data = {"type": "item_update", "uuid": uuid,
            "args": {"id": task_id, "content": quote(content)}}
    api.queue.append(data)

    return api

# Ensure label updates are only issued once per task and commit to queue


def commit_labels_update(api, overview_task_ids, overview_task_labels):

    filtered_overview_ids = [
        k for k, v in overview_task_ids.items() if v != 0]

    for task_id in filtered_overview_ids:
        labels = overview_task_labels[task_id]

        # api.update_task(task_id=task_id, labels=labels) # Not using REST API, since we would get too many single requests
        uuid = str(time.perf_counter())  # Create unique request id
        data = {"type": "item_update", "uuid": uuid,
                "args": {"id": task_id, "labels": labels}}
        api.queue.append(data)

    return api


# Update tasks in batch with Todoist Sync API


def sync(api):
    # # This approach does not seem to work correctly.
    # BASE_URL = "https://api.todoist.com"
    # SYNC_VERSION = "v9"
    # SYNC_API = urljoin(BASE_URL, f"/sync/{SYNC_VERSION}/")
    # SYNC_ENDPOINT = "sync"
    # endpoint = urljoin(SYNC_API, SYNC_ENDPOINT)
    # task_data = post(api._session, endpoint, api._token, data=data)

    try:
        bearer_token = 'Bearer %s' % api._token

        headers = {
            'Authorization': bearer_token,
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        data = 'sync_token=' + api.sync_token + \
            '&commands=' + json.dumps(api.queue)

        response = requests.post(
            'https://api.todoist.com/api/v1/sync', headers=headers, data=data)

        if response.status_code == 200:
            return response.json()

        # Log error details for debugging
        logging.error(f"Sync API error {response.status_code}: {response.text[:200]}")
        response.raise_for_status()
        return response.ok

    except Exception as e:
        logging.exception(
            'Error trying to sync with Todoist API: %s' % str(e))
        quit()

# Find the type based on name suffix.


def check_name(args, string, num):

    try:
        # Find inbox or none section as exceptions
        if string == None:
            current_type = None
            pass
        elif string == 'Inbox':
            current_type = args.inbox
            pass
        else:
            # Find any = or - symbol at the end of the string. Look at last 3 for projects, 2 for sections, and 1 for tasks
            regex = '[%s%s]{1,%s}$' % (args.s_suffix, args.p_suffix, str(num))
            re_ind = re.search(regex, string)
            suffix = re_ind[0]

            # Somebody put fewer characters than intended. Take last character and apply for every missing one.
            if len(suffix) < num:
                suffix += suffix[-1] * (num - len(suffix))

            current_type = ''
            for s in suffix:
                if s == args.s_suffix:
                    current_type += 's'
                elif s == args.p_suffix:
                    current_type += 'p'

        # Always return a three letter string
        if len(current_type) == 2:
            current_type = 'x' + current_type
        elif len(current_type) == 1:
            current_type = 'xx' + current_type

    except:
        logging.debug("String {} not recognised.".format(string))
        current_type = None

    return current_type

# Scan the end of a name to find what type it is


def get_type(args, connection, model, key):

    # model_name = ''

    try:
        old_type = ''
        old_type = db_read_value(connection, model, key)[0][0]

    except:
        # logging.debug('No defined project_type: %s' % str(e))
        old_type = None

    if isinstance(model, Task):
        current_type = check_name(args, model.content, 1)  # Tasks
    elif isinstance(model, Section):
        current_type = check_name(args, model.name, 2)  # Sections
    elif isinstance(model, Project):
        current_type = check_name(args, model.name, 3)  # Projects

    # Check if type changed with respect to previous run
    if old_type == current_type:
        type_changed = 0
    else:
        type_changed = 1
        db_update_value(connection, model, key, current_type)

    return current_type, type_changed

# Determine a project type


def get_project_type(args, connection, project):
    """Identifies how a project should be handled."""
    project_type, project_type_changed = get_type(
        args, connection, project, 'project_type')

    if project_type is not None:
        logging.debug('Identified \'%s\' as %s type',
                      project.name, project_type)

    return project_type, project_type_changed

# Determine a section type


def get_section_type(args, connection, section, project):
    """Identifies how a section should be handled."""
    if section is not None:
        section_type, section_type_changed = get_type(
            args, connection, section, 'section_type')
    else:
        section_type = None
        section_type_changed = 0

    if section_type is not None:
        logging.debug("Identified '%s > %s' as %s type",
                      project.name, section.name, section_type)

    return section_type, section_type_changed

# Determine an task type


def get_task_type(args, connection, task, section, project):
    """Identifies how a task with sub tasks should be handled."""

    task_type, task_type_changed = get_type(
        args, connection, task, 'task_type')

    if task_type is not None:
        logging.debug("Identified '%s > %s > %s' as %s type",
                      project.name, section.name, task.content, task_type)

    return task_type, task_type_changed

# Logic to track addition of a label to a task


def add_label(task, label, overview_task_ids, overview_task_labels):
    if label not in task.labels:
        labels = task.labels  # To also copy other existing labels
        logging.debug('Updating \'%s\' with label', task.content)
        labels.append(label)

        try:
            overview_task_ids[task.id] += 1
        except:
            overview_task_ids[task.id] = 1
        overview_task_labels[task.id] = labels

# Logic to track removal of a label from a task


def remove_label(task, label, overview_task_ids, overview_task_labels):
    if label in task.labels:
        labels = task.labels
        logging.debug('Removing \'%s\' of its label', task.content)
        labels.remove(label)

        try:
            overview_task_ids[task.id] -= 1
        except:
            overview_task_ids[task.id] = -1
        overview_task_labels[task.id] = labels


# Check if header logic needs to be applied


def check_header(api, model):
    header_all_in_level = False
    unheader_all_in_level = False
    regex_a = r'(^[*]{2}\s*)(.*)'
    regex_b = r'(^\-\*\s*)(.*)'

    try:
        if isinstance(model, Task):
            ra = re.search(regex_a, model.content)
            rb = re.search(regex_b, model.content)

            if ra:
                header_all_in_level = True
                model.content = ra[2]  # Local record
                api.update_task(task_id=model.id, content=ra[2])
                # overview_updated_ids.append(model.id) # Ignore this one, since else it's count double
            if rb:
                unheader_all_in_level = True
                model.content = rb[2]  # Local record
                api.update_task(task_id=model.id, content=rb[2])
                # overview_updated_ids.append(model.id)
        else:
            ra = re.search(regex_a, model.name)
            rb = re.search(regex_b, model.name)

            if isinstance(model, Section):
                if ra:
                    header_all_in_level = True
                    api.update_section(section_id=model.id, name=ra[2])
                    api.overview_updated_ids.append(model.id)
                if rb:
                    unheader_all_in_level = True
                    api.update_section(section_id=model.id, name=rb[2])
                    api.overview_updated_ids.append(model.id)

            elif isinstance(model, Project):
                if ra:
                    header_all_in_level = True
                    api.update_project(project_id=model.id, name=ra[2])
                    api.overview_updated_ids.append(model.id)
                if rb:
                    unheader_all_in_level = True
                    api.update_project(project_id=model.id, name=rb[2])
                    api.overview_updated_ids.append(model.id)
    except:
        logging.debug('check_header: no right model found')

    return api, header_all_in_level, unheader_all_in_level

# Logic for applying and removing headers


def modify_task_headers(api, task, section_tasks, header_all_in_p, unheader_all_in_p, header_all_in_s, unheader_all_in_s, header_all_in_t, unheader_all_in_t):

    if any([header_all_in_p, header_all_in_s]):
        if task.content[:2] != '* ':
            content = '* ' + task.content
            api = commit_content_update(api, task.id, content)
            # api.update_task(task_id=task.id, content='* ' + task.content)
            # overview_updated_ids.append(task.id)

    if any([unheader_all_in_p, unheader_all_in_s]):
        if task.content[:2] == '* ':
            content = task.content[2:]
            api = commit_content_update(api, task.id, content)
            # api.update_task(task_id=task.id, content=task.content[2:])
            # overview_updated_ids.append(task.id)

    if header_all_in_t:
        if task.content[:2] != '* ':
            content = '* ' + task.content
            api = commit_content_update(api, task.id, content)
            # api.update_task(task_id=task.id, content='* ' + task.content)
            # overview_updated_ids.append(task.id)
        api = find_and_headerify_all_children(
            api, task, section_tasks, 1)

    if unheader_all_in_t:
        if task.content[:2] == '* ':
            content = task.content[2:]
            api = commit_content_update(api, task.id, content)
            # api.update_task(task_id=task.id, content=task.content[2:])
            # overview_updated_ids.append(task.id)
        api = find_and_headerify_all_children(
            api, task, section_tasks, 2)

    return api


# Check regen mode based on label name


def check_regen_mode(api, item, regen_labels_id):

    labels = item.labels

    overlap = set(labels) & set(regen_labels_id)
    overlap = [val for val in overlap]

    if len(overlap) > 1:
        logging.warning(
            'Multiple regeneration labels used! Please pick only one for item: "{}".'.format(item.content))
        return None

    try:
        regen_next_action_label = overlap[0]
    except:
        logging.debug(
            'No regeneration label for item: %s' % item.content)
        regen_next_action_label = [0]

    if regen_next_action_label == regen_labels_id[0]:
        return 0
    elif regen_next_action_label == regen_labels_id[1]:
        return 1
    elif regen_next_action_label == regen_labels_id[2]:
        return 2
    else:
        # label_name = api.labels.get_by_id(regen_next_action_label)['name']
        # logging.debug(
        # 'No regeneration label for item: %s' % item.content)
        return None


# Recurring lists logic


def run_recurring_lists_logic(args, api, connection, task, task_items, task_items_all, regen_labels_id):

    if task.parent_id == 0:
        try:
            if task.due.is_recurring:
                try:
                    db_task_due_date = db_read_value(
                        connection, task, 'due_date')[0][0]

                    if db_task_due_date is None:
                        # If date has never been saved before, create a new entry
                        logging.debug(
                            'New recurring task detected: %s' % task.content)
                        db_update_value(connection, task,
                                        'due_date', task.due.date)

                    # Check if the T0 task date has changed, because a user has checked the task
                    if task.due.date != db_task_due_date:

                        # TODO: reevaluate regeneration mode. Disabled for now.
                        # # Mark children for action based on mode
                        # if args.regeneration is not None:

                        #     # Check if task has a regen label
                        #     regen_mode = check_regen_mode(
                        #         api, item, regen_labels_id)

                        #     # If no label, use general mode instead
                        #     if regen_mode is None:
                        #         regen_mode = args.regeneration
                        #         logging.debug('Using general recurring mode \'%s\' for item: %s',
                        #                       regen_mode, item.content)
                        #     else:
                        #         logging.debug('Using recurring label \'%s\' for item: %s',
                        #                       regen_mode, item.content)

                        #     # Apply tags based on mode
                        #     give_regen_tag = 0

                        #     if regen_mode == 1:  # Regen all
                        #         give_regen_tag = 1
                        #     elif regen_mode == 2:  # Regen if all sub-tasks completed
                        #         if not child_items:
                        #             give_regen_tag = 1

                        #     if give_regen_tag == 1:
                        #         for child_item in child_items_all:
                        #             child_item['r_tag'] = 1

                        # If alternative end of day, fix due date if needed
                        if args.end is not None:
                            # Determine current hour
                            t = datetime.today()
                            current_hour = t.hour

                            # Check if current time is before our end-of-day
                            if (args.end - current_hour) > 0:

                                # Determine the difference in days set by todoist
                                nd = [int(x) for x in task.due.date.split('-')]
                                od = [int(x)
                                      for x in db_task_due_date.split('-')]

                                new_date = datetime(
                                    nd[0], nd[1], nd[2])
                                old_date = datetime(
                                    od[0], od[1], od[2])
                                today = datetime(
                                    t.year, t.month, t.day)
                                days_difference = (
                                    new_date-today).days
                                days_overdue = (
                                    today - old_date).days

                                # Only apply if overdue and if it's a daily recurring tasks
                                if days_overdue >= 1 and days_difference == 1:

                                    # Find current date in string format
                                    today_str = t.strftime("%Y-%m-%d")

                                    # Update due-date to today
                                    api.update_task(
                                        task_id=task.id, due_date=today_str, due_string=task.due.string)
                                    logging.debug(
                                        "Update date on task: '%s'" % (task.content))

                        # Save the new date for reference us
                        db_update_value(connection, task,
                                        'due_date', task.due.date)

                except:
                    # If date has never been saved before, create a new entry
                    logging.debug(
                        'New recurring task detected: %s' % task.content)
                    db_update_value(connection, task,
                                    'due_date', task.due.date)

        except:
            pass

    # TODO: reevaluate regeneration mode. Disabled for now.
    # if args.regeneration is not None and item.parent_id != 0:
    #     try:
    #         if item['r_tag'] == 1:
    #             item.update(checked=0)
    #             item.update(in_history=0)
    #             item['r_tag'] = 0
    #             api.items.update(item['id'])

    #             for child_item in child_items_all:
    #                 child_item['r_tag'] = 1
    #     except:
    #         # logging.debug('Child not recurring: %s' %
    #         #               item.content)
    #         pass

# Find and clean all children under a task


def find_and_clean_all_children(task_ids, task, section_tasks):

    child_tasks = list(filter(lambda x: x.parent_id == task.id, section_tasks))

    if child_tasks != []:
        for child_task in child_tasks:
            # Children found, go deeper
            task_ids.append(child_task.id)
            task_ids = find_and_clean_all_children(
                task_ids, child_task, section_tasks)

    return task_ids


def find_and_headerify_all_children(api, task, section_tasks, mode):

    child_tasks = list(filter(lambda x: x.parent_id == task.id, section_tasks))

    if child_tasks != []:
        for child_task in child_tasks:
            # Children found, go deeper
            if mode == 1:
                if child_task.content[:2] != '* ':
                    api = commit_content_update(
                        api, child_task.id, '* ' + child_task.content)
                    # api.update_task(task_id=child_task.id,
                    # content='* ' + child_task.content)
                    # overview_updated_ids.append(child_task.id)

            elif mode == 2:
                if child_task.content[:2] == '* ':
                    api = commit_content_update(
                        api, child_task.id, child_task.content[2:])
                    # api.update_task(task_id=child_task.id,
                    #                 content=child_task.content[2:])
                    # overview_updated_ids.append(child_task.id)

            find_and_headerify_all_children(
                api, child_task, section_tasks, mode)

    return 0

# Contains all main autodoist functionalities


def autodoist_magic(args, api, connection):

    # Preallocate dictionaries and other values
    overview_task_ids = {}
    overview_task_labels = {}
    next_action_label = args.label
    regen_labels_id = args.regen_label_names
    first_found = [False, False, False]
    api.queue = []
    api.overview_updated_ids = []

    # Get all todoist info
    try:
        # In API v3, get_*() methods return paginators that yield pages (lists)
        all_projects = [item for page in api.get_projects() for item in page]
        all_sections = [item for page in api.get_sections() for item in page]
        all_tasks = [item for page in api.get_tasks() for item in page]

    except Exception as error:
        logging.error(error)

    for project in all_projects:

        # Skip processing inbox as intended feature
        if project.is_inbox_project:
            continue

        # Check db existance
        db_check_existance(connection, project)

        # Check if we need to (un)header entire project
        api, header_all_in_p, unheader_all_in_p = check_header(
            api, project)

        # Get project type
        if next_action_label is not None:
            project_type, project_type_changed = get_project_type(
                args, connection, project)
        else:
            project_type = None
            project_type_changed = 0

        # Get all tasks for the project
        try:
            project_tasks = [
                t for t in all_tasks if t.project_id == project.id]
        except Exception as error:
            logging.warning(error)

        # If a project type has changed, clean all tasks in this project for good measure
        if next_action_label is not None:
            if project_type_changed == 1:
                for task in project_tasks:
                    remove_label(task, next_action_label,
                                 overview_task_ids, overview_task_labels)
                    db_update_value(connection, task, 'task_type', None)
                    db_update_value(connection, task, 'parent_type', None)

        # Run for both non-sectioned and sectioned tasks
        # for s in [0,1]:
        #     if s == 0:
        #         sections = Section(None, None, 0, project.id)
        #     elif s == 1:
        #         try:
        #             sections = api.get_sections(project_id=project.id)
        #         except Exception as error:
        #             print(error)

        # Get all sections and add the 'None' section too.
        try:
            sections = [s for s in all_sections if s.project_id == project.id]
            # In API v3, Section requires: id, name, project_id, is_collapsed, order
            # Create a fake section for tasks without a section
            sections.insert(0, Section(id=None, name=None, project_id=project.id, is_collapsed=False, order=0))
        except Exception as error:
            logging.debug(error)

        # Reset
        first_found[0] = False

        for section in sections:

            # Check if section labelling is disabled (useful for e.g. Kanban)
            if next_action_label is not None:
                disable_section_labelling = 0
                try:
                    if section.name.startswith('*') or section.name.endswith('*'):
                        disable_section_labelling = 1
                except:
                    pass

            # Check db existance
            db_check_existance(connection, section)

            # Check if we need to (un)header entire secion
            api, header_all_in_s, unheader_all_in_s = check_header(
                api, section)

            # Get section type
            if next_action_label:
                section_type, section_type_changed = get_section_type(
                    args, connection, section, project)
            else:
                section_type = None
                section_type_changed = 0

            # Get all tasks for the section
            section_tasks = [x for x in project_tasks if x.section_id
                             == section.id]

            # Change top tasks parents_id from 'None' to '0' in order to numerically sort later on
            for task in section_tasks:
                if not task.parent_id:
                    task.parent_id = 0

            # Sort by parent_id and child order
            # In the past, Todoist used to screw up the tasks orders, so originally I processed parentless tasks first such that children could properly inherit porperties.
            # With the new API this seems to be in order, but I'm keeping this just in case for now. TODO: Could be used for optimization in the future.
            # In API v3, IDs are strings, so don't convert to int
            section_tasks = sorted(section_tasks, key=lambda x: (
                x.parent_id if x.parent_id else "", x.order))

            # If a type has changed, clean all tasks in this section for good measure
            if next_action_label is not None:
                if section_type_changed == 1:
                    for task in section_tasks:
                        remove_label(task, next_action_label,
                                     overview_task_ids, overview_task_labels)
                        db_update_value(connection, task, 'task_type', None)
                        db_update_value(connection, task, 'parent_type', None)

            # Reset
            first_found[1] = False

            # For all tasks in this section
            for task in section_tasks:

                # Reset
                dominant_type = None

                # Check db existance
                db_check_existance(connection, task)

                # Determine which child_tasks exist, both all and the ones that have not been checked yet
                non_completed_tasks = list(
                    filter(lambda x: not x.is_completed, section_tasks))
                child_tasks_all = list(
                    filter(lambda x: x.parent_id == task.id, section_tasks))
                child_tasks = list(
                    filter(lambda x: x.parent_id == task.id, non_completed_tasks))

                # Check if we need to (un)header entire task tree
                api, header_all_in_t, unheader_all_in_t = check_header(
                    api, task)

                # Modify headers where needed
                api = modify_task_headers(api, task, section_tasks, header_all_in_p,
                                          unheader_all_in_p, header_all_in_s, unheader_all_in_s, header_all_in_t, unheader_all_in_t)

                # TODO: Check is regeneration is still needed, now that it's part of core Todoist. Disabled for now.
                # Logic for recurring lists
                # if not args.regeneration:
                #     try:
                #         # If old label is present, reset it
                #         if item.r_tag == 1: #TODO: METADATA
                #             item.r_tag = 0  #TODO: METADATA
                #             api.items.update(item.id)
                #     except:
                #         pass

                # If options turned on, start recurring lists logic #TODO: regeneration currently doesn't work, becaue TASK_ENDPOINT doesn't show completed tasks. Use workaround.
                if args.regeneration is not None or args.end:
                    run_recurring_lists_logic(
                        args, api, connection, task, child_tasks, child_tasks_all, regen_labels_id)

                # If options turned on, start labelling logic
                if next_action_label is not None:
                    # Skip processing a task if it has already been checked or is a header
                    if task.is_completed:
                        continue

                    # Remove clean all task and subtask data
                    if task.content.startswith('*') or disable_section_labelling:
                        remove_label(task, next_action_label,
                                     overview_task_ids, overview_task_labels)
                        db_update_value(connection, task, 'task_type', None)
                        db_update_value(connection, task, 'parent_type', None)

                        task_ids = find_and_clean_all_children(
                            [], task, section_tasks)
                        child_tasks_all = list(
                            filter(lambda x: x.id in task_ids, section_tasks))

                        for child_task in child_tasks_all:
                            remove_label(child_task, next_action_label,
                                         overview_task_ids, overview_task_labels)
                            db_update_value(
                                connection, child_task, 'task_type', None)
                            db_update_value(
                                connection, child_task, 'parent_type', None)

                        continue

                    # Check task type
                    task_type, task_type_changed = get_task_type(
                        args, connection, task, section, project)

                    # If task type has changed, clean all of its children for good measure
                    if next_action_label is not None:
                        if task_type_changed == 1:

                            # Find all children under this task
                            task_ids = find_and_clean_all_children(
                                [], task, section_tasks)
                            child_tasks_all = list(
                                filter(lambda x: x.id in task_ids, section_tasks))

                            for child_task in child_tasks_all:
                                remove_label(
                                    child_task, next_action_label, overview_task_ids, overview_task_labels)
                                db_update_value(
                                    connection, child_task, 'task_type', None)
                                db_update_value(
                                    connection, child_task, 'parent_type', None)

                    # Determine hierarchy types for logic
                    hierarchy_types = [task_type,
                                       section_type, project_type]
                    hierarchy_boolean = [type(x) != type(None)
                                         for x in hierarchy_types]

                    # If task has no type, but has a label, most likely the order has been changed by user. Remove data.
                    if not True in hierarchy_boolean and next_action_label in task.labels:
                        remove_label(task, next_action_label,
                                     overview_task_ids, overview_task_labels)
                        db_update_value(connection, task, 'task_type', None)
                        db_update_value(connection, task, 'parent_type', None)

                    # If it is a parentless task, set task type based on hierarchy
                    if task.parent_id == 0:
                        if not True in hierarchy_boolean:
                            # Parentless task has no type, so skip any children.
                            continue
                        else:
                            if hierarchy_boolean[0]:
                                # Inherit task type
                                dominant_type = task_type
                            elif hierarchy_boolean[1]:
                                # Inherit section type
                                dominant_type = section_type
                            elif hierarchy_boolean[2]:
                                # Inherit project type
                                dominant_type = project_type

                            # TODO: optimise below code
                            # If indicated on project level
                            if dominant_type[0] == 's':
                                if not first_found[0]:

                                    if dominant_type[1] == 's':
                                        if not first_found[1]:
                                            add_label(
                                                task, next_action_label, overview_task_ids, overview_task_labels)

                                        elif next_action_label in task.labels:
                                            # Probably the task has been manually moved, so if it has a label, let's remove it.
                                            remove_label(
                                                task, next_action_label, overview_task_ids, overview_task_labels)

                                    elif dominant_type[1] == 'p':
                                        add_label(
                                            task, next_action_label, overview_task_ids, overview_task_labels)

                            elif dominant_type[0] == 'p':

                                if dominant_type[1] == 's':
                                    if not first_found[1]:
                                        add_label(
                                            task, next_action_label, overview_task_ids, overview_task_labels)

                                    elif next_action_label in task.labels:
                                        # Probably the task has been manually moved, so if it has a label, let's remove it.
                                        remove_label(
                                            task, next_action_label, overview_task_ids, overview_task_labels)

                                elif dominant_type[1] == 'p':
                                    add_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)

                            # If indicated on section level
                            if dominant_type[0] == 'x' and dominant_type[1] == 's':
                                if not first_found[1]:
                                    add_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)

                                elif next_action_label in task.labels:
                                    # Probably the task has been manually moved, so if it has a label, let's remove it.
                                    remove_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)

                            elif dominant_type[0] == 'x' and dominant_type[1] == 'p':
                                add_label(task, next_action_label,
                                          overview_task_ids, overview_task_labels)

                            # If indicated on parentless task level
                            if dominant_type[1] == 'x' and dominant_type[2] == 's':
                                if not first_found[1]:
                                    add_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)

                                if next_action_label in task.labels:
                                    # Probably the task has been manually moved, so if it has a label, let's remove it.
                                    remove_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)

                            elif dominant_type[1] == 'x' and dominant_type[2] == 'p':
                                add_label(task, next_action_label,
                                          overview_task_ids, overview_task_labels)

                    # If a parentless or sub-task which has children
                    if len(child_tasks) > 0:

                        # If it is a sub-task with no own type, inherit the parent task type instead
                        if task.parent_id != 0 and task_type == None:
                            dominant_type = db_read_value(
                                connection, task, 'parent_type')[0][0]

                        # If it is a sub-task with no dominant type (e.g. lower level child with new task_type), use the task type
                        if task.parent_id != 0 and dominant_type == None:
                            dominant_type = task_type

                        if dominant_type is None:
                            # Task with parent that has been headered, skip.
                            continue
                        else:
                            # Only last character is relevant for subtasks
                            dominant_type = dominant_type[-1]

                        # Process sequential tagged tasks
                        if dominant_type == 's':

                            for child_task in child_tasks:

                                # Ignore headered children
                                if child_task.content.startswith('*'):
                                    continue

                                # Clean up for good measure.
                                remove_label(
                                    child_task, next_action_label, overview_task_ids, overview_task_labels)

                                # Pass task_type down to the children
                                db_update_value(
                                    connection, child_task, 'parent_type', dominant_type)

                                # Pass label down to the first child
                                if not child_task.is_completed and next_action_label in task.labels:
                                    add_label(
                                        child_task, next_action_label, overview_task_ids, overview_task_labels)
                                    remove_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)

                        # Process parallel tagged tasks or untagged parents
                        elif dominant_type == 'p' and next_action_label in task.labels:
                            remove_label(
                                task, next_action_label, overview_task_ids, overview_task_labels)

                            for child_task in child_tasks:

                                # Ignore headered children
                                if child_task.content.startswith('*'):
                                    continue

                                db_update_value(
                                    connection, child_task, 'parent_type', dominant_type)

                                if not child_task.is_completed:
                                    add_label(
                                        child_task, next_action_label, overview_task_ids, overview_task_labels)

                    # Remove labels based on start / due dates

                    # If task is too far in the future, remove the next_action tag and skip
                    try:
                        if args.hide_future > 0 and task.due.date is not None:
                            due_date = datetime.strptime(
                                task.due.date, "%Y-%m-%d")
                            future_diff = (
                                due_date - datetime.today()).days
                            if future_diff >= args.hide_future:
                                remove_label(
                                    task, next_action_label, overview_task_ids, overview_task_labels)
                    except:
                        # Hide-future not set, skip
                        pass

                    # If start-date has not passed yet, remove label
                    try:
                        f1 = re.search(
                            r'start=(\d{2}[-]\d{2}[-]\d{4})', task.content)
                        if f1:
                            start_date = f1.groups()[0]
                            start_date = datetime.strptime(
                                start_date, args.dateformat)
                            future_diff = (
                                datetime.today()-start_date).days
                            # If start-date hasen't passed, remove all labels
                            if future_diff < 0:
                                remove_label(
                                    task, next_action_label, overview_task_ids, overview_task_labels)
                                [remove_label(child_task, next_action_label, overview_task_ids,
                                              overview_task_labels) for child_task in child_tasks]

                    except:
                        logging.warning(
                            'Wrong start-date format for task: "%s". Please use "start=<DD-MM-YYYY>"', task.content)
                        continue

                    # Recurring task friendly - remove label with relative change from due date
                    if task.due is not None:
                        try:
                            f2 = re.search(
                                r'start=due-(\d+)([dw])', task.content)

                            if f2:
                                offset = f2.groups()[0]

                                if f2.groups()[1] == 'd':
                                    td = timedelta(days=int(offset))
                                elif f2.groups()[1] == 'w':
                                    td = timedelta(weeks=int(offset))

                                # Determine start-date
                                try:
                                    due_date = datetime.strptime(
                                        task.due.datetime, "%Y-%m-%dT%H:%M:%S")
                                except:
                                    due_date = datetime.strptime(
                                        task.due.date, "%Y-%m-%d")

                                start_date = due_date - td

                                # If we're not in the offset from the due date yet, remove all labels
                                future_diff = (
                                    datetime.today()-start_date).days

                                if future_diff < 0:
                                    remove_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)
                                    [remove_label(child_task, next_action_label, overview_task_ids,
                                                  overview_task_labels) for child_task in child_tasks]
                                    continue

                        except:
                            logging.warning(
                                'Wrong start-date format for task: %s. Please use "start=due-<NUM><d or w>"', task.content)
                            continue

                # Mark first found task in section
                # TODO: is this always true? What about starred tasks?
                if next_action_label is not None and first_found[1] == False:
                    first_found[1] = True

            # Mark first found section with tasks in project (to account for None section)
            if next_action_label is not None and first_found[0] == False and section_tasks:
                first_found[0] = True

    # Return all ids and corresponding labels that need to be modified
    return overview_task_ids, overview_task_labels

# Main


def main():

    # Version
    current_version = 'v2.0'

    # Main process functions.
    parser = argparse.ArgumentParser(
        formatter_class=make_wide(argparse.HelpFormatter, w=120, h=60))
    parser.add_argument(
        '-a', '--api_key', help='takes your Todoist API Key.', default=os.environ.get('TODOIST_API_KEY'), type=str)
    parser.add_argument(
        '-l', '--label', help='enable next action labelling. Define which label to use.', type=str)
    parser.add_argument(
        '-r', '--regeneration', help='[CURRENTLY DISABLED FEATURE] enable regeneration of sub-tasks in recurring lists. Chose overall mode: 0 - regen off, 1 - regen all (default),  2 - regen only if all sub-tasks are completed. Task labels can be used to overwrite this mode.', nargs='?', const='1', default=None, type=int)
    parser.add_argument(
        '-e', '--end', help='enable alternative end-of-day time instead of default midnight. Enter a number from 1 to 24 to define which hour is used.', type=int)
    parser.add_argument(
        '-d', '--delay', help='specify the delay in seconds between syncs (default 5).', default=5, type=int)
    parser.add_argument(
        '-p', '--p_suffix', help='change suffix for parallel labeling (default "=").', default='=')
    parser.add_argument(
        '-s', '--s_suffix', help='change suffix for sequential labeling (default "-").', default='-')
    parser.add_argument(
        '-df', '--dateformat', help='[CURRENTLY DISABLED FEATURE] strptime() format of starting date (default "%%d-%%m-%%Y").', default='%d-%m-%Y')
    parser.add_argument(
        '-hf', '--hide_future', help='prevent labelling of future tasks beyond a specified number of days.', default=0, type=int)
    parser.add_argument(
        '--onetime', help='update Todoist once and exit.', action='store_true')
    parser.add_argument('--debug', help='enable debugging and store detailed to a log file.',
                        action='store_true')
    parser.add_argument('--inbox', help='the method the Inbox should be processed with.',
                        default=None, choices=['parallel', 'sequential'])

    args = parser.parse_args()

    # #TODO: Temporary disable this feature for now. Find a way to see completed tasks first, since REST API v2 lost this funcionality.
    args.regeneration = None

    # Addition of regeneration labels
    args.regen_label_names = ('Regen_off', 'Regen_all',
                              'Regen_all_if_completed')

    # Set logging
    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # Set logging config settings
    logging.basicConfig(level=log_level,
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        handlers=[logging.FileHandler(
                            'debug.log', 'w+', 'utf-8'),
                            logging.StreamHandler()]
                        )

    # Check for updates
    check_for_update(current_version)

    # Initialise api
    api = initialise_api(args)

    # Initialise SQLite database
    connection = initialise_sqlite()

    # Start main loop
    while True:
        start_time = time.time()

        # Evaluate projects, sections, and tasks
        overview_task_ids, overview_task_labels = autodoist_magic(
            args, api, connection)

        # Commit next action label changes
        if args.label is not None:
            api = commit_labels_update(api, overview_task_ids,
                                       overview_task_labels)

        # Sync all queued up changes
        if api.queue:
            sync(api)

        num_changes = len(api.queue)+len(api.overview_updated_ids)

        if num_changes:
            if num_changes == 1:
                logging.info(
                    '%d change committed to Todoist.', num_changes)
            else:
                logging.info(
                    '%d changes committed to Todoist.', num_changes)
        else:
            logging.info('No changes in queue, skipping sync.')

        # If onetime is set, exit after first execution.
        if args.onetime:
            break

        # Set a delay before next sync
        end_time = time.time()
        delta_time = end_time - start_time

        if args.delay - delta_time < 0:
            logging.debug(
                'Computation time %d is larger than the specified delay %d. Sleeping skipped.', delta_time, args.delay)
        elif args.delay >= 0:
            sleep_time = args.delay - delta_time
            logging.debug('Sleeping for %d seconds', sleep_time)
            time.sleep(sleep_time)


if __name__ == '__main__':
    main()
