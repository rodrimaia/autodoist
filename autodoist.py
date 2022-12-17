#!/usr/bin/python3

from todoist_api_python.api import TodoistAPI
import sys
import time
import requests
import argparse
import logging
from datetime import datetime, timedelta
import time

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
        label_id = label[0].id
        logging.debug('Label \'%s\' found as label id %d',
                      label_name, label_id)
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
            label_id = label[0].id

            logging.info("Label '{}' has been created!".format(label_name))
        else:
            logging.info('Exiting Autodoist.')
            exit(1)

    return label_id


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
        label_id = verify_label_existance(api, args.label, 1)

    else:
        # Label functionality not needed
        label_id = None

    # If regeneration mode is used, verify labels
    if args.regeneration is not None:

        # Verify the existance of the regeneraton labels; force creation of label
        regen_labels_id = [verify_label_existance(
            api, regen_label, 2) for regen_label in args.regen_label_names]

    else:
        # Label functionality not needed
        regen_labels_id = [None, None, None]

    return api, label_id, regen_labels_id

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
    elif name[-len_suffix[1]:] == args.ps_suffix:
        current_type = 'p-s'
    elif name[-len_suffix[1]:] == args.sp_suffix:
        current_type = 's-p'
    # Workaround for section names, which don't allow / symbol.
    elif args.ps_suffix == '/-' and name[-2:] == '_-':
        current_type = 'p-s'
    # Workaround for section names, which don't allow / symbol.
    elif args.sp_suffix == '-/' and name[-2:] == '-_':
        current_type = 's-p'
    # Workaround for section names, which don't allow / symbol.
    elif args.pp_suffix == '//' and name[-1:] == '_':
        current_type = 'parallel'
    else:
        current_type = None

    return current_type

# Scan the end of a name to find what type it is


def get_type(args, object, key):

    object_name = ''

    try:
        old_type = object[key]
    except:
        # logging.debug('No defined project_type: %s' % str(e))
        old_type = None

    try:
        object_name = object['name'].strip()
    except:
        try:
            object_name = object['content'].strip()
        except:
            pass

    current_type = check_name(args, object_name)

    # Check if project type changed with respect to previous run
    if old_type == current_type:
        type_changed = 0
    else:
        type_changed = 1
        object[key] = current_type

    return current_type, type_changed

# Determine a project type


def get_project_type(args, project_object):
    """Identifies how a project should be handled."""
    project_type, project_type_changed = get_type(
        args, project_object, 'project_type')

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

# Determine an item type


def get_item_type(args, item, project_type):
    """Identifies how an item with sub items should be handled."""

    if project_type is None and item['parent_id'] != 0:
        try:
            item_type = item['parent_type']
            item_type_changed = 1
            item['item_type'] = item_type
        except:
            item_type, item_type_changed = get_type(args, item, 'item_type')
    else:
        item_type, item_type_changed = get_type(args, item, 'item_type')

    return item_type, item_type_changed

# Logic to add a label to an item


def add_label(item, label, overview_item_ids, overview_item_labels):
    if label not in item['labels']:
        labels = item['labels']
        logging.debug('Updating \'%s\' with label', item['content'])
        labels.append(label)

        try:
            overview_item_ids[str(item['id'])] += 1
        except:
            overview_item_ids[str(item['id'])] = 1
        overview_item_labels[str(item['id'])] = labels

# Logic to remove a label from an item


def remove_label(item, label, overview_item_ids, overview_item_labels):
    if label in item['labels']:
        labels = item['labels']
        logging.debug('Removing \'%s\' of its label', item['content'])
        labels.remove(label)

        try:
            overview_item_ids[str(item['id'])] -= 1
        except:
            overview_item_ids[str(item['id'])] = -1
        overview_item_labels[str(item['id'])] = labels

# Ensure labels are only issued once per item


def update_labels(api, label_id, overview_item_ids, overview_item_labels):
    filtered_overview_ids = [
        k for k, v in overview_item_ids.items() if v != 0]
    for item_id in filtered_overview_ids:
        labels = overview_item_labels[item_id]
        api.items.update(item_id, labels=labels)

# To handle items which have no sections


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
            content = level['content']
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

# Check regen mode based on label name


def check_regen_mode(api, item, regen_labels_id):

    labels = item['labels']

    overlap = set(labels) & set(regen_labels_id)
    overlap = [val for val in overlap]

    if len(overlap) > 1:
        logging.warning(
            'Multiple regeneration labels used! Please pick only one for item: "{}".'.format(item['content']))
        return None

    try:
        regen_label_id = overlap[0]
    except:
        logging.debug(
            'No regeneration label for item: %s' % item['content'])
        regen_label_id = [0]

    if regen_label_id == regen_labels_id[0]:
        return 0
    elif regen_label_id == regen_labels_id[1]:
        return 1
    elif regen_label_id == regen_labels_id[2]:
        return 2
    else:
        # label_name = api.labels.get_by_id(regen_label_id)['name']
        # logging.debug(
            # 'No regeneration label for item: %s' % item['content'])
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
                                    regen_mode, item['content'])
                            else:
                                logging.debug('Using recurring label \'%s\' for item: %s',
                                    regen_mode, item['content'])

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

                                    # Find curreny date in string format
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
                        'New recurring task detected: %s' % item['content'])
                    item['date_old'] = item['due']['date'][:10]
                    api.items.update(item['id'])

        except:
            # logging.debug(
            #     'Parent not recurring: %s' % item['content'])
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
            #               item['content'])
            pass

# Contains all main autodoist functionalities


def autodoist_magic(args, api, label_id, regen_labels_id):

    # Preallocate dictionaries
    overview_item_ids = {}
    overview_item_labels = {}

    try:
        projects = api.get_projects()
    except Exception as error:
        print(error)

    for project in projects:

        # To determine if a sequential task was found
        first_found_project = False

        # Check if we need to (un)header entire project
        header_all_in_p, unheader_all_in_p = check_header(project)

        if label_id is not None:
            # Get project type
            project_type, project_type_changed = get_project_type(
                args, project)
            if project_type is not None:
                logging.debug('Identified \'%s\' as %s type',
                            project['name'], project_type)

        # Get all items for the project
        try:
            project_tasks = api.get_tasks(project_id = project.id)
        except Exception as error:
            print(error)

        # Run for both none-sectioned and sectioned items

        # Get completed tasks: get(api._session, endpoint, api._token, '0')['items']

        # for s in [0, 1]: # TEMP SECTION ONLY
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
                                section['name'], section_type)

                # Get all items for the section
                tasks = [x for x in project_tasks if x.section_id
                         == section.id]

                # Change top parents_id in order to numerically sort later on
                for task in tasks:
                    if not task.parent_id:
                        task.parent_id = 0

                # Sort by parent_id and filter for completable items
                items = sorted(items, key=lambda x: (
                    x['parent_id'], x['child_order']))

                # If a type has changed, clean label for good measure
                if label_id is not None:
                    if project_type_changed == 1 or section_type_changed == 1:
                        # Remove labels
                        [remove_label(item, label_id, overview_item_ids,
                                      overview_item_labels) for item in items]
                        # Remove parent types
                        for item in items:
                            item['parent_type'] = None

                # For all items in this section
                for item in items:
                    active_type = None  # Reset

                    # Possible nottes routine for the future
                    # notes = api.notes.all() TODO: Quick notes test to see what the impact is?
                    # note_content = [x['content'] for x in notes if x['item_id'] == item['id']]
                    # print(note_content)

                    # Determine which child_items exist, both all and the ones that have not been checked yet
                    non_checked_items = list(
                        filter(lambda x: x['checked'] == 0, items))
                    child_items_all = list(
                        filter(lambda x: x['parent_id'] == item['id'], items))
                    child_items = list(
                        filter(lambda x: x['parent_id'] == item['id'], non_checked_items))

                    # Check if we need to (un)header entire item tree
                    header_all_in_i, unheader_all_in_i = check_header(item)

                    # Logic for applying and removing headers
                    if any([header_all_in_p, header_all_in_s, header_all_in_i]):
                        if item['content'][0] != '*':
                            item.update(content='* ' + item['content'])
                            for ci in child_items:
                                if not ci['content'].startswith('*'):
                                    ci.update(content='* ' + ci['content'])

                    if any([unheader_all_in_p, unheader_all_in_s]):
                        if item['content'][0] == '*':
                            item.update(content=item['content'][2:])
                    if unheader_all_in_i:
                        [ci.update(content=ci['content'][2:])
                         for ci in child_items]

                    # Logic for recurring lists
                    if not args.regeneration:
                        try:
                            # If old label is present, reset it
                            if item['r_tag'] == 1:
                                item['r_tag'] = 0
                                api.items.update(item['id'])
                        except:
                            pass

                    # If options turned on, start recurring lists logic
                    if args.regeneration is not None or args.end:
                        run_recurring_lists_logic(
                            args, api, item, child_items, child_items_all, regen_labels_id)

                    # If options turned on, start labelling logic
                    if label_id is not None:
                        # Skip processing an item if it has already been checked or is a header
                        if item['checked'] == 1:
                            continue
                        if item['content'].startswith('*'):
                            # Remove next action label if it's still present
                            remove_label(item, label_id, overview_item_ids,overview_item_labels)
                            continue

                        # Check item type
                        item_type, item_type_changed = get_item_type(
                            args, item, project_type)
                        if item_type is not None:
                            logging.debug('Identified \'%s\' as %s type',
                                        item['content'], item_type)

                        # Determine hierarchy types for logic
                        hierarchy_types = [item_type,
                                           section_type, project_type]
                        active_types = [type(x) != type(None)
                                        for x in hierarchy_types]

                        # If it is a parentless task
                        if item['parent_id'] == 0:
                            if active_types[0]:
                                # Do item types
                                active_type = item_type
                                add_label(
                                    item, label_id, overview_item_ids, overview_item_labels)

                            elif active_types[1]:
                                # Do section types
                                active_type = section_type

                                if section_type == 'sequential' or section_type == 's-p':
                                    if not first_found_section:
                                        add_label(
                                            item, label_id, overview_item_ids, overview_item_labels)
                                        first_found_section = True
                                elif section_type == 'parallel' or section_type == 'p-s':
                                    add_label(
                                        item, label_id, overview_item_ids, overview_item_labels)

                            elif active_types[2]:
                                # Do project types
                                active_type = project_type

                                if project_type == 'sequential' or project_type == 's-p':
                                    if not first_found_project:
                                        add_label(
                                            item, label_id, overview_item_ids, overview_item_labels)
                                        first_found_project = True

                                elif project_type == 'parallel' or project_type == 'p-s':
                                    add_label(
                                        item, label_id, overview_item_ids, overview_item_labels)

                            # Mark other conditions too
                            if first_found_section == False and active_types[1]:
                                first_found_section = True
                            if first_found_project is False and active_types[2]:
                                first_found_project = True

                        # If there are children
                        if len(child_items) > 0:
                            # Check if item state has changed, if so clean children for good measure
                            if item_type_changed == 1:
                                [remove_label(child_item, label_id, overview_item_ids, overview_item_labels)
                                    for child_item in child_items]

                            # If a sub-task, inherit parent task type
                            if item['parent_id'] !=0:
                                try:
                                    active_type = item['parent_type']      
                                except:
                                    pass 
                            
                            # Process sequential tagged items (item_type can overrule project_type)
                            if active_type == 'sequential' or active_type == 'p-s':
                                for child_item in child_items:
                                    
                                    # Ignore headered children
                                    if child_item['content'].startswith('*'):
                                        continue

                                    # Pass item_type down to the children
                                    child_item['parent_type'] = active_type
                                    # Pass label down to the first child
                                    if child_item['checked'] == 0 and label_id in item['labels']:
                                        add_label(
                                            child_item, label_id, overview_item_ids, overview_item_labels)
                                        remove_label(
                                            item, label_id, overview_item_ids, overview_item_labels)
                                    else:
                                        # Clean for good measure
                                        remove_label(
                                            child_item, label_id, overview_item_ids, overview_item_labels)

                            # Process parallel tagged items or untagged parents
                            elif active_type == 'parallel' or (active_type == 's-p' and label_id in item['labels']):
                                remove_label(
                                    item, label_id, overview_item_ids, overview_item_labels)
                                for child_item in child_items:

                                    # Ignore headered children
                                    if child_item['content'].startswith('*'):
                                        continue

                                    child_item['parent_type'] = active_type
                                    if child_item['checked'] == 0:
                                        # child_first_found = True
                                        add_label(
                                            child_item, label_id, overview_item_ids, overview_item_labels)

                        # Remove labels based on start / due dates

                        # If item is too far in the future, remove the next_action tag and skip
                        try:
                            if args.hide_future > 0 and 'due' in item.data and item['due'] is not None:
                                due_date = datetime.strptime(
                                    item['due']['date'][:10], "%Y-%m-%d")
                                future_diff = (
                                    due_date - datetime.today()).days
                                if future_diff >= args.hide_future:
                                    remove_label(
                                        item, label_id, overview_item_ids, overview_item_labels)
                                    continue
                        except:
                            # Hide-future not set, skip
                            continue

                        # If start-date has not passed yet, remove label
                        try:
                            f1 = item['content'].find('start=')
                            f2 = item['content'].find('start=due-')
                            if f1 > -1 and f2 == -1:
                                f_end = item['content'][f1+6:].find(' ')
                                if f_end > -1:
                                    start_date = item['content'][f1 +
                                                                 6:f1+6+f_end]
                                else:
                                    start_date = item['content'][f1+6:]

                                # If start-date hasen't passed, remove all labels
                                start_date = datetime.strptime(
                                    start_date, args.dateformat)
                                future_diff = (
                                    datetime.today()-start_date).days
                                if future_diff < 0:
                                    remove_label(
                                        item, label_id, overview_item_ids, overview_item_labels)
                                    [remove_label(child_item, label_id, overview_item_ids,
                                                  overview_item_labels) for child_item in child_items]
                                    continue

                        except:
                            logging.warning(
                                'Wrong start-date format for item: "%s". Please use "start=<DD-MM-YYYY>"', item['content'])
                            continue

                        # Recurring task friendly - remove label with relative change from due date
                        try:
                            f = item['content'].find('start=due-')
                            if f > -1:
                                f1a = item['content'].find(
                                    'd')  # Find 'd' from 'due'
                                f1b = item['content'].rfind(
                                    'd')  # Find 'd' from days
                                f2 = item['content'].find('w')
                                f_end = item['content'][f+10:].find(' ')

                                if f_end > -1:
                                    offset = item['content'][f+10:f+10+f_end-1]
                                else:
                                    offset = item['content'][f+10:-1]

                                try:
                                    item_due_date = item['due']['date'][:10]
                                    item_due_date = datetime.strptime(
                                        item_due_date, '%Y-%m-%d')
                                except:
                                    logging.warning(
                                        'No due date to determine start date for item: "%s".', item['content'])
                                    continue

                                if f1a != f1b and f1b > -1:  # To make sure it doesn't trigger if 'w' is chosen
                                    td = timedelta(days=int(offset))
                                elif f2 > -1:
                                    td = timedelta(weeks=int(offset))

                                # If we're not in the offset from the due date yet, remove all labels
                                start_date = item_due_date - td
                                future_diff = (
                                    datetime.today()-start_date).days
                                if future_diff < 0:
                                    remove_label(
                                        item, label_id, overview_item_ids, overview_item_labels)
                                    [remove_label(child_item, label_id, overview_item_ids,
                                                  overview_item_labels) for child_item in child_items]
                                    continue

                        except:
                            logging.warning(
                                'Wrong start-date format for item: %s. Please use "start=due-<NUM><d or w>"', item['content'])
                            continue

    return overview_item_ids, overview_item_labels

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
        '-pp', '--pp_suffix', help='change suffix for parallel-parallel labeling (default "//").', default='//')
    parser.add_argument(
        '-ss', '--ss_suffix', help='change suffix for sequential-sequential labeling (default "--").', default='--')
    parser.add_argument(
        '-ps', '--ps_suffix', help='change suffix for parallel-sequential labeling (default "/-").', default='/-')
    parser.add_argument(
        '-sp', '--sp_suffix', help='change suffix for sequential-parallel labeling (default "-/").', default='-/')
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
    api, label_id, regen_labels_id = initialise(args)

    # Start main loop
    while True:
        start_time = time.time()
        # sync(api)

        # Evaluate projects, sections, and items
        overview_item_ids, overview_item_labels = autodoist_magic(
            args, api, label_id, regen_labels_id)

        # Commit the queue with changes
        if label_id is not None:
            update_labels(api, label_id, overview_item_ids,
                          overview_item_labels)

        if len(api.queue):
            len_api_q = len(api.queue)
            api.commit()
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
