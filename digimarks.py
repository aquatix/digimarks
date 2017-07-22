from __future__ import print_function
import datetime
import gzip
import hashlib
import os
import sys
import requests
import shutil
import bs4
from urlparse import urlparse, urlunparse, urljoin

from flask import Flask, abort, redirect, render_template, request, url_for, jsonify
from werkzeug.contrib.atom import AtomFeed
from flask_peewee.db import Database
#from flask_peewee.utils import get_object_or_404
from peewee import * # noqa

DEFAULT_THEME = 'green'
themes = {
    'green': {
        'BODY': 'grey lighten-4',
        'TEXT': 'black-text',
        'TEXTHEX': '#000',
        'NAV': 'green darken-3',
        'PAGEHEADER': 'grey-text lighten-5',
        'MESSAGE_BACKGROUND': 'orange lighten-2',
        'MESSAGE_TEXT': 'white-text',
        'ERRORMESSAGE_BACKGROUND': 'red darken-1',
        'ERRORMESSAGE_TEXT': 'white-text',
        'CARD_BACKGROUND': 'green darken-3',
        'CARD_TEXT': 'white-text',
        'FAB': 'red',

        'STAR': 'yellow-text',
        'PROBLEM': 'red-text',
        'COMMENT': '',
    },
    'freshgreen': {
        'BODY': 'grey lighten-5',
        'TEXT': 'black-text',
        'TEXTHEX': '#000',
        'NAV': 'green darken-1',
        'PAGEHEADER': 'grey-text lighten-5',
        'MESSAGE_BACKGROUND': 'orange lighten-2',
        'MESSAGE_TEXT': 'white-text',
        'ERRORMESSAGE_BACKGROUND': 'red darken-1',
        'ERRORMESSAGE_TEXT': 'white-text',
        'CARD_BACKGROUND': 'green darken-1',
        'CARD_TEXT': 'white-text',
        'FAB': 'red',

        'STAR': 'yellow-text',
        'PROBLEM': 'red-text',
        'COMMENT': '',
    },
    'dark': {
        'BODY': 'grey darken-4',
        'TEXT': 'grey-text lighten-1',
        'TEXTHEX': '#bdbdbd',
        'NAV': 'grey darken-3',
        'PAGEHEADER': 'grey-text lighten-1',
        'MESSAGE_BACKGROUND': 'orange lighten-2',
        'MESSAGE_TEXT': 'white-text',
        'ERRORMESSAGE_BACKGROUND': 'red darken-1',
        'ERRORMESSAGE_TEXT': 'white-text',
        'CARD_BACKGROUND': 'grey darken-3',
        'CARD_TEXT': 'grey-text lighten-1',
        'FAB': 'red',

        'STAR': 'yellow-text',
        'PROBLEM': 'red-text',
        'COMMENT': '',
    }
}

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
settings = {}


def ifilterfalse(predicate, iterable):
    # ifilterfalse(lambda x: x%2, range(10)) --> 0 2 4 6 8
    if predicate is None:
        predicate = bool
    for x in iterable:
        if not predicate(x):
            yield x


def unique_everseen(iterable, key=None):
    "List unique elements, preserving order. Remember all elements ever seen."
    # unique_everseen('AAAABBBCCDAABBB') --> A B C D
    # unique_everseen('ABBCcAD', str.lower) --> A B C D
    seen = set()
    seen_add = seen.add
    if key is None:
        for element in ifilterfalse(seen.__contains__, iterable):
            seen_add(element)
            yield element
    else:
        for element in iterable:
            k = key(element)
            if k not in seen:
                seen_add(k)
                yield element

def clean_tags(tags_list):
    tags_res = [x.strip() for x in tags_list]
    tags_res = list(unique_everseen(tags_res))
    tags_res.sort()
    if tags_res and tags_res[0] == '':
        del tags_res[0]
    return tags_res


magic_dict = {
    "\x1f\x8b\x08": "gz",
    "\x42\x5a\x68": "bz2",
    "\x50\x4b\x03\x04": "zip"
    }

max_len = max(len(x) for x in magic_dict)

def file_type(filename):
    with open(filename) as f:
        file_start = f.read(max_len)
    for magic, filetype in magic_dict.items():
        if file_start.startswith(magic):
            return filetype
    return "no match"


class User(db.Model):
    """ User account """
    username = CharField()
    key = CharField()
    theme = CharField(default=DEFAULT_THEME)
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
    note = TextField(default='')
    #image = CharField(default='')
    url_hash = CharField(default='')
    tags = CharField(default='')
    starred = BooleanField(default=False)

    # Website (domain) favicon
    favicon = CharField(null=True)

    # Status code: 200 is OK, 404 is not found, for example (showing an error)
    HTTP_CONNECTIONERROR = 0
    HTTP_OK = 200
    HTTP_MOVEDTEMPORARILY = 304
    HTTP_NOTFOUND = 404

    http_status = IntegerField(default=200)
    redirect_uri = None

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
        try:
            result = requests.head(self.url)
            self.http_status = result.status_code
        except requests.ConnectionError:
            self.http_status = self.HTTP_CONNECTIONERROR
        return self.http_status

    def set_favicon(self):
        """ Fetch favicon for the domain """
        # http://codingclues.eu/2009/retrieve-the-favicon-for-any-url-thanks-to-google/
        u = urlparse(self.url)
        domain = u.netloc
        # if file exists, don't re-download it
        #response = requests.get('http://www.google.com/s2/favicons?domain=' + domain, stream=True)
        fileextension = '.png'
        meta = requests.head('http://icons.better-idea.org/icon?size=60&url=' + domain, allow_redirects=True)
        if meta.url[-3:].lower() == 'ico':
            fileextension = '.ico'
        response = requests.get('http://icons.better-idea.org/icon?size=60&url=' + domain, stream=True)
        filename = os.path.join(MEDIA_ROOT, 'favicons/' + domain + fileextension)
        with open(filename, 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)
        del response
        filetype = file_type(filename)
        if filetype == 'gz':
            # decompress
            orig = gzip.GzipFile(filename, 'rb')
            origcontent = orig.read()
            orig.close()
            os.remove(filename)
            new = file(filename, 'wb')
            new.write(origcontent)
            new.close()
        self.favicon = domain + fileextension

    def set_tags(self, tags):
        """ Set tags from `tags`, strip and sort them """
        tags_split = tags.split(',')
        tags_clean = clean_tags(tags_split)
        self.tags = ','.join(tags_clean)

    def get_redirect_uri(self):
        if self.redirect_uri:
            return self.redirect_uri
        if self.http_status == 301 or self.http_status == 302:
            result = requests.head(self.url, allow_redirects=True)
            self.http_status = result.status_code
            self.redirect_uri = result.url
            return result.url
        else:
            return None

    def get_uri_domain(self):
        parsed = urlparse(self.url)
        return parsed.hostname

    @classmethod
    def strip_url_params(cls, url):
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, '', parsed.fragment))

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
                'created':  self.created_date.strftime('%Y-%m-%d %H:%M:%S'),
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


def get_cached_tags(userkey):
    """ Fail-safe way to get the cached tags for `userkey` """
    try:
        return all_tags[userkey]
    except KeyError:
        return []


def get_theme(userkey):
    try:
        usertheme = settings[userkey]['theme']
        return themes[usertheme]
    except KeyError:
        return themes[DEFAULT_THEME]  # default


def make_external(url):
    return urljoin(request.url_root, url)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', error=e), 404


@app.route('/')
def index():
    """ Homepage, point visitors to project page """
    theme = themes[DEFAULT_THEME]
    return render_template('index.html', theme=theme)


@app.route('/<userkey>', methods=['GET', 'POST'])
@app.route('/<userkey>/filter/<filtermethod>', methods=['GET', 'POST'])
@app.route('/<userkey>/sort/<sortmethod>', methods=['GET', 'POST'])
def bookmarks(userkey, filtermethod = None, sortmethod = None):
    """ User homepage, list their bookmarks, optionally filtered and/or sorted """
    #return object_list('bookmarks.html', Bookmark.select())
    #user = User.select(key=userkey)
    #if user:
    #    bookmarks = Bookmark.select(User=user)
    #    return render_template('bookmarks.html', bookmarks)
    #else:
    #    abort(404)
    message = request.args.get('message')
    tags = get_cached_tags(userkey)

    filter_text = ''
    if request.form:
        filter_text = request.form['filter_text']

    filter_starred = False
    if filtermethod and filtermethod.lower() == 'starred':
        filter_starred = True

    filter_broken = False
    if filtermethod and filtermethod.lower() == 'broken':
        filter_broken = True

    filter_note = False
    if filtermethod and filtermethod.lower() == 'note':
        filter_note = True

    if filter_text:
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.title.contains(filter_text),
                                            Bookmark.status == Bookmark.VISIBLE).order_by(Bookmark.created_date.desc())
    elif filter_starred:
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey,
                                            Bookmark.starred == True).order_by(Bookmark.created_date.desc())
    elif filter_broken:
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey,
                                            Bookmark.http_status != 200).order_by(Bookmark.created_date.desc())
    elif filter_note:
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey,
                                            Bookmark.note != '').order_by(Bookmark.created_date.desc())
    else:
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE).order_by(Bookmark.created_date.desc())

    theme = get_theme(userkey)
    return render_template('bookmarks.html', bookmarks=bookmarks, userkey=userkey, tags=tags, filter_text=filter_text, message=message, theme=theme)



#@app.route('/<userkey>/<urlhash>')
#def viewbookmark(userkey, urlhash):
#    """ Bookmark detail view """
#    bookmark = Bookmark.select(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey)
#    return render_template('viewbookmark.html', userkey=userkey, bookmark=bookmark)


@app.route('/<userkey>/<urlhash>/json')
def viewbookmarkjson(userkey, urlhash):
    """ Serialise bookmark to json """
    bookmark = Bookmark.select(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE)[0]
    return jsonify(bookmark.to_dict())


@app.route('/<userkey>/<urlhash>')
@app.route('/<userkey>/<urlhash>/edit')
def editbookmark(userkey, urlhash):
    """ Bookmark edit form """
    # bookmark = getbyurlhash()
    try:
        bookmark = Bookmark.get(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey)
    except Bookmark.DoesNotExist:
        abort(404)
    message = request.args.get('message')
    tags = get_cached_tags(userkey)
    if not bookmark.note:
        # Workaround for when an existing bookmark has a null note
        bookmark.note = ''
    theme = get_theme(userkey)
    return render_template('edit.html', action='Edit bookmark', userkey=userkey, bookmark=bookmark, message=message, formaction='edit', tags=tags, theme=theme)


@app.route('/<userkey>/add')
def addbookmark(userkey):
    """ Bookmark add form """
    url = request.args.get('url')
    if not url:
        url = ''
    if request.args.get('referrer'):
        url = request.referrer
    bookmark = Bookmark(title='', url=url, tags='')
    message = request.args.get('message')
    tags = get_cached_tags(userkey)
    theme = get_theme(userkey)
    return render_template('edit.html', action='Add bookmark', userkey=userkey, bookmark=bookmark, tags=tags, message=message, theme=theme)


def updatebookmark(userkey, request, urlhash = None):
    """ Add (no urlhash) or edit (urlhash is set) a bookmark """
    title = request.form.get('title')
    url = request.form.get('url')
    tags = request.form.get('tags')
    note = request.form.get('note')
    starred = False
    if request.form.get('starred'):
        starred = True
    strip_params = False
    if request.form.get('strip'):
        strip_params = True

    if url and not urlhash:
        # New bookmark
        bookmark, created = Bookmark.get_or_create(url=url, userkey=userkey)
        if not created:
            message = 'Existing bookmark, did not overwrite with new values'
            return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash, message=message))
    elif url:
        # Existing bookmark, get from DB
        bookmark = Bookmark.get(Bookmark.userkey == userkey, Bookmark.url_hash == urlhash)
        # Editing this bookmark, set modified_date to now
        bookmark.modified_date = datetime.datetime.now()
    else:
        # No url was supplied, abort. @TODO: raise exception?
        return None

    bookmark.title = title
    if strip_params:
        url = Bookmark.strip_url_params(url)
    bookmark.url = url
    bookmark.starred = starred
    bookmark.set_tags(tags)
    bookmark.note = note
    bookmark.set_hash()
    #bookmark.fetch_image()
    if not title:
        # Title was empty, automatically fetch it from the url, will also update the status code
        bookmark.set_title_from_source()
    else:
        bookmark.set_status_code()

    if bookmark.http_status == 200:
        try:
            bookmark.set_favicon()
        except IOError:
            # Icon file could not be saved possibly, don't bail completely
            pass

    bookmark.save()
    return bookmark


@app.route('/<userkey>/adding', methods=['GET', 'POST'])
#@app.route('/<userkey>/adding')
def addingbookmark(userkey):
    """ Add the bookmark from form submit by /add """
    tags = get_cached_tags(userkey)

    if request.method == 'POST':
        bookmark = updatebookmark(userkey, request)
        if not bookmark:
            return redirect(url_for('addbookmark', userkey=userkey, message='No url provided', tags=tags))
        if type(bookmark).__name__ == 'Response':
            return bookmark
        all_tags[userkey] = get_tags_for_user(userkey)
        return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash))
    return redirect(url_for('addbookmark', userkey=userkey, tags=tags))


@app.route('/<userkey>/<urlhash>/editing', methods=['GET', 'POST'])
def editingbookmark(userkey, urlhash):
    """ Edit the bookmark from form submit """

    if request.method == 'POST':
        bookmark = updatebookmark(userkey, request, urlhash=urlhash)
        all_tags[userkey] = get_tags_for_user(userkey)
        return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash))
    return redirect(url_for('editbookmark', userkey=userkey, urlhash=urlhash))


@app.route('/<userkey>/<urlhash>/delete', methods=['GET', 'POST'])
def deletingbookmark(userkey, urlhash):
    """ Delete the bookmark from form submit by <urlhash>/delete """
    query = Bookmark.update(status=Bookmark.DELETED).where(Bookmark.userkey==userkey, Bookmark.url_hash==urlhash)
    query.execute()
    query = Bookmark.update(deleted_date = datetime.datetime.now()).where(Bookmark.userkey==userkey, Bookmark.url_hash==urlhash)
    query.execute()
    message = 'Bookmark deleted. <a href="{}">Undo deletion</a>'.format(url_for('undeletebookmark', userkey=userkey, urlhash=urlhash))
    all_tags[userkey] = get_tags_for_user(userkey)
    return redirect(url_for('bookmarks', userkey=userkey, message=message))


@app.route('/<userkey>/<urlhash>/undelete')
def undeletebookmark(userkey, urlhash):
    """ Undo deletion of the bookmark identified by urlhash """
    query = Bookmark.update(status=Bookmark.VISIBLE).where(Bookmark.userkey==userkey, Bookmark.url_hash==urlhash)
    query.execute()
    message = 'Bookmark restored'
    all_tags[userkey] = get_tags_for_user(userkey)
    return redirect(url_for('bookmarks', userkey=userkey, message=message))


@app.route('/<userkey>/tags')
def tags(userkey):
    """ Overview of all tags used by user """
    tags = get_cached_tags(userkey)
    #publictags = PublicTag.select().where(Bookmark.userkey == userkey)
    alltags = []
    for tag in tags:
        try:
            publictag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
        except PublicTag.DoesNotExist:
            publictag = None

        total = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.tags.contains(tag), Bookmark.status == Bookmark.VISIBLE).count()
        alltags.append({'tag': tag, 'publictag': publictag, 'total': total})
    totaltags = len(alltags)
    totalbookmarks = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE).count()
    totalpublic = PublicTag.select().where(PublicTag.userkey == userkey).count()
    totalstarred = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.starred == True).count()
    totaldeleted = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.status == Bookmark.DELETED).count()
    totalnotes = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.note != '').count()
    totalhttperrorstatus = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.http_status != 200).count()
    theme = get_theme(userkey)
    return render_template('tags.html', tags=alltags, totaltags=totaltags, totalpublic=totalpublic, totalbookmarks=totalbookmarks,
                            totaldeleted=totaldeleted, totalstarred=totalstarred, totalhttperrorstatus=totalhttperrorstatus,
                            totalnotes=totalnotes, userkey=userkey, theme=theme)


@app.route('/<userkey>/tag/<tag>')
def tag(userkey, tag):
    """ Overview of all bookmarks with a certain tag """
    bookmarks = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.tags.contains(tag), Bookmark.status == Bookmark.VISIBLE).order_by(Bookmark.created_date.desc())
    tags = get_cached_tags(userkey)
    pageheader = 'tag: ' + tag
    message = request.args.get('message')

    try:
        publictag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
    except PublicTag.DoesNotExist:
        publictag = None

    theme = get_theme(userkey)
    return render_template('bookmarks.html', bookmarks=bookmarks, userkey=userkey, tags=tags, tag=tag, publictag=publictag, action=pageheader,
                            message=message, theme=theme)


@app.route('/pub/<tagkey>')
def publictag(tagkey):
    """ Read-only overview of the bookmarks in the userkey/tag of this PublicTag """
    #this_tag = get_object_or_404(PublicTag.select().where(PublicTag.tagkey == tagkey))
    try:
        this_tag = PublicTag.get(PublicTag.tagkey == tagkey)
        bookmarks = Bookmark.select().where(Bookmark.userkey == this_tag.userkey, Bookmark.tags.contains(this_tag.tag), Bookmark.status == Bookmark.VISIBLE).order_by(Bookmark.created_date.desc())
        theme = themes[DEFAULT_THEME]
        return render_template('publicbookmarks.html', bookmarks=bookmarks, tag=tag, action=this_tag.tag, tagkey=tagkey, theme=theme)
    except PublicTag.DoesNotExist:
        abort(404)


@app.route('/pub/<tagkey>/json')
def publictagjson(tagkey):
    """ json representation of the Read-only overview of the bookmarks in the userkey/tag of this PublicTag """
    try:
        this_tag = PublicTag.get(PublicTag.tagkey == tagkey)
        bookmarks = Bookmark.select().where(Bookmark.userkey == this_tag.userkey, Bookmark.tags.contains(this_tag.tag), Bookmark.status == Bookmark.VISIBLE)
        result = {'count': len(bookmarks), 'items': []}
        for bookmark in bookmarks:
            result['items'].append(bookmark.to_dict())
        return jsonify(result)
    except PublicTag.DoesNotExist:
        abort(404)


@app.route('/pub/<tagkey>/feed')
def publictagfeed(tagkey):
    """ rss/atom representation of the Read-only overview of the bookmarks in the userkey/tag of this PublicTag """
    try:
        this_tag = PublicTag.get(PublicTag.tagkey == tagkey)
        bookmarks = Bookmark.select().where(Bookmark.userkey == this_tag.userkey, Bookmark.tags.contains(this_tag.tag), Bookmark.status == Bookmark.VISIBLE).limit(15)
        feed = AtomFeed(this_tag.tag, feed_url=request.url, url=make_external(url_for('publictag', tagkey=tagkey)))
        for bookmark in bookmarks:
            updated_date = bookmark.modified_date
            if not bookmark.modified_date:
                updated_date = bookmark.created_date
            feed.add(bookmark.title,
                 content_type='html',
                 author='digimarks',
                 url=bookmark.url,
                 updated=updated_date,
                 published=bookmark.created_date)
        return feed.get_response()
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


@app.route('/<userkey>/<tag>/removepublic/<tagkey>', methods=['GET', 'POST'])
def removepublictag(userkey, tag, tagkey):
    q = PublicTag.delete().where(PublicTag.userkey == userkey, PublicTag.tag == tag, PublicTag.tagkey == tagkey)
    q.execute()
    message = 'Public link deleted'
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


@app.route('/<systemkey>/refreshfavicons')
def refreshfavicons(systemkey):
    """ Add user endpoint, convenience """
    if systemkey == settings.SYSTEMKEY:
        bookmarks = Bookmark.select()
        for bookmark in bookmarks:
            if bookmark.favicon:
                try:
                    filename = os.path.join(MEDIA_ROOT, 'favicons/' + bookmark.favicon)
                    os.remove(filename)
                except OSError as e:
                    print(e)
            bookmark.set_favicon()
        return redirect('/')
    else:
        abort(404)


# Initialisation == create the bookmark, user and public tag tables if they do not exist
Bookmark.create_table(True)
User.create_table(True)
PublicTag.create_table(True)

users = User.select()
print('Current user keys:')
for user in users:
    all_tags[user.key] = get_tags_for_user(user.key)
    settings[user.key] = {'theme': user.theme}
    print(user.key)

# Run when called standalone
if __name__ == '__main__':
    # run the application
    app.run(port=9999, debug=True)
