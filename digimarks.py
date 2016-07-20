import datetime
import hashlib
import os
import sys
import requests
import shutil
import bs4
from urlparse import urlparse

from utilkit import datetimeutil

from flask import Flask, abort, redirect, render_template, request, url_for
from flask_peewee.db import Database
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
#PHANTOM = '/usr/local/bin/phantomjs'
#SCRIPT = os.path.join(APP_ROOT, 'screenshot.js')

# create our flask app and a database wrapper
app = Flask(__name__)
app.config.from_object(__name__)
db = Database(app)

# set custom url for the app, for example '/bookmarks'
try:
    app.config['APPLICATION_ROOT'] = settings.APPLICATION_ROOT
except AttributeError:
    pass


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

    # Website favicon - http://codingclues.eu/2009/retrieve-the-favicon-for-any-url-thanks-to-google/
    favicon = CharField(null=True)

    # Status code: 200 is OK, 404 is not found, for example (showing an error)
    http_status = IntegerField(default=200)


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

    def set_hash(self):
        """ Generate hash """
        self.url_hash = hashlib.md5(self.url).hexdigest()


    def set_title_from_source(self):
        """ Request the title by requesting the source url """
        result = requests.get(self.url)
        print result.status_code
        if result.status_code == 200:
            html = bs4.BeautifulSoup(result.text, 'html.parser')
            self.title = html.title.text.strip()
        else:
            self.http_status = result.status_code
        return self.title


    def set_status_code(self):
        """ Check the HTTP status of the url, as it might not exist for example """
        result = requests.head(self.url)
        self.http_status = result.status_code
        return self.http_status


    def set_favicon(self):
        """ Fetch favicon for the domain """
        u = urlparse(self.url)
        domain = u.netloc
        filename = os.path.join(MEDIA_ROOT, 'favicons/' + domain + '.png')
        response = requests.get('http://www.google.com/s2/favicons?domain=' + domain, stream=True)
        with open(filename, 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)
        del response
        self.favicon = domain + '.png'


    def to_dict(self):
        result = {
                'title': self.title,
                'url': self.url,
                'created':  datetimeutil.datetime_to_string(self.created_date),
                'url_hash': self.url_hash,
                'tags': self.tags,
                }
        return result


def get_tags_for_user(userkey):
    """ Extract all tags from the bookmarks """
    bookmarks = Bookmark.select(Bookmark.userkey == userkey)
    tags = []
    for bookmark in bookmarks:
        these_tags = bookmark.tags.split(',')
        print these_tags
    return tags


@app.route('/')
def index():
    """ Homepage, point visitors to project page """
    return render_template('index.html')


@app.route('/<userkey>/')
@app.route('/<userkey>')
def bookmarks(userkey):
    """ User homepage, list their (unfiltered) bookmarks """
    #return object_list('bookmarks.html', Bookmark.select())
    #user = User.select(key=userkey)
    #if user:
    #    bookmarks = Bookmark.select(User=user)
    #    return render_template('bookmarks.html', bookmarks)
    #else:
    #    abort(404)
    bookmarks = Bookmark.select().where(Bookmark.userkey == userkey)
    return render_template('bookmarks.html', bookmarks=bookmarks, userkey=userkey)



#@app.route('/<userkey>/<urlhash>')
#def viewbookmark(userkey, urlhash):
#    """ Bookmark detail view """
#    bookmark = Bookmark.select(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey)
#    return render_template('viewbookmark.html', userkey=userkey, bookmark=bookmark)


@app.route('/<userkey>/<urlhash>/json')
def viewbookmarkjson(userkey, urlhash):
    """ Serialise bookmark to json """
    bookmark = Bookmark.select(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey)
    return bookmark.to_dict()


@app.route('/<userkey>/<urlhash>')
@app.route('/<userkey>/<urlhash>/edit')
def editbookmark(userkey, urlhash):
    """ Bookmark edit form """
    # bookmark = getbyurlhash()
    bookmark = Bookmark.get(Bookmark.url_hash == urlhash)
    print bookmark.url
    return render_template('edit.html', action='Edit bookmark', userkey=userkey, bookmark=bookmark)


@app.route('/<userkey>/add')
def addbookmark(userkey):
    """ Bookmark add form """
    bookmark = Bookmark(title='', url='', tags='')
    return render_template('edit.html', action='Add bookmark', userkey=userkey, bookmark=bookmark)


@app.route('/<userkey>/adding', methods=['GET', 'POST'])
#@app.route('/<userkey>/adding')
def addingbookmark(userkey):
    """ Add the bookmark from form submit by /add """

    if request.method == 'POST':
        title = request.form['title']
        url = request.form['url']
        tags = request.form['tags']
        if url:
            bookmark = Bookmark(url=url, title=title, tags=tags, userkey=userkey)
            bookmark.set_hash()
            #bookmark.fetch_image()
            if not title:
                # Title was empty, automatically fetch it from the url, will also update the status code
                bookmark.set_title_from_source()
            else:
                bookmark.set_status_code()

            if bookmark.http_status == 200:
                bookmark.set_favicon()

            bookmark.save()
            #return redirect(url)
            return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash))
        abort(404)
    return redirect(url_for('add'))


@app.route('/<userkey>/<urlhash>/delete', methods=['GET', 'POST'])
def deletingbookmark(userkey, urlhash):
    """ Delete the bookmark from form submit by <urlhash>/delete """
    # TODO implement
    return redirect(url_for('bookmarks', userkey=userkey))


@app.route('/<userkey>/tags')
def tags(userkey):
    """ Overview of all tags used by user """
    tags = get_tags_for_user(userkey)
    return render_template('tags.html', tags=tags, userkey=userkey)


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

    users = User.select()
    print 'Current user keys:'
    for user in users:
        print user.key

    # run the application
    app.run(port=9999, debug=True)
