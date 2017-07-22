"""
A setuptools based setup module.
See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

from setuptools import setup
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='digimarks', # pip install digimarks
    description='Simple bookmarking service, using a SQLite database to store bookmarks, supporting tags and automatic title fetching.',
    #long_description=open('README.md', 'rt').read(),
    long_description=long_description,

    # version
    # third part for minor release
    # second when api changes
    # first when it becomes stable someday
    version='1.1.0',
    author='Michiel Scholten',
    author_email='michiel@diginaut.net',

    url='https://github.com/aquatix/digimarks',
    license='Apache',

    # as a practice no need to hard code version unless you know program wont
    # work unless the specific versions are used
    install_requires=['Flask', 'Peewee', 'Flask-Peewee', 'requests'],

    py_modules=['digimarks'],

    zip_safe=True,
)
