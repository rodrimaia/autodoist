# Autodoist

*Note: v2.0 is a major overhaul of Autodoist, so please be sure to view the README in order to get up to speed with the latest changes. Thanks to everyone for helping out and supporting this project!*

This program adds four major functionalities to Todoist to help automate your workflow:

1) Assign automatic `@next_action` labels for a more GTD-like workflow
   - Flexible options to label tasks sequentially or in parallel
   - Limit labels based on a start-date or hide future tasks based on the due date
2) [Temporary disabled] Enable regeneration of sub-tasks in lists with a recurring date. Multiple modes possible.
3) Postpone the end-of-day time to after midnight to finish your daily recurring tasks
4) Make multiple tasks (un)checkable at the same time

If this tool helped you out, I would really appreciate your support by providing me with some coffee!

<a href=https://ko-fi.com/hoffelhas>
 <img src="https://i.imgur.com/MU1rAPG.png" width="150">
</a>

# Requirements

Autodoist has been build with Python 3.11.1, which is the recommended version. Older versions of 3.x should be compatible, however be aware that they have not been tested.

To run Autodoist the following packages are required:
* ```todoist-python```
* ```requests```

For your convenience a requirements.txt is provided, which allows you to install them by using pip:

`pip install -r requirements.txt`

# 1. Automatic next action labels

The program looks for pre-defined tags in the name of every project, section, or parentless tasks in your Todoist account to automatically add and remove `@next_action` labels.

Projects, sections, and parentless tasks can be tagged independently of each other to create the required functionality. If this tag is not defined, it will not activate this functionality. The result will be a clear, current and comprehensive list of next actions without the need for further thought.

See the example given at [running Autodoist](#running-autodoist) on how to run this mode. If the label does not exist yet in your Todoist, a possibility is given to automatically create it.

## Useful filter tip

For a more GTD-like workflow, you can use Todoist filters to create a clean and cohesive list that only contains your actionable tasks. As a simple example, you could use the following filter:

`@next_action & #PROJECT_NAME`

## Sequential processing

If a project, section, or parentless task ends with a dash `-`, the tasks will be treated sequentially in a priority queue, where only the first task that is found is labeled. If a task contains sub-tasks, the first lowest task is labeled instead.

![Sequential task labeling](https://i.imgur.com/ZUKbA8E.gif)

## Parallel processing

If a project, section, or parentless task name ends with an equal sign `=`, all tasks will be treated in parallel. A waterfall processing is applied, where the lowest possible (sub-)tasks are labelled.

![Parallel task labeling](https://i.imgur.com/xZZ0kEM.gif)

## Advanced labelling

Projects, sections, and (parentless) tasks can be used to specify how the levels under them should behave. This means that:

- A project can accept up to three tags, to specify how the sections, parentless tasks, and subtasks should behave.
- A section can accept up to two tags, to specify parentless tasks and subtasks should behave.
- A task at any level can be labelled with one tag, to specify how its sub-tasks should behave.

Tags can be applied on each level simultaneously, where the lower level setting will always override the one specified in the levels above.

### Shorthand notation

If fewer tags then needed are specified, the last one is simply copied. E.g. if a project has the tag `=` this is similar to `===`, or if a project has `=-` this is similar to `=--`. Same for sections, `=` is similar to `==`.

### Project labeling examples
- If a project ends with `---`, only the first section has tasks that are handled sequentially.
- If a project ends with `=--`, all sections have tasks that are handled sequentially.
- If a project ends with `-=-`, only the first section has parallel parentless tasks with sequential sub-tasks.
- If a project ends with `--=`, only the first section and first parentless tasks has parallel sub-tasks.
- If a project ends with `==-`, all sections and all parentless tasks will have sub-tasks are handled sequentially.
- If a project ends with `=-=`, all sections will have parentless tasks that are processed sequentially, but all sub-tasks are handled in parallel.
- If a project ends with `-==`, only the first section has parallel tasks.
- If a project ends with `===`, all tasks are handled in parallel.

### Section labeling examples
- If a section ends with `--`, only the first parentless task will have sub-tasks that are handled sequentially.
- If a section ends with `=-`, all parentless tasks will have sub-tasks that are handled sequentially.
- If a section ends with `-=`, only the first parentless task has sub-tasks that are handled in parallel.
- If a section ends with `==`, all tasks are handled in parallel.

### Tasks labeling examples
- If a task ends with `-`, the sub-tasks are handled sequentially.
- If a task ends with `=`, the sub-tasks are handled in parallel.

### Kanban board labeling
A standard workflow for Kanban boards is to have one actionable task per column/section, which is then moved to the next column when needed. Most often, the most right column is the 'done' section. To ensure that every column only has one labelled task and the last column contains no labelled tasks, you could do either of two things:
- Add the `=--` tag to the project name, and disable labelling for the 'done' section by adding `*` to either the start or end of the section name.
- Add the `--` tag to every section that you want to have labels.


## Start/Due date enhanced experience

Two methods are provided to hide tasks that are not relevant yet.

- Prevent labels by defining a start-date that is added to the task itself. The label is only assigned if this date is reached. You can define the start-date by adding 'start=DD-MM-YYYY'. On the other hand, the start date can be defined as several days or weeks before the due-date by using either 'start=due-<NUMBER_OF_DAYS>d' or 'start=due-<NUMBER_OF_WEEKS>w'. This is especially useful for recurring tasks!
   [See an example of using start-dates](https://i.imgur.com/WJRoJzW.png).

- Prevent labels of all tasks if the due date is too far in the future. Define the amount by running with the argument '-hf <NUMBER_OF_DAYS>'.
[See an example of the hide-future functionality](https://i.imgur.com/LzSoRUm.png).

# 2. Regenerate sub-tasks in recurring lists

*DISCLAIMER: This feature has been disabled for now due to two reasons:*
- *Regeneration is a [core feature of Todoist nowadays](https://todoist.com/help/articles/can-i-reset-sub-tasks). This was made possible thanks to all of you who are using and supporting Autodoist, which resulted in Doist to include this too! Thank you all for making this happen!*
- *In the new REST API v2 it's currently not possible to see completed tasks, which makes regeneration a bit difficult.*

*Nevertheless, the Todoist implementation is still more limited than Autodoist, it does not restore the original order of the sub-tasks, and deeper sub-tasks can't be reset. I therefore believe it is still useful for this feature to be re-enabled in the near future.*

Autodoist looks for all parentless tasks with a recurring date. If they contain sub-tasks, they will be regenerated in the same order when the parentless task is checked.

![See example](https://i.imgur.com/WKKd14o.gif)

To give you more flexibility, multiple modes are provided:
1. No regeneration
2. Checking the main task regenerates all sub-tasks
3. Checking the main task regenerates all sub-tasks only if all sub-tasks have been checked first

When this functionality is activated, it is possible to chose which mode is used as overall functionality for your Todoist. See the example given at [running Autodoist](#running-autodoist).

In addition you can override the overall mode by adding the labels `Regen_off`, `Regen_all`, or `Regen_all_if_completed` to one of your main recurring task. These labels will automatically be created for you.

# 3. Postpone the end-of-day

You have a daily recurring task, but you're up working late and now it's past midnight. When this happens, Todoist will automatically mark it overdue and when checked by you it moves to tomorrow. This means that after a good night's rest you can't complete the task that day!

By setting an alternative time for the end-of-day you can now finish your work after midnight and the new date will automatically be corrected for you.

![See example 1](https://i.imgur.com/tvnTMOJ.gif)

# 4. Make multiple tasks uncheckable / re-checkable at the same time

Todoist allows the asterisk symbol `* ` to be used to ensure tasks can't be checked by turning them into headers. Now you are able to do this en masse!

Simply add `** ` or `-* ` in front of a project, section, or parentless task to automatically turn all the tasks that it includes into respectively headers or checkable tasks.

# Executing Autodoist

You can run Autodoist from any system that supports Python.

## Running Autodoist

Autodoist will read your environment to retrieve your Todoist API key and additional arguments. In order to run on Windows/Linux/Mac OSX you can use the following command lines.
    
If you want to enable labelling mode, run with the `-l` argument:

    python autodoist.py -a <API Key> -l <LABEL_NAME>
    
If you want to enable regeneration of sub-tasks in recurring lists, run with the `-r` argument followed by a mode number for the overall functionality (1: no regeneration, 2: regenerate all, 3: regenerate only if all sub-tasks are completed):

    python autodoist.py -a <API Key> -r <NUMBER>
    
If you want to enable an alternative end-of-day, run with the `-e` argument and a number from 1 to 24 to specify which hour:

    python autodoist.py -a <API Key> -e <NUMBER>
    
These modes can be run individually, or combined with each other.

## Additional arguments

Several additional arguments can be provided, for example to change the suffix tags for parallel and sequential projects:

    python autodoist.py --p_suffix <tag>
    python autodoist.py --s_suffix <tag>
    
Note: Be aware that Todoist sections don't like to have a slash '/' in the name, which will automatically change to an underscore. Detection of the tag will not work. 
    
If you want to hide all tasks due in the future:

    python autodoist.py --hf <NUMBER_OF_DAYS>

In addition, if you experience issues with syncing you can increase the api syncing time (default 5 seconds):
    
    python autodoist.py --delay <time in seconds>

For all arguments, please check out the help:

    python autodoist.py --help


## Docker container

To build the docker container, check out the repository and run:

    docker build . --tag autodoist:latest

To run autodoist inside the docker container:

    docker run -it autodoist:latest
