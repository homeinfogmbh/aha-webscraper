#! /usr/bin/env python3

from setuptools import setup


setup(
    name='aha',
    use_scm_version={
        "local_scheme": "node-and-timestamp"
    },
    setup_requires=['setuptools_scm'],
    install_requires=['beautifulsoup4', 'requests'],
    author='HOMEINFO - Digitale Informationssysteme GmbH',
    author_email='<info at homeinfo dot de>',
    maintainer='Richard Neumann',
    maintainer_email='<r dot neumann at homeinfo priod de>',
    packages=['aha'],
    entry_points={
        'console_scripts': [
            'aha-dates = aha.api:main'
        ]
    },
    license='GPLv3',
    description='Webscraper for garbage disposal dates of AHA Region Hannover.'
)
