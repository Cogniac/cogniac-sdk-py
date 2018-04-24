#!/usr/bin/env python

from distutils.core import setup

setup(name='cogniac',
      version='1.5.16',
      description='Python SDK for Cogniac Public API',
      packages=['cogniac'],
      author = 'Cogniac Corporation',
      author_email = 'support@cogniac.co',
      url = 'https://github.com/Cogniac/cogniac-sdk-py',
      scripts=['bin/icogniac', 'bin/cogupload'],
      install_requires=['requests', 'retrying', 'tabulate'])
