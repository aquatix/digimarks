"""
A setuptools based setup module.
See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

# To use a consistent encoding
from codecs import open as codecopen
from os import path

from setuptools import setup

here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
with codecopen(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='digimarks', # pip install digimarks
    description='Simple bookmarking service, using a SQLite database to store bookmarks, supporting tags, automatic '
                'title fetching and REST API calls.',
    #long_description=open('README.md', 'rt').read(),
    long_description=long_description,

    # version
    # third part for minor release
    # second when api changes
    # first when it becomes stable someday
    version='1.1.99',
    author='Michiel Scholten',
    author_email='michiel@diginaut.net',

    url='https://github.com/aquatix/digimarks',
    license='Apache',

    # as a practice no need to hard code version unless you know program wont
    # work unless the specific versions are used
    install_requires=['Flask', 'Peewee', 'requests', 'bs4'],

    py_modules=['digimarks'],

    zip_safe=True,
)
