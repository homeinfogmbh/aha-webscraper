#! /usr/bin/env python3

from distutils.core import setup


setup(
    name='aha',
    version='latest',
    author='HOMEINFO - Digitale Informationssysteme GmbH',
    requires=['requests', 'bs4', 'html5lib'],
    py_modules=['aha'],
    scripts=['aha-pickups'],
    description=(
        'AHA Region Hannover garbage collection dates web scraping API.'))
