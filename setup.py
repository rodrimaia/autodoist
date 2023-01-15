from setuptools import setup

setup(
    name='autodoist',
    version='2.0',
    py_modules=['autodoist'],
    url='https://github.com/Hoffelhas/automation-todoist',
    license='MIT',
    author='Alexander Haselhoff',
    author_email='xela@live.nl',
    description='Added functionality for Todoist: 1) next-action labels, 2) sub-task regeneration, 3) postpone end of day, and 4) (un)header items simultaneously)',
    install_requires=[
        'todoist-python',
        'requests',
    ]
)
