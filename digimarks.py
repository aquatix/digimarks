import datetime
import hashlib
import os
import subprocess

from utilkit import datetimeutil

from flask import Flask, abort, redirect, render_template, request
from flask_peewee.db import Database
from flask_peewee.utils import object_list
from peewee import *

try:
    import settings
except ImportError:
    print('Copy settings_example.py to settings.py and set the configuration to your own preferences')
    sys.exit(1)

# app configuration
APP_ROOT = os.path.dirname(os.path.realpath(__file__))
MEDIA_ROOT = os.path.join(APP_ROOT, 'static')
MEDIA_URL = '/static/'
DATABASE = {
    'name': os.path.join(APP_ROOT, 'bookmarks.db'),
    'engine': 'peewee.SqliteDatabase',
}
#PASSWORD = 'shh'
#PHANTOM = '/usr/local/bin/phantomjs'
#SCRIPT = os.path.join(APP_ROOT, 'screenshot.js')

# create our flask app and a database wrapper
app = Flask(__name__)
app.config.from_object(__name__)
db = Database(app)


def getkey():
    return os.urandom(24).encode('hex')


class User(db.Model):
    """ User account """
    username = CharField()
    key = CharField()
    created_date = DateTimeField(default=datetime.datetime.now)


class Bookmark(db.Model):
    """ Bookmark instance, connected to User """
    # Foreign key to User
    userkey = CharField()

    title = CharField()
    url = CharField()
    created_date = DateTimeField(default=datetime.datetime.now)
    modified_date = DateTimeField(null=True)
    #image = CharField(default='')
    url_hash = CharField()
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

    def sethash(self):
        """ Generate hash """
        self.url_hash = hashlib.md5(self.url).hexdigest()


    def to_dict(self):
        result = {
                'title': self.title,
                'url': self.url,
                'created':  datetimeutil.datetime_to_string(self.created_date),
                'url_hash': self.url_hash,
                'tags': self.tags,
                }
        return result


@app.route('/')
def index():
    """ Homepage, point visitors to project page """
    return object_list('index.html', Bookmark.select())


@app.route('/<userkey>/')
@app.route('/<userkey>')
def bookmarks(userkey):
    """ User homepage, list their (unfiltered) bookmarks """
    return object_list('bookmarks.html', Bookmark.select())


@app.route('/<userkey>/<urlhash>')
def viewbookmark(urlhash):
    """ Bookmark detail view """
    # bookmark = getbyurlhash()
    return render_template('viewbookmark.html')


@app.route('/<userkey>/<urlhash>/json')
def viewbookmarkjson(urlhash):
    """ Serialise bookmark to json """
    # bookmark = getbyurlhash()
    return bookmark


@app.route('/<userkey>/edit/<urlhash>')
def editbookmark(urlhash):
    """ Bookmark edit form """
    # bookmark = getbyurlhash()
    return render_template('edit.html')


@app.route('/<userkey>/add')
def addbookmark():
    """ Bookmark add form """
    bookmark = Bookmark()
    return render_template('edit.html')


@app.route('/<userkey>/add/')
def adding(userkey):
    password = request.args.get('password')
    if password != PASSWORD:
        abort(404)

    url = request.args.get('url')
    title = 'Temp'
    tags = ''
    if url:
        bookmark = Bookmark(url=url, title=title, tags=tags)
        bookmark.sethash()
        #bookmark.fetch_image()
        bookmark.save()
        return redirect(url)
    abort(404)


@app.route('/<systemkey>/adduser')
def adduser(systemkey):
    """ Add user endpoint, convenience """
    if systemkey == settings.SYSTEMKEY:
        newuser = User()
        newuser.key = getkey()
        newuser.username = 'Nomen Nescio'
        newuser.save()
        return redirect('/' + newuser.key, code=302)
    else:
        abort(404)



if __name__ == '__main__':
    # create the bookmark table if it does not exist
    Bookmark.create_table(True)
    User.create_table(True)

    # run the application
    app.run(port=9999)
