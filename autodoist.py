#!/usr/bin/python3

from todoist_api_python.api import TodoistAPI
import sys
import time
import requests
import argparse
import logging
from datetime import datetime, timedelta
import time
import sqlite3
from sqlite3 import Error

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

# Sync with Todoist API


def sync(api):
    try:
        logging.debug('Syncing the current state from the API')
        api.sync()
    except Exception as e:
        logging.exception(
            'Error trying to sync with Todoist API: %s' % str(e))
        quit()

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
    labels = api.get_labels()
    label = [x for x in labels if x.name == label_name]

    if len(label) > 0:
        next_action_label = label[0].id
        logging.debug('Label \'%s\' found as label id %d',
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
                print(error)

            labels = api.get_labels()
            label = [x for x in labels if x.name == label_name]
            next_action_label = label[0].id

            logging.info("Label '{}' has been created!".format(label_name))
        else:
            logging.info('Exiting Autodoist.')
            exit(1)

    return 0

# Initialisation of Autodoist
def initialise(args):

    # Check we have a API key
    if not args.api_key:
        logging.error(
            "\n\nNo API key set. Run Autodoist with '-a <YOUR_API_KEY>'\n")
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
        if not set([0,1,2]) & set([args.regeneration]):
            logging.error('Wrong regeneration mode. Please choose a number from 0 to 2. Check --help for more information on the available modes.')
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

    api_arguments = {'token': args.api_key}
    
    if args.nocache:
        logging.debug('Disabling local caching')
        api_arguments['cache'] = None

    api = TodoistAPI(**api_arguments)

    logging.info("Autodoist has connected and is running fine!\n")

    # Check if labels exist

    # If labeling argument is used
    if args.label is not None:

        # Verify that the next action label exists; ask user if it needs to be created
        verify_label_existance(api, args.label, 1)

    # If regeneration mode is used, verify labels
    if args.regeneration is not None:

        # Verify the existance of the regeneraton labels; force creation of label
        regen_labels_id = [verify_label_existance(
            api, regen_label, 2) for regen_label in args.regen_label_names]

    else:
        # Label functionality not needed
        regen_labels_id = [None, None, None]

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

# Assign current type based on settings


def check_name(args, name):
    len_suffix = [len(args.pp_suffix), len(args.ss_suffix),
                  len(args.ps_suffix), len(args.sp_suffix)]

    if name == 'Inbox':
        current_type = args.inbox
    elif name[-len_suffix[0]:] == args.pp_suffix:
        current_type = 'parallel'
    elif name[-len_suffix[1]:] == args.ss_suffix:
        current_type = 'sequential'
    elif name[-len_suffix[2]:] == args.ps_suffix:
        current_type = 'p-s'
    elif name[-len_suffix[3]:] == args.sp_suffix:
        current_type = 's-p'
    #TODO: Remove below workarounds if standard notation is changing. Just messy and no longer needed.
    # # Workaround for section names, which don't allow '/' symbol.
    # elif args.ps_suffix == '/-' and name[-2:] == '_-':
    #     current_type = 'p-s'
    # # Workaround for section names, which don't allow '/' symbol.
    # elif args.sp_suffix == '-/' and name[-2:] == '-_':
    #     current_type = 's-p'
    # # Workaround for section names, which don't allow '/' symbol.
    # elif args.pp_suffix == '//' and name[-1:] == '_':
    #     current_type = 'parallel'
    else:
        current_type = None

    return current_type

# Scan the end of a name to find what type it is


def get_type(args, model, key):

    model_name = ''

    try:
        old_type = model[key] #TODO: METADATA: this information used to be part of the metadata, needs to be retreived from own database
    except:
        # logging.debug('No defined project_type: %s' % str(e))
        old_type = None

    try:
        model_name = model.name.strip()
    except:
        #TODO: Old support for legacy tag in v1 API, can likely be removed since moving to v2.
        # try:
        #     
        #     object_name = object['content'].strip()
        # except:
        #     pass
        pass

    current_type = check_name(args, model_name)

    # Check if project type changed with respect to previous run
    if old_type == current_type:
        type_changed = 0
    else:
        type_changed = 1
        # model.key = current_type #TODO: METADATA: this information used to be part of the metadata, needs to be retreived from own database

    return current_type, type_changed

# Determine a project type


def get_project_type(args, project_model):
    """Identifies how a project should be handled."""
    project_type, project_type_changed = get_type(
        args, project_model, 'project_type')

    return project_type, project_type_changed

# Determine a section type


def get_section_type(args, section_object):
    """Identifies how a section should be handled."""
    if section_object is not None:
        section_type, section_type_changed = get_type(
            args, section_object, 'section_type')
    else:
        section_type = None
        section_type_changed = 0

    return section_type, section_type_changed

# Determine an task type


def get_task_type(args, task, project_type):
    """Identifies how a task with sub tasks should be handled."""

    if project_type is None and task.parent_id != 0:
        try:
            task_type = task.parent_type #TODO: METADATA
            task_type_changed = 1
            task.task_type = task_type
        except:
            task_type, task_type_changed = get_type(args, task, 'task_type')  #TODO: METADATA
    else:
        task_type, task_type_changed = get_type(args, task, 'task_type')  #TODO: METADATA

    return task_type, task_type_changed

# Logic to track addition of a label to a task


def add_label(task, label, overview_task_ids, overview_task_labels):
    if label not in task.labels:
        labels = task.labels # Copy other existing labels
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

# Ensure label updates are only issued once per task


def update_labels(api, overview_task_ids, overview_task_labels):
    filtered_overview_ids = [
        k for k, v in overview_task_ids.items() if v != 0]
    for task_id in filtered_overview_ids:
        labels = overview_task_labels[task_id]
        api.update_task(task_id=task_id, labels=labels)

    return filtered_overview_ids

# To handle tasks which have no sections


def create_none_section():
    none_sec = {
        'id': None,
        'name': 'None',
        'section_order': 0
    }
    return none_sec

# Check if header logic needs to be applied


def check_header(level):
    header_all_in_level = False
    unheader_all_in_level = False
    method = 0

    try:
        # Support for legacy structure
        name = level['name']
        method = 1
    except:
        try:
            # Current structure
            content = level.content
            method = 2
        except:
            pass

    if method == 1:
        if name[:3] == '** ':
            header_all_in_level = True
            level.update(name=name[3:])
        if name[:3] == '!* ' or name[:3] == '_* ':
            unheader_all_in_level = True
            level.update(name=name[3:])
    elif method == 2:
        if content[:3] == '** ':
            header_all_in_level = True
            level.update(content=content[3:])
        if content[:3] == '!* ' or content[:3] == '_* ':
            unheader_all_in_level = True
            level.update(content=content[3:])
    else:
        pass

    return header_all_in_level, unheader_all_in_level

# Logic for applying and removing headers
def modify_headers(task, child_tasks, header_all_in_p, unheader_all_in_p, header_all_in_s, unheader_all_in_s, header_all_in_t, unheader_all_in_t):       
    if any([header_all_in_p, header_all_in_s, header_all_in_t]):
        if task.content[0] != '*':
            task.update(content='* ' + task.content)
            for ci in child_tasks:
                if not ci.content.startswith('*'):
                    ci.update(content='* ' + ci.content)

    if any([unheader_all_in_p, unheader_all_in_s]):
        if task.content[0] == '*':
            task.update(content=task.content[2:])
    if unheader_all_in_t:
        [ci.update(content=ci.content[2:])
            for ci in child_tasks]

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


def run_recurring_lists_logic(args, api, item, child_items, child_items_all, regen_labels_id):

    if item['parent_id'] == 0:
        try:
            if item['due']['is_recurring']:
                try:
                    # Check if the T0 task date has changed
                    if item['due']['date'][:10] != item['date_old']:

                        # Mark children for action based on mode
                        if args.regeneration is not None:

                            # Check if task has a regen label
                            regen_mode = check_regen_mode(
                                api, item, regen_labels_id)

                            # If no label, use general mode instead
                            if regen_mode is None:
                                regen_mode = args.regeneration
                                logging.debug('Using general recurring mode \'%s\' for item: %s',
                                    regen_mode, item.content)
                            else:
                                logging.debug('Using recurring label \'%s\' for item: %s',
                                    regen_mode, item.content)

                            # Apply tags based on mode
                            give_regen_tag = 0

                            if regen_mode == 1: # Regen all
                                give_regen_tag = 1
                            elif regen_mode == 2: # Regen if all sub-tasks completed
                                if not child_items:
                                    give_regen_tag = 1

                            if give_regen_tag == 1:
                                for child_item in child_items_all:
                                    child_item['r_tag'] = 1

                        # If alternative end of day, fix due date if needed
                        if args.end is not None:
                            # Determine current hour
                            t = datetime.today()
                            current_hour = t.hour

                            # Check if current time is before our end-of-day
                            if (args.end - current_hour) > 0:

                                # Determine the difference in days set by todoist
                                nd = [
                                    int(x) for x in item['due']['date'][:10].split('-')]
                                od = [
                                    int(x) for x in item['date_old'][:10].split('-')]

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
                                    today_str = [str(x) for x in [
                                        today.year, today.month, today.day]]
                                    if len(today_str[1]) == 1:
                                        today_str[1] = ''.join(
                                            ['0', today_str[1]])

                                    # Update due-date to today
                                    item_due = item['due']
                                    item_due['date'] = '-'.join(
                                        today_str)
                                    item.update(due=item_due)
                                    # item.update(due={'date': '2020-05-29', 'is_recurring': True, 'string': 'every day'})

                        # Save the new date for reference us
                        item.update(
                            date_old=item['due']['date'][:10])

                except:
                    # If date has never been saved before, create a new entry
                    logging.debug(
                        'New recurring task detected: %s' % item.content)
                    item['date_old'] = item['due']['date'][:10]
                    api.items.update(item['id'])

        except:
            # logging.debug(
            #     'Parent not recurring: %s' % item.content)
            pass

    if args.regeneration is not None and item['parent_id'] != 0:
        try:
            if item['r_tag'] == 1:
                item.update(checked=0)
                item.update(in_history=0)
                item['r_tag'] = 0
                api.items.update(item['id'])

                for child_item in child_items_all:
                    child_item['r_tag'] = 1
        except:
            # logging.debug('Child not recurring: %s' %
            #               item.content)
            pass

# Contains all main autodoist functionalities


def autodoist_magic(args, api, next_action_label, regen_labels_id):

    # Preallocate dictionaries
    overview_task_ids = {}
    overview_task_labels = {}

    try:
        projects = api.get_projects()
    except Exception as error:
        print(error)

    for project in projects:

        # To determine if a sequential task was found
        first_found_project = False

        # Check if we need to (un)header entire project
        header_all_in_p, unheader_all_in_p = check_header(project)

        # Get project type
        if next_action_label is not None:
            project_type, project_type_changed = get_project_type(
                args, project)

            if project_type is not None:
                logging.debug('Identified \'%s\' as %s type',
                            project.name, project_type)

        # Get all tasks for the project
        try:
            project_tasks = api.get_tasks(project_id = project.id)
        except Exception as error:
            print(error)

        # Run for both non-sectioned and sectioned tasks

        # Get completed tasks: 
        # endpoint = 'https://api.todoist.com/sync/v9/completed/get_all'
        # get(api._session, endpoint, api._token, '0')['items']
        # $ curl https://api.todoist.com/sync/v9/sync-H "Authorization: Bearer e2f750b64e8fc06ae14383d5e15ea0792a2c1bf3" -d commands='[ {"type": "item_add", "temp_id": "63f7ed23-a038-46b5-b2c9-4abda9097ffa", "uuid": "997d4b43-55f1-48a9-9e66-de5785dfd69b", "args": {"content": "Buy Milk", "project_id": "2203306141","labels": ["Food", "Shopping"]}}]'

        # for s in [0, 1]: # TODO: TEMPORARELY SKIP SECTIONLESS TASKS
        for s in [1]:
            if s == 0:
                sections = [create_none_section()] # TODO: Rewrite
            elif s == 1:
                try:
                    sections = api.get_sections(project_id = project.id)
                except Exception as error:
                    print(error)

            for section in sections:

                # Check if we need to (un)header entire secion
                header_all_in_s, unheader_all_in_s = check_header(section)

                # To determine if a sequential task was found
                first_found_section = False

                # Get section type
                section_type, section_type_changed = get_section_type(
                    args, section)
                if section_type is not None:
                    logging.debug('Identified \'%s\' as %s type',
                                section.name, section_type)

                # Get all tasks for the section
                tasks = [x for x in project_tasks if x.section_id
                         == section.id]

                # Change top tasks parents_id from 'None' to '0' in order to numerically sort later on
                for task in tasks:
                    if not task.parent_id:
                        task.parent_id = 0

                # Sort by parent_id and child order
                # In the past, Todoist used to screw up the tasks orders, so originally I processed parentless tasks first such that children could properly inherit porperties.
                # With the new API this seems to be in order, but I'm keeping this just in case for now. TODO: Could be used for optimization in the future.
                tasks = sorted(tasks, key=lambda x: (
                    int(x.parent_id), x.order))

                # If a type has changed, clean all task labels for good measure
                if next_action_label is not None:
                    if project_type_changed == 1 or section_type_changed == 1:
                        # Remove labels
                        [remove_label(task, next_action_label, overview_task_ids,
                                      overview_task_labels) for task in tasks]
                        # Remove parent types
                        # for task in tasks:
                        #     task.parent_type = None #TODO: METADATA 

                # For all tasks in this section
                for task in tasks:
                    dominant_type = None  # Reset

                    # Possible nottes routine for the future
                    # notes = api.notes.all() TODO: Quick notes test to see what the impact is?
                    # note_content = [x['content'] for x in notes if x['item_id'] == item['id']]
                    # print(note_content)

                    # Determine which child_tasks exist, both all and the ones that have not been checked yet
                    non_completed_tasks = list(
                        filter(lambda x: not x.is_completed, tasks))
                    child_tasks_all = list(
                        filter(lambda x: x.parent_id == task.id, tasks))
                    child_tasks = list(
                        filter(lambda x: x.parent_id == task.id, non_completed_tasks))

                    # Check if we need to (un)header entire task tree
                    header_all_in_t, unheader_all_in_t = check_header(task)

                    # Modify headers where needed
                    #TODO: DISABLED FOR NOW, FIX LATER
                    # modify_headers(header_all_in_p, unheader_all_in_p, header_all_in_s, unheader_all_in_s, header_all_in_t, unheader_all_in_t)

#TODO: Check is regeneration is still needed, now that it's part of core Todoist. Disabled for now.
                    # Logic for recurring lists
                    # if not args.regeneration:
                    #     try:
                    #         # If old label is present, reset it
                    #         if item.r_tag == 1: #TODO: METADATA
                    #             item.r_tag = 0  #TODO: METADATA
                    #             api.items.update(item.id)
                    #     except:
                    #         pass

                    # # If options turned on, start recurring lists logic
                    # if args.regeneration is not None or args.end:
                    #     run_recurring_lists_logic(
                    #         args, api, item, child_items, child_items_all, regen_labels_id)

                    # If options turned on, start labelling logic
                    if next_action_label is not None:
                        # Skip processing a task if it has already been checked or is a header
                        if task.is_completed:
                            continue
                        if task.content.startswith('*'):
                            # Remove next action label if it's still present
                            remove_label(task, next_action_label, overview_task_ids, overview_task_labels)
                            continue

                        # Check task type
                        task_type, task_type_changed = get_task_type(
                            args, task, project_type)
                        if task_type is not None:
                            logging.debug('Identified \'%s\' as %s type',
                                        task.content, task_type)

                        # Determine hierarchy types for logic
                        hierarchy_types = [task_type,
                                           section_type, project_type]
                        hierarchy_boolean = [type(x) != type(None)
                                        for x in hierarchy_types]

                        # If it is a parentless task
                        if task.parent_id == 0:
                            if hierarchy_boolean[0]:
                                # Inherit task type
                                dominant_type = task_type
                                add_label(
                                    task, next_action_label, overview_task_ids, overview_task_labels)

                            elif hierarchy_boolean[1]:
                                # Inherit section type
                                dominant_type = section_type

                                if section_type == 'sequential' or section_type == 's-p':
                                    if not first_found_section:
                                        add_label(
                                            task, next_action_label, overview_task_ids, overview_task_labels)
                                        first_found_section = True
                                elif section_type == 'parallel' or section_type == 'p-s':
                                    add_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)

                            elif hierarchy_boolean[2]:
                                # Inherit project type
                                dominant_type = project_type

                                if project_type == 'sequential' or project_type == 's-p':
                                    if not first_found_project:
                                        add_label(
                                            task, next_action_label, overview_task_ids, overview_task_labels)
                                        first_found_project = True

                                elif project_type == 'parallel' or project_type == 'p-s':
                                    add_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)

                            # Mark other conditions too
                            if first_found_section == False and hierarchy_boolean[1]:
                                first_found_section = True
                            if first_found_project is False and hierarchy_boolean[2]:
                                first_found_project = True

                        # If there are children
                        if len(child_tasks) > 0:
                            # Check if task state has changed, if so clean children for good measure
                            if task_type_changed == 1:
                                [remove_label(child_task, next_action_label, overview_task_ids, overview_task_labels)
                                    for child_task in child_tasks]

                            # If a sub-task, inherit parent task type
                            if task.parent_id !=0:
                                try:
                                    dominant_type = task.parent_type #TODO: METADATA
                                except:
                                    pass 
                            
                            # Process sequential tagged tasks (task_type can overrule project_type)
                            if dominant_type == 'sequential' or dominant_type == 'p-s':
                                for child_task in child_tasks:
                                    
                                    # Ignore headered children
                                    if child_task.content.startswith('*'):
                                        continue

                                    # Pass task_type down to the children
                                    child_task.parent_type = dominant_type
                                    # Pass label down to the first child
                                    if not child_task.is_completed and next_action_label in task.labels:
                                        add_label(
                                            child_task, next_action_label, overview_task_ids, overview_task_labels)
                                        remove_label(
                                            task, next_action_label, overview_task_ids, overview_task_labels)
                                    else:
                                        # Clean for good measure
                                        remove_label(
                                            child_task, next_action_label, overview_task_ids, overview_task_labels)

                            # Process parallel tagged tasks or untagged parents
                            elif dominant_type == 'parallel' or (dominant_type == 's-p' and next_action_label in task.labels):
                                remove_label(
                                    task, next_action_label, overview_task_ids, overview_task_labels)
                                for child_task in child_tasks:

                                    # Ignore headered children
                                    if child_task.content.startswith('*'):
                                        continue

                                    child_task.parent_type = dominant_type #TODO: METADATA
                                    if not child_task.is_completed:
                                        add_label(
                                            child_task, next_action_label, overview_task_ids, overview_task_labels)

                        # Remove labels based on start / due dates

                        # If task is too far in the future, remove the next_action tag and skip #TODO: FIX THIS
                        try:
                            if args.hide_future > 0 and 'due' in task.data and task.due is not None:
                                due_date = datetime.strptime(
                                    task.due['date'][:10], "%Y-%m-%d")
                                future_diff = (
                                    due_date - datetime.today()).days
                                if future_diff >= args.hide_future:
                                    remove_label(
                                        task, next_action_label, overview_task_ids, overview_task_labels)
                                    continue
                        except:
                            # Hide-future not set, skip
                            continue

                        # If start-date has not passed yet, remove label
                        try:
                            f1 = task.content.find('start=')
                            f2 = task.content.find('start=due-')
                            if f1 > -1 and f2 == -1:
                                f_end = task.content[f1+6:].find(' ')
                                if f_end > -1:
                                    start_date = task.content[f1 +
                                                                 6:f1+6+f_end]
                                else:
                                    start_date = task.content[f1+6:]

                                # If start-date hasen't passed, remove all labels
                                start_date = datetime.strptime(
                                    start_date, args.dateformat)
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
                                'Wrong start-date format for task: "%s". Please use "start=<DD-MM-YYYY>"', task.content)
                            continue

                        # Recurring task friendly - remove label with relative change from due date #TODO Fix this logic
                        try:
                            f = task.content.find('start=due-')
                            if f > -1:
                                f1a = task.content.find(
                                    'd')  # Find 'd' from 'due'
                                f1b = task.content.rfind(
                                    'd')  # Find 'd' from days
                                f2 = task.content.find('w')
                                f_end = task.content[f+10:].find(' ')

                                if f_end > -1:
                                    offset = task.content[f+10:f+10+f_end-1]
                                else:
                                    offset = task.content[f+10:-1]

                                try:
                                    task_due_date = task.due['date'][:10]
                                    task_due_date = datetime.strptime(
                                        task_due_date, '%Y-%m-%d')
                                except:
                                    logging.warning(
                                        'No due date to determine start date for task: "%s".', task.content)
                                    continue

                                if f1a != f1b and f1b > -1:  # To make sure it doesn't trigger if 'w' is chosen
                                    td = timedelta(days=int(offset))
                                elif f2 > -1:
                                    td = timedelta(weeks=int(offset))

                                # If we're not in the offset from the due date yet, remove all labels
                                start_date = task_due_date - td
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

    return overview_task_ids, overview_task_labels


# Connect to SQLite database

def create_connection(path):
    connection = None
    try:
        connection = sqlite3.connect(path)
        print("Connection to SQLite DB successful")
    except Error as e:
        print(f"The error '{e}' occurred")

    return connection

# Main


def main():

    # Version
    current_version = 'v1.5'

    # Main process functions.
    parser = argparse.ArgumentParser(
        formatter_class=make_wide(argparse.HelpFormatter, w=120, h=60))
    parser.add_argument('-a', '--api_key',
                        help='takes your Todoist API Key.', type=str)
    parser.add_argument(
        '-l', '--label', help='enable next action labelling. Define which label to use.', type=str)
    parser.add_argument(
        '-r', '--regeneration', help='enable regeneration of sub-tasks in recurring lists. Chose overall mode: 0 - regen off, 1 - regen all (default),  2 - regen only if all sub-tasks are completed. Task labels can be used to overwrite this mode.', nargs='?', const='1', default=None, type=int)
    parser.add_argument(
        '-e', '--end', help='enable alternative end-of-day time instead of default midnight. Enter a number from 1 to 24 to define which hour is used.', type=int)
    parser.add_argument(
        '-d', '--delay', help='specify the delay in seconds between syncs (default 5).', default=5, type=int)
    parser.add_argument(
        '-pp', '--pp_suffix', help='change suffix for parallel-parallel labeling (default "==").', default='==')
    parser.add_argument(
        '-ss', '--ss_suffix', help='change suffix for sequential-sequential labeling (default "--").', default='--')
    parser.add_argument(
        '-ps', '--ps_suffix', help='change suffix for parallel-sequential labeling (default "=-").', default='=-')
    parser.add_argument(
        '-sp', '--sp_suffix', help='change suffix for sequential-parallel labeling (default "-=").', default='-=')
    parser.add_argument(
        '-df', '--dateformat', help='strptime() format of starting date (default "%%d-%%m-%%Y").', default='%d-%m-%Y')
    parser.add_argument(
        '-hf', '--hide_future', help='prevent labelling of future tasks beyond a specified number of days.', default=0, type=int)
    parser.add_argument(
        '--onetime', help='update Todoist once and exit.', action='store_true')
    parser.add_argument(
        '--nocache', help='disables caching data to disk for quicker syncing.', action='store_true')
    parser.add_argument('--debug', help='enable debugging and store detailed to a log file.',
                        action='store_true')
    parser.add_argument('--inbox', help='the method the Inbox should be processed with.',
                        default=None, choices=['parallel', 'sequential'])

    args = parser.parse_args()

    # #TODO: Temporary disable this feature for now. Find a way to see completed tasks first, since REST API v2 lost this funcionality.
    args.regeneration = 0

    # Addition of regeneration labels
    args.regen_label_names = ('Regen_off', 'Regen_all',
                              'Regen_all_if_completed')

    # Set debug
    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

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
    api = initialise(args)

    # Start main loop
    while True:
        start_time = time.time()
        # sync(api)

        # Evaluate projects, sections, and tasks
        overview_task_ids, overview_task_labels = autodoist_magic(
            args, api, args.label, args.regen_label_names)

        # Commit next action label changes
        if args.label is not None:
            updated_ids = update_labels(api, overview_task_ids,
                          overview_task_labels)

        if len(updated_ids):
            len_api_q = len(updated_ids)

            if len_api_q == 1:
                logging.info(
                    '%d change committed to Todoist.', len_api_q)
            else:
                logging.info(
                    '%d changes committed to Todoist.', len_api_q)
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
