digimarks
=========

|PyPI version| |PyPI downloads| |PyPI license| |Code health|

Simple bookmarking service, using a SQLite database to store bookmarks, supporting tags and automatic title fetching.


Installation
------------

From PyPI
~~~~~~~~~

Assuming you already are inside a virtualenv:

.. code-block:: bash

    pip install digimarks


From Git
~~~~~~~~

Create a new virtualenv (if you are not already in one) and install the
necessary packages:

.. code-block:: bash

    git clone https://github.com/aquatix/digimarks.git
    cd digimarks
    mkvirtualenv digimarks # or whatever project you are working on
    pip install -r requirements.txt


Usage
-----

Copy ``settings.py`` from example_config to the parent directory and
configure to your needs (*at the least* change the value of `SYSTEMKEY`).

Run digimarks as a service under nginx or apache and call the appropriate
url's when wanted.

Url's are of the form https://marks.example.com/<userkey>/<action>


Example configuration
---------------------

/<secretkey>/adduser


Server configuration
~~~~~~~~~~~~~~~~~~~~

* `vhost for Apache2.4`_
* `uwsgi.ini`_


What's new?
-----------

See the `Changelog`_.


.. _digimarks: https://github.com/aquatix/digimarks
.. _webhook: https://en.wikipedia.org/wiki/Webhook
.. |PyPI version| image:: https://img.shields.io/pypi/v/digimarks.svg
   :target: https://pypi.python.org/pypi/digimarks/
.. |PyPI downloads| image:: https://img.shields.io/pypi/dm/digimarks.svg
   :target: https://pypi.python.org/pypi/digimarks/
.. |PyPI license| image:: https://img.shields.io/github/license/aquatix/digimarks.svg
   :target: https://pypi.python.org/pypi/digimarks/
.. |Code health| image:: https://landscape.io/github/aquatix/digimarks/master/landscape.svg?style=flat
   :target: https://landscape.io/github/aquatix/digimarks/master
   :alt: Code Health
.. _hook settings: https://github.com/aquatix/digimarks/blob/master/example_config/examples.yaml
.. _vhost for Apache2.4: https://github.com/aquatix/digimarks/blob/master/example_config/apache_vhost.conf
.. _uwsgi.ini: https://github.com/aquatix/digimarks/blob/master/example_config/uwsgi.ini
.. _Changelog: https://github.com/aquatix/digimarks/blob/master/CHANGELOG.md