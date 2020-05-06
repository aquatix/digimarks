# Virtualenv to use with the wsgi file (optional)
VENV = '/srv/marks.example.com/venv/bin/activate_this.py'

PORT = 8086

DEBUG = False

# Password/url key to do admin stuff with, like adding a user
# NB: change this to something else! For example, in bash:
# echo -n "yourstring" | sha1sum
SYSTEMKEY = 'S3kr1t'

# RapidAPI key for favicons
# https://rapidapi.com/realfavicongenerator/api/realfavicongenerator
MASHAPE_API_KEY = 'your_MASHAPE_key'

LOG_LOCATION = 'digimarks.log'
#LOG_LOCATION = '/var/log/digimarks/digimarks.log'
# How many logs to keep in log rotation:
LOG_BACKUP_COUNT = 10
