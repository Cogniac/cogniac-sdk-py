#!/usr/bin/env python

from setuptools import setup

setup(name='cogniac',
      version='3.0.0',
      description='Python SDK for Cogniac Public API',
      packages=['cogniac'],
      author = 'Cogniac Corporation',
      author_email = 'support@cogniac.co',
      url = 'https://github.com/Cogniac/cogniac-sdk-py',
      scripts=['bin/icogniac', 'bin/cogupload', 'bin/cogstats'],
      entry_points={
          'console_scripts': [
              'cogniac=cogniac.cli:main',
          ],
      },
      python_requires='>=3.11',
      install_requires=['httpx>=0.24.0', 'tenacity>=8.0.0', 'tabulate'])
