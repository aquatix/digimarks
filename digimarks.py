import datetime
import hashlib
import os
import subprocess

from flask import Flask, abort, redirect, render_template, request
from flask_peewee.db import Database
from flask_peewee.utils import object_list
from peewee import *

# app configuration
APP_ROOT = os.path.dirname(os.path.realpath(__file__))
MEDIA_ROOT = os.path.join(APP_ROOT, 'static')
MEDIA_URL = '/static/'
DATABASE = {
    'name': os.path.join(APP_ROOT, 'bookmarks.db'),
    'engine': 'peewee.SqliteDatabase',
}
PASSWORD = 'shh'
PHANTOM = '/usr/local/bin/phantomjs'
SCRIPT = os.path.join(APP_ROOT, 'screenshot.js')

# create our flask app and a database wrapper
app = Flask(__name__)
app.config.from_object(__name__)
db = Database(app)


class User(db.Model):
    username = CharField()
    key = CharField()
    created_date = DateTimeField(default=datetime.datetime.now)


class Bookmark(db.Model):
    title = CharField()
    url = CharField()
    created_date = DateTimeField(default=datetime.datetime.now)
    #image = CharField(default='')
    tags = CharField()

    class Meta:
        ordering = (('created_date', 'desc'),)

    #def fetch_image(self):
    #    url_hash = hashlib.md5(self.url).hexdigest()
    #    filename = 'bookmark-%s.png' % url_hash

    #    outfile = os.path.join(MEDIA_ROOT, filename)
    #    params = [PHANTOM, SCRIPT, self.url, outfile]

    #    exitcode = subprocess.call(params)
    #    if exitcode == 0:
    #        self.image = os.path.join(MEDIA_URL, filename)


@app.route('/')
def index():
    return object_list('index.html', Bookmark.select())

@app.route('/<userkey>/')
def bookmarks(userkey):
    return object_list('bookmarks.html', Bookmark.select())

@app.route('/<userkey>/add/')
def add(userkey):
    password = request.args.get('password')
    if password != PASSWORD:
        abort(404)

    url = request.args.get('url')
    title = 'Temp'
    tags = ''
    if url:
        bookmark = Bookmark(url=url, title=title, tags=tags)
        #bookmark.fetch_image()
        bookmark.save()
        return redirect(url)
    abort(404)

if __name__ == '__main__':
    # create the bookmark table if it does not exist
    Bookmark.create_table(True)

    # run the application
    app.run(port=9999)
