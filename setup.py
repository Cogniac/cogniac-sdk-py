#!/usr/bin/env python

from setuptools import setup

setup(name='cogniac',
      version='2.0.18',
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
      install_requires=['requests', 'retrying', 'tabulate', 'six'])
