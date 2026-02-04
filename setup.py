#!/usr/bin/env python3
"""Setup configuration for issue-bot package."""

from setuptools import setup, find_packages

with open('requirements.txt') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name='openwisp-utils',
    version='1.0.0',
    description='Issue Assignment Bot - Automated issue assignment and PR management',
    author='OpenWISP',
    packages=find_packages(),
    install_requires=requirements,
    extras_require={
        'github_actions': requirements,
    },
    python_requires='>=3.8',
    entry_points={
        'console_scripts': [
            'issue-assignment-bot=openwisp_utils.issue_assignment_bot:main',
        ],
    },
)
