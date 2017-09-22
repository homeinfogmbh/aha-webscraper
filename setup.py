#! /usr/bin/env python3

from distutils.core import setup


setup(
    name='aha',
    version='latest',
    author='HOMEINFO - Digitale Informationssysteme GmbH',
    requires=['bs4', 'requests'],
    py_modules=['aha'],
    description=(
        'AHA Region Hannover garbage collection dates web scraping API.'))
