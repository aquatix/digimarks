# Virtualenv to use with the wsgi file
VENV = '/srv/marks.example.com/venv/bin/activate_this.py'

PORT = 8086

DEBUG = False

# Password/url key to do admin stuff with, like adding a user
SYSTEMKEY = 'S3kr1t'

LOG_LOCATION = 'digimarks.log'
#LOG_LOCATION = '/var/log/digimarks/digimarks.log'
# How many logs to keep in log rotation:
LOG_BACKUP_COUNT = 10
