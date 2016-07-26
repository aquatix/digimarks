import datetime
import hashlib
import os
import sys
import requests
import shutil
import bs4
from more_itertools import unique_everseen
from urlparse import urlparse

from utilkit import datetimeutil

from flask import Flask, abort, redirect, render_template, request, url_for
from flask_peewee.db import Database
#from flask_peewee.utils import get_object_or_404
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

# Cache the tags
all_tags = {}


def clean_tags(tags_list):
    tags_res = [x.strip() for x in tags_list]
    tags_res = list(unique_everseen(tags_res))
    tags_res.sort()
    if tags_res and tags_res[0] == '':
        del tags_res[0]
    return tags_res


class User(db.Model):
    """ User account """
    username = CharField()
    key = CharField()
    created_date = DateTimeField(default=datetime.datetime.now)

    def generate_key(self):
        """ Generate userkey """
        self.key = os.urandom(24).encode('hex')
        return self.key


class Bookmark(db.Model):
    """ Bookmark instance, connected to User """
    # Foreign key to User
    userkey = CharField()

    title = CharField(default='')
    url = CharField()
    #image = CharField(default='')
    url_hash = CharField(default='')
    tags = CharField(default='')
    starred = BooleanField(default=False)

    # Website (domain) favicon
    favicon = CharField(null=True)

    # Status code: 200 is OK, 404 is not found, for example (showing an error)
    http_status = IntegerField(default=200)

    created_date = DateTimeField(default=datetime.datetime.now)
    modified_date = DateTimeField(null=True)
    deleted_date = DateTimeField(null=True)

    # Bookmark status; deleting doesn't remove from DB
    VISIBLE = 0
    DELETED = 1
    status = IntegerField(default=VISIBLE)


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
        try:
            result = requests.get(self.url)
            self.http_status = result.status_code
        except:
            # For example 'MissingSchema: Invalid URL 'abc': No schema supplied. Perhaps you meant http://abc?'
            self.http_status = 404
        if self.http_status == 200:
            html = bs4.BeautifulSoup(result.text, 'html.parser')
            try:
                self.title = html.title.text.strip()
            except AttributeError:
                self.title = ''
        return self.title

    def set_status_code(self):
        """ Check the HTTP status of the url, as it might not exist for example """
        result = requests.head(self.url)
        self.http_status = result.status_code
        return self.http_status

    def set_favicon(self):
        """ Fetch favicon for the domain """
        # http://codingclues.eu/2009/retrieve-the-favicon-for-any-url-thanks-to-google/
        u = urlparse(self.url)
        domain = u.netloc
        filename = os.path.join(MEDIA_ROOT, 'favicons/' + domain + '.png')
        # if file exists, don't re-download it
        response = requests.get('http://www.google.com/s2/favicons?domain=' + domain, stream=True)
        with open(filename, 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)
        del response
        self.favicon = domain + '.png'

    def set_tags(self, tags):
        """ Set tags from `tags`, strip and sort them """
        tags_split = tags.split(',')
        tags_clean = clean_tags(tags_split)
        self.tags = ','.join(tags_clean)

    @property
    def tags_list(self):
        """ Get the tags as a list, iterable in template """
        if self.tags:
            return self.tags.split(',')
        else:
            return []


    def to_dict(self):
        result = {
                'title': self.title,
                'url': self.url,
                'created':  datetimeutil.datetime_to_string(self.created_date),
                'url_hash': self.url_hash,
                'tags': self.tags,
                }
        return result


class PublicTag(db.Model):
    """ Publicly shared tag """
    tagkey = CharField()
    userkey = CharField()
    tag = CharField()
    created_date = DateTimeField(default=datetime.datetime.now)

    def generate_key(self):
        """ Generate hash-based key for publicly shared tag """
        self.tagkey = os.urandom(16).encode('hex')


def get_tags_for_user(userkey):
    """ Extract all tags from the bookmarks """
    bookmarks = Bookmark.select().filter(Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE)
    tags = []
    for bookmark in bookmarks:
        tags += bookmark.tags_list
    return clean_tags(tags)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.route('/')
def index():
    """ Homepage, point visitors to project page """
    return render_template('index.html')


@app.route('/<userkey>', methods=['GET', 'POST'])
@app.route('/<userkey>/sort/<sortmethod>', methods=['GET', 'POST'])
def bookmarks(userkey, sortmethod = None):
    """ User homepage, list their bookmarks, optionally filtered and/or sorted """
    #return object_list('bookmarks.html', Bookmark.select())
    #user = User.select(key=userkey)
    #if user:
    #    bookmarks = Bookmark.select(User=user)
    #    return render_template('bookmarks.html', bookmarks)
    #else:
    #    abort(404)
    message = request.args.get('message')
    if request.method == 'POST':
        filter_on = request.form['filter']
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.title.contains(filter_on),
                                            Bookmark.status == Bookmark.VISIBLE).order_by(Bookmark.created_date.desc())
        return render_template('bookmarks.html', bookmarks=bookmarks, userkey=userkey, tags=all_tags[userkey], filter=filter_on, message=message)
    else:
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE).order_by(Bookmark.created_date.desc())
        return render_template('bookmarks.html', bookmarks=bookmarks, userkey=userkey, tags=all_tags[userkey], message=message)



#@app.route('/<userkey>/<urlhash>')
#def viewbookmark(userkey, urlhash):
#    """ Bookmark detail view """
#    bookmark = Bookmark.select(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey)
#    return render_template('viewbookmark.html', userkey=userkey, bookmark=bookmark)


@app.route('/<userkey>/<urlhash>/json')
def viewbookmarkjson(userkey, urlhash):
    """ Serialise bookmark to json """
    bookmark = Bookmark.select(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE)
    return bookmark.to_dict()


@app.route('/<userkey>/<urlhash>')
@app.route('/<userkey>/<urlhash>/edit')
def editbookmark(userkey, urlhash):
    """ Bookmark edit form """
    # bookmark = getbyurlhash()
    bookmark = Bookmark.get(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey)
    message = request.args.get('message')
    return render_template('edit.html', action='Edit bookmark', userkey=userkey, bookmark=bookmark, message=message, formaction='edit')


@app.route('/<userkey>/add')
def addbookmark(userkey):
    """ Bookmark add form """
    bookmark = Bookmark(title='', url='', tags='')
    return render_template('edit.html', action='Add bookmark', userkey=userkey, bookmark=bookmark)


def updatebookmark(userkey, request, urlhash = None):
    """ Add (no urlhash) or edit (urlhash is set) a bookmark """
    title = request.form.get('title')
    url = request.form.get('url')
    tags = request.form.get('tags')
    starred = False
    if request.form.get('starred'):
        starred = True

    if url and not urlhash:
        # New bookmark
        bookmark, created = Bookmark.get_or_create(url=url, userkey=userkey)
        if not created:
            message = 'Existing bookmark, did not overwrite with new values'
            return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash, message=message))
    elif url:
        # Existing bookmark, get from DB
        bookmark = Bookmark.get(userkey == userkey, Bookmark.url_hash == urlhash)
        # Editing this bookmark, set modified_date to now
        bookmark.modified_date = datetime.datetime.now()

    bookmark.title = title
    bookmark.url = url
    bookmark.starred = starred
    bookmark.set_tags(tags)
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
    return bookmark


@app.route('/<userkey>/adding', methods=['GET', 'POST'])
#@app.route('/<userkey>/adding')
def addingbookmark(userkey):
    """ Add the bookmark from form submit by /add """

    if request.method == 'POST':
        bookmark = updatebookmark(userkey, request)
        if type(bookmark).__name__ == 'Response':
            return bookmark
        all_tags[userkey] = get_tags_for_user(userkey)
        return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash))
    return redirect(url_for('add'))


@app.route('/<userkey>/<urlhash>/editing', methods=['GET', 'POST'])
def editingbookmark(userkey, urlhash):
    """ Edit the bookmark from form submit """

    if request.method == 'POST':
        bookmark = updatebookmark(userkey, request, urlhash=urlhash)
        all_tags[userkey] = get_tags_for_user(userkey)
        return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash))
    return redirect(url_for('add'))


@app.route('/<userkey>/<urlhash>/delete', methods=['GET', 'POST'])
def deletingbookmark(userkey, urlhash):
    """ Delete the bookmark from form submit by <urlhash>/delete """
    query = Bookmark.update(status=Bookmark.DELETED).where(Bookmark.userkey==userkey, Bookmark.url_hash==urlhash)
    query.execute()
    query = Bookmark.update(deleted_date = datetime.datetime.now()).where(Bookmark.userkey==userkey, Bookmark.url_hash==urlhash)
    query.execute()
    message = 'Bookmark deleted'
    all_tags[userkey] = get_tags_for_user(userkey)
    return redirect(url_for('bookmarks', userkey=userkey, message=message))


@app.route('/<userkey>/tags')
def tags(userkey):
    """ Overview of all tags used by user """
    tags = get_tags_for_user(userkey)
    print tags
    return render_template('tags.html', tags=tags, userkey=userkey)


@app.route('/<userkey>/tag/<tag>')
def tag(userkey, tag):
    """ Overview of all bookmarks with a certain tag """
    bookmarks = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.tags.contains(tag), Bookmark.status == Bookmark.VISIBLE)
    tags = get_tags_for_user(userkey)
    pageheader = 'tag: ' + tag
    message = request.args.get('message')

    try:
        publictag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
    except PublicTag.DoesNotExist:
        publictag = None

    return render_template('bookmarks.html', bookmarks=bookmarks, userkey=userkey, tags=tags, tag=tag, publictag=publictag, action=pageheader, message=message)


@app.route('/pub/<tagkey>')
def publictag(tagkey):
    """ Read-only overview of the bookmarks in the userkey/tag of this PublicTag """
    #this_tag = get_object_or_404(PublicTag.select().where(PublicTag.tagkey == tagkey))
    try:
        this_tag = PublicTag.get(PublicTag.tagkey == tagkey)
        bookmarks = Bookmark.select().where(Bookmark.userkey == this_tag.userkey, Bookmark.tags.contains(this_tag.tag), Bookmark.status == Bookmark.VISIBLE)
        return render_template('publicbookmarks.html', bookmarks=bookmarks, tag=tag, action=this_tag.tag)
    except PublicTag.DoesNotExist:
        abort(404)


@app.route('/<userkey>/<tag>/makepublic', methods=['GET', 'POST'])
def addpublictag(userkey, tag):
    #user = get_object_or_404(User.get(User.key == userkey))
    try:
        User.get(User.key == userkey)
    except User.DoesNotExist:
        abort(404)
    try:
        publictag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
    except PublicTag.DoesNotExist:
        publictag = None
    if not publictag:
        newpublictag = PublicTag()
        newpublictag.generate_key()
        newpublictag.userkey = userkey
        newpublictag.tag = tag
        newpublictag.save()

        message = 'Public link to this tag created'
        return redirect(url_for('tag', userkey=userkey, tag=tag, message=message))
    else:
        message = 'Public link already existed'
        return redirect(url_for('tag', userkey=userkey, tag=tag, message=message))


@app.route('/<systemkey>/adduser')
def adduser(systemkey):
    """ Add user endpoint, convenience """
    if systemkey == settings.SYSTEMKEY:
        newuser = User()
        newuser.generate_key()
        newuser.username = 'Nomen Nescio'
        newuser.save()
        all_tags[newuser.key] = []
        return redirect('/' + newuser.key, code=302)
    else:
        abort(404)


# Initialise
# create the bookmark, user and public tag tables if they do not exist
Bookmark.create_table(True)
User.create_table(True)
PublicTag.create_table(True)

users = User.select()
print 'Current user keys:'
for user in users:
    all_tags[user.key] = get_tags_for_user(user.key)
    print user.key

if __name__ == '__main__':
    # run the application
    app.run(port=9999, debug=True)
