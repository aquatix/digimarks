import binascii
import datetime
import gzip
import hashlib
import logging
import os
import shutil
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

import bs4
import httpx
from dateutil import tz

# from flask import (Flask, abort, jsonify, make_response, redirect,
#                   render_template, request, url_for)
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from feedgen.feed import FeedGenerator
from pydantic import DirectoryPath, FilePath
from pydantic_settings import BaseSettings
from sqlalchemy import VARCHAR, Boolean, Column, DateTime, Integer, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, sessionmaker

DIGIMARKS_USER_AGENT = 'digimarks/2.0.0-dev'

DEFAULT_THEME = 'freshgreen'


class Settings(BaseSettings):
    """Configuration needed for digimarks to find its database, favicons, API integrations."""

    # database_file: FilePath = './bookmarks.db'
    database_file: FilePath
    media_dir: DirectoryPath
    media_url: str = '/static/'

    mashape_api_key: str

    debug: bool = False


settings = Settings()
print(settings.model_dump())

engine = create_engine(f'sqlite:///{settings.database_file}', connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

@asynccontextmanager
async def lifespan(the_app: FastAPI):
    """Upon start, initialise an AsyncClient and assign it to an attribute named requests_client on the app object"""
    the_app.requests_client = httpx.AsyncClient()
    yield
    await the_app.requests_client.aclose()

app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory='templates')

logger = logging.getLogger('digimarks')
if settings.debug:
    logger.setLevel(logging.DEBUG)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Allow requests from everywhere
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Temporary
all_tags = {}
usersettings = {}


def ifilterfalse(predicate, iterable):
    # ifilterfalse(lambda x: x%2, range(10)) --> 0 2 4 6 8
    if predicate is None:
        predicate = bool
    for x in iterable:
        if not predicate(x):
            yield x


def unique_ever_seen(iterable, key=None):
    """List unique elements, preserving order. Remember all elements ever seen.

    unique_ever_seen('AAAABBBCCDAABBB') --> A B C D
    unique_ever_seen('ABBCcAD', str.lower) --> A B C D
    """
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
    """Generate unique list of the tags.

    :param list tags_list: list with all tags
    :return: deduplicated list of the tags, without leading or trailing whitespace
    :rtype: list
    """
    tags_res = [x.strip() for x in tags_list]
    tags_res = list(unique_ever_seen(tags_res))
    tags_res.sort()
    if tags_res and tags_res[0] == '':
        del tags_res[0]
    return tags_res


def file_type(filename):
    """Try to determine the file type for the file in `filename`.

    :param str filename: path to file to check
    :return: zip file type
    :rtype: str
    """
    magic_dict = {b'\x1f\x8b\x08': 'gz', b'\x42\x5a\x68': 'bz2', b'\x50\x4b\x03\x04': 'zip'}

    max_len = max(len(x) for x in magic_dict)

    with open(filename, 'rb') as f:
        file_start = f.read(max_len)
    for magic, filetype in magic_dict.items():
        if file_start.startswith(magic):
            return filetype
    return 'no match'


class User(Base):
    """User account."""

    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    username = Column(VARCHAR(255))
    key = Column(VARCHAR(255))
    # theme = CharField(default=DEFAULT_THEME)
    theme = Column(VARCHAR(20), default=DEFAULT_THEME)
    created_date = Column(DateTime, default=datetime.datetime.now)

    def generate_key(self):
        """Generate userkey."""
        self.key = binascii.hexlify(os.urandom(24))
        return self.key


class Bookmark(Base):
    """Bookmark instance, connected to User."""

    __tablename__ = 'bookmark'

    id = Column(Integer, primary_key=True)
    # Foreign key to User
    userkey = Column(VARCHAR(255))

    title = Column(VARCHAR(255), default='')
    url = Column(VARCHAR(255))
    note = Column(Text, default='')
    # image = CharField(default='')
    url_hash = Column(VARCHAR(255), default='')
    tags = Column(VARCHAR(255), default='')
    starred = Column(Boolean, default=False)

    # Website (domain) favicon
    # favicon = Column(VARCHAR(255), null=True)
    # favicon = Column(VARCHAR(255))
    favicon: Mapped[Optional[str]]

    # Status code: 200 is OK, 404 is not found, for example (showing an error)
    HTTP_CONNECTIONERROR = 0
    HTTP_OK = 200
    HTTP_ACCEPTED = 202
    HTTP_MOVEDTEMPORARILY = 304
    HTTP_NOTFOUND = 404

    http_status = Column(Integer, default=200)
    redirect_uri = None

    created_date = Column(DateTime, default=datetime.datetime.now)
    # modified_date = Column(DateTime, null=True)
    modified_date: Mapped[Optional[datetime.datetime]]
    # deleted_date = Column(DateTime, null=True)
    deleted_date: Mapped[Optional[datetime.datetime]]

    # Bookmark status; deleting doesn't remove from DB
    VISIBLE = 0
    DELETED = 1
    status = Column(Integer, default=VISIBLE)

    class Meta:
        ordering = (('created_date', 'desc'),)

    def set_hash(self):
        """Generate hash."""
        self.url_hash = hashlib.md5(self.url.encode('utf-8')).hexdigest()

    def set_title_from_source(self, request: Request) -> str:
        """Request the title by requesting the source url."""
        try:
            result = request.app.requests_client.get(self.url, headers={'User-Agent': DIGIMARKS_USER_AGENT})
            self.http_status = result.status_code
        except:
            # For example 'MissingSchema: Invalid URL 'abc': No schema supplied. Perhaps you meant http://abc?'
            self.http_status = 404
        if self.http_status == 200 or self.http_status == 202:
            html = bs4.BeautifulSoup(result.text, 'html.parser')
            try:
                self.title = html.title.text.strip()
            except AttributeError:
                self.title = ''
        return self.title

    def set_status_code(self, request: Request) -> int:
        """Check the HTTP status of the url, as it might not exist for example."""
        try:
            result = request.app.requests_client.head(self.url, headers={'User-Agent': DIGIMARKS_USER_AGENT}, timeout=30)
            self.http_status = result.status_code
        except httpx.HTTPError as e:
            logger.error(f'Failed to do head info fetching for {self.url}: {e}')
            self.http_status = self.HTTP_CONNECTIONERROR
        return self.http_status

    def _set_favicon_with_iconsbetterideaorg(self, request: Request, domain):
        """Fetch favicon for the domain."""
        fileextension = '.png'
        meta = request.app.requests_client.head(
            'http://icons.better-idea.org/icon?size=60&url=' + domain,
            allow_redirects=True,
            headers={'User-Agent': DIGIMARKS_USER_AGENT},
            timeout=15,
        )
        if meta.url[-3:].lower() == 'ico':
            fileextension = '.ico'
        response = request.app.requests_client.get(
            'http://icons.better-idea.org/icon?size=60&url=' + domain,
            stream=True,
            headers={'User-Agent': DIGIMARKS_USER_AGENT},
            timeout=15,
        )
        filename = os.path.join(settings.media_dir, 'favicons/', domain + fileextension)
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
            with open(filename, 'wb') as new:
                new.write(origcontent)
        self.favicon = domain + fileextension

    def _set_favicon_with_realfavicongenerator(self, request: Request, domain: str):
        """Fetch favicon for the domain."""
        response = request.app.requests_client.get(
            'https://realfavicongenerator.p.rapidapi.com/favicon/icon?platform=android_chrome&site=' + domain,
            stream=True,
            headers={'User-Agent': DIGIMARKS_USER_AGENT, 'X-Mashape-Key': settings.MASHAPE_API_KEY},
        )
        if response.status_code == 404:
            # Fall back to desktop favicon
            response = request.app.requests_client.get(
                'https://realfavicongenerator.p.rapidapi.com/favicon/icon?platform=desktop&site=' + domain,
                stream=True,
                headers={'User-Agent': DIGIMARKS_USER_AGENT, 'X-Mashape-Key': settings.MASHAPE_API_KEY},
            )
        # Debug for the moment
        print(domain)
        print(response.headers)
        if 'Content-Length' in response.headers and response.headers['Content-Length'] == '0':
            # No favicon found, likely
            print('Skipping this favicon, needs fallback')
            return
        # Default to 'image/png'
        fileextension = '.png'
        if response.headers['content-type'] == 'image/jpeg':
            fileextension = '.jpg'
        if response.headers['content-type'] == 'image/x-icon':
            fileextension = '.ico'
        filename = os.path.join(settings.media_dir, 'favicons/', domain + fileextension)
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
            with open(filename, 'wb') as new:
                new.write(origcontent)
        self.favicon = domain + fileextension

    def set_favicon(self, request: Request):
        """Fetch favicon for the domain."""
        u = urlparse(self.url)
        domain = u.netloc
        if os.path.isfile(os.path.join(settings.media_dir, 'favicons/', domain + '.png')):
            # If file exists, don't re-download it
            self.favicon = f'{domain}.png'
            return
        if os.path.isfile(os.path.join(settings.media_dir, 'favicons/', domain + '.ico')):
            # If file exists, don't re-download it
            self.favicon = f'{domain}.ico'
            return
        # self._set_favicon_with_iconsbetterideaorg(domain)
        self._set_favicon_with_realfavicongenerator(request, domain)

    def set_tags(self, new_tags):
        """Set tags from `tags`, strip and sort them."""
        tags_split = new_tags.split(',')
        tags_clean = clean_tags(tags_split)
        self.tags = ','.join(tags_clean)

    def get_redirect_uri(self, request: Request):
        """Derive where to redirect to."""
        if self.redirect_uri:
            return self.redirect_uri
        if self.http_status in (301, 302):
            result = request.app.requests_client.head(
                self.url, allow_redirects=True, headers={'User-Agent': DIGIMARKS_USER_AGENT}, timeout=30
            )
            self.http_status = result.status_code
            self.redirect_uri = result.url
            return result.url
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
        """Get the tags as a list, iterable in template."""
        if self.tags:
            return self.tags.split(',')
        return []

    def to_dict(self) -> dict:
        result = {
            'title': self.title,
            'url': self.url,
            'created': self.created_date.strftime('%Y-%m-%d %H:%M:%S'),
            'url_hash': self.url_hash,
            'tags': self.tags,
        }
        return result

    @property
    def serialize(self) -> dict:
        return self.to_dict()


class PublicTag(Base):
    """Publicly shared tag."""

    __tablename__ = 'public_tag'

    id = Column(Integer, primary_key=True)
    tagkey = Column(VARCHAR(255))
    userkey = Column(VARCHAR(255))
    tag = Column(VARCHAR(255))
    created_date = Column(DateTime, default=datetime.datetime.now)

    def generate_key(self):
        """Generate hash-based key for publicly shared tag."""
        self.tagkey = binascii.hexlify(os.urandom(16))


def get_tags_for_user(userkey):
    """Extract all tags from the bookmarks."""
    bookmarks = Bookmark.select().filter(Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE)
    tags = []
    for bookmark in bookmarks:
        tags += bookmark.tags_list
    return clean_tags(tags)


def get_cached_tags(userkey):
    """Fail-safe way to get the cached tags for `userkey`."""
    try:
        return all_tags[userkey]
    except KeyError:
        return []


def get_theme(userkey):
    themes = {DEFAULT_THEME: {}}
    try:
        usertheme = usersettings[userkey]['theme']
        return themes[usertheme]
    except KeyError:
        return themes[DEFAULT_THEME]  # default


def make_external(request: Request, url):
    return urljoin(request.url_root, url)


def _find_bookmarks(userkey, filter_text) -> list[Bookmark]:
    """Look up bookmark for `userkey` which contains `filter_text` in its properties."""
    return (
        Bookmark.select()
        .where(
            Bookmark.userkey == userkey,
            (
                    Bookmark.title.contains(filter_text)
                    | Bookmark.url.contains(filter_text)
                    | Bookmark.note.contains(filter_text)
            ),
            Bookmark.status == Bookmark.VISIBLE,
        )
        .order_by(Bookmark.created_date.desc())
    )


# @app.errorhandler(404)
# def page_not_found(e):
#     theme = themes[DEFAULT_THEME]
#     return render_template('404.html', error=e, theme=theme), 404


@app.get('/')
def index():
    """Homepage, point visitors to project page."""
    # theme = themes[DEFAULT_THEME]
    # return render_template('index.html', theme=theme)
    return {}


def get_bookmarks(request: Request, user_key, filter_method=None, sort_method=None):
    """User homepage, list their bookmarks, optionally filtered and/or sorted."""
    # return object_list('bookmarks.html', Bookmark.select())
    # user = User.select(key=userkey)
    # if user:
    #    bookmarks = Bookmark.select(User=user)
    #    return render_template('bookmarks.html', bookmarks)
    # else:
    #    abort(404)
    message = request.args.get('message')
    bookmark_tags = get_cached_tags(user_key)

    filter_text = ''
    if request.form:
        filter_text = request.form['filter_text']

    filter_starred = False
    if filter_method and filter_method.lower() == 'starred':
        filter_starred = True

    filter_broken = False
    if filter_method and filter_method.lower() == 'broken':
        filter_broken = True

    filter_note = False
    if filter_method and filter_method.lower() == 'note':
        filter_note = True

    if filter_text:
        bookmarks = _find_bookmarks(user_key, filter_text)
    elif filter_starred:
        bookmarks = (
            Bookmark.select()
            .where(Bookmark.userkey == user_key, Bookmark.starred)
            .order_by(Bookmark.created_date.desc())
        )
    elif filter_broken:
        bookmarks = (
            Bookmark.select()
            .where(Bookmark.userkey == user_key, Bookmark.http_status != 200)
            .order_by(Bookmark.created_date.desc())
        )
    elif filter_note:
        bookmarks = (
            Bookmark.select()
            .where(Bookmark.userkey == user_key, Bookmark.note != '')
            .order_by(Bookmark.created_date.desc())
        )
    else:
        bookmarks = (
            Bookmark.select()
            .where(Bookmark.userkey == user_key, Bookmark.status == Bookmark.VISIBLE)
            .order_by(Bookmark.created_date.desc())
        )

    return bookmarks, bookmark_tags, filter_text, message


@app.get('/{user_key}', response_class=HTMLResponse)
@app.post('/{user_key}', response_class=HTMLResponse)
@app.route('/<user_key>/filter/<filtermethod>', methods=['GET', 'POST'])
@app.route('/<user_key>/sort/<sortmethod>', methods=['GET', 'POST'])
@app.route('/<user_key>/<show_as>', methods=['GET', 'POST'])
@app.route('/<user_key>/<show_as>/filter/<filtermethod>', methods=['GET', 'POST'])
@app.route('/<user_key>/<show_as>/sort/<sortmethod>', methods=['GET', 'POST'])
def bookmarks_page(request: Request, user_key, filter_method=None, sort_method=None, show_as='cards'):
    bookmarks, bookmarktags, filter_text, message = get_bookmarks(request, user_key, filter_method, sort_method)
    theme = get_theme(user_key)
    return templates.TemplateResponse(
        'bookmarks.html',
        bookmarks=bookmarks,
        userkey=user_key,
        tags=bookmarktags,
        filter_text=filter_text,
        message=message,
        theme=theme,
        editable=True,  # bookmarks can be edited
        showtags=True,  # tags should be shown with the bookmarks
        filtermethod=filter_method,
        sortmethod=sort_method,
        show_as=show_as,  # show list of bookmarks instead of cards
    )


@app.get('/{user_key}/js')
def bookmarks_js(user_key):
    """Return list of bookmarks with their favicons, to be used for autocompletion."""
    bookmarks = (
        Bookmark.select()
        .where(Bookmark.userkey == user_key, Bookmark.status == Bookmark.VISIBLE)
        .order_by(Bookmark.created_date.desc())
    )
    result = []
    for bookmark in bookmarks:
        result.append({'title': bookmark.title})
    # resp = make_response(render_template(
    #     'bookmarks.js',
    #     bookmarks=bookmarks
    # ))
    # resp.headers['Content-type'] = 'text/javascript; charset=utf-8'
    # return resp
    return result


@app.get('/r/<userkey>/<urlhash>', response_class=HTMLResponse)
def bookmark_redirect(userkey, urlhash):
    """Securely redirect a bookmark to its url, stripping referrer (if browser plays nice)."""
    # @TODO: add counter to this bookmark
    try:
        bookmark = Bookmark.get(
            Bookmark.url_hash == urlhash, Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE
        )
    except Bookmark.DoesNotExist:
        raise HTTPException(status_code=404, detail='Bookmark not found')
    return templates.TemplateResponse('redirect.html', url=bookmark.url)


@app.route('/api/v1/<userkey>', methods=['GET', 'POST'])
@app.route('/api/v1/<userkey>/filter/<filtermethod>', methods=['GET', 'POST'])
@app.route('/api/v1/<userkey>/sort/<sortmethod>', methods=['GET', 'POST'])
def bookmarks_json(request: Request, userkey, filtermethod=None, sortmethod=None):
    bookmarks, bookmarktags, filter_text, message = get_bookmarks(request, userkey, filtermethod, sortmethod)

    bookmarkslist = [i.serialize for i in bookmarks]

    the_data = {
        'bookmarks': bookmarkslist,
        'tags': bookmarktags,
        'filter_text': filter_text,
        'message': message,
        'userkey': userkey,
    }
    return the_data


@app.route('/api/v1/<userkey>/<urlhash>')
def bookmark_json(userkey, urlhash):
    """Serialise bookmark to json."""
    try:
        bookmark = Bookmark.get(
            Bookmark.url_hash == urlhash, Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE
        )
        return bookmark.to_dict()
    except Bookmark.DoesNotExist:
        raise HTTPException(status_code=404, detail='Bookmark not found')


@app.route('/api/v1/<userkey>/search/<filter_text>')
def search_bookmark_titles_json(userkey, filter_text):
    """Serialise bookmark to json."""
    bookmarks = _find_bookmarks(userkey, filter_text)
    result = []
    for bookmark in bookmarks:
        result.append(bookmark.to_dict())
    return result


@app.get('/<userkey>/<urlhash>', response_class=HTMLResponse)
@app.get('/<userkey>/<urlhash>/edit', response_class=HTMLResponse)
def edit_bookmark(request: Request, userkey, urlhash):
    """Bookmark edit form."""
    # bookmark = getbyurlhash()
    try:
        bookmark = Bookmark.get(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey)
    except Bookmark.DoesNotExist:
        raise HTTPException(status_code=404, detail='Bookmark not found')
    message = request.args.get('message')
    tags = get_cached_tags(userkey)
    if not bookmark.note:
        # Workaround for when an existing bookmark has a null note
        bookmark.note = ''
    theme = get_theme(userkey)
    return templates.TemplateResponse(
        'edit.html',
        action='Edit bookmark',
        userkey=userkey,
        bookmark=bookmark,
        message=message,
        formaction='edit',
        tags=tags,
        theme=theme,
    )


@app.get('/<userkey>/add', response_class=HTMLResponse)
def add_bookmark(request: Request, userkey):
    """Bookmark add form."""
    url = request.args.get('url')
    if not url:
        url = ''
    if request.args.get('referrer'):
        url = request.referrer
    bookmark = Bookmark(title='', url=url, tags='')
    message = request.args.get('message')
    tags = get_cached_tags(userkey)
    theme = get_theme(userkey)
    return templates.TemplateResponse(
        'edit.html', action='Add bookmark', userkey=userkey, bookmark=bookmark, tags=tags, message=message, theme=theme
    )


def update_bookmark(request: Request, userkey, urlhash=None):
    """Add (no urlhash) or edit (urlhash is set) a bookmark."""
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
            return RedirectResponse(
                request.url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash, message=message)
            )
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
    # bookmark.fetch_image()
    if not title:
        # Title was empty, automatically fetch it from the url, will also update the status code
        bookmark.set_title_from_source(request)
    else:
        bookmark.set_status_code(request)

    if bookmark.http_status in (200, 202):
        try:
            bookmark.set_favicon()
        except IOError:
            # Icon file could not be saved possibly, don't bail completely
            pass

    bookmark.save()
    return bookmark


@app.route('/<userkey>/adding', methods=['GET', 'POST'])
# @app.route('/<userkey>/adding')
def adding_bookmark(request: Request, user_key):
    """Add the bookmark from form submit by /add."""
    tags = get_cached_tags(user_key)

    if request.method == 'POST':
        bookmark = update_bookmark(request, user_key)
        if not bookmark:
            return RedirectResponse(
                request.url_for('addbookmark', userkey=user_key, message='No url provided', tags=tags)
            )
        if type(bookmark).__name__ == 'Response':
            return bookmark
        all_tags[user_key] = get_tags_for_user(user_key)
        return RedirectResponse(request.url_for('editbookmark', userkey=user_key, urlhash=bookmark.url_hash))
    return RedirectResponse(request.url_for('addbookmark', userkey=user_key, tags=tags))


@app.route('/<userkey>/<urlhash>/editing', methods=['GET', 'POST'])
def editing_bookmark(request: Request, userkey, urlhash):
    """Edit the bookmark from form submit."""
    if request.method == 'POST':
        bookmark = update_bookmark(request, userkey, urlhash=urlhash)
        all_tags[userkey] = get_tags_for_user(userkey)
        return RedirectResponse(request.url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash))
    return RedirectResponse(request.url_for('editbookmark', userkey=userkey, urlhash=urlhash))


@app.route('/<userkey>/<urlhash>/delete', methods=['GET', 'POST'])
def deleting_bookmark(request: Request, userkey, urlhash):
    """Delete the bookmark from form submit by <urlhash>/delete."""
    query = Bookmark.update(status=Bookmark.DELETED).where(Bookmark.userkey == userkey, Bookmark.url_hash == urlhash)
    query.execute()
    query = Bookmark.update(deleted_date=datetime.datetime.now()).where(
        Bookmark.userkey == userkey, Bookmark.url_hash == urlhash
    )
    query.execute()
    message = 'Bookmark deleted. <a href="{}">Undo deletion</a>'.format(
        request.url_for('undeletebookmark', userkey=userkey, urlhash=urlhash)
    )
    all_tags[userkey] = get_tags_for_user(userkey)
    return RedirectResponse(request.url_for('bookmarks_page', userkey=userkey, message=message))


@app.get('/<userkey>/<urlhash>/undelete')
def undelete_bookmark(request: Request, userkey, urlhash):
    """Undo deletion of the bookmark identified by urlhash."""
    query = Bookmark.update(status=Bookmark.VISIBLE).where(Bookmark.userkey == userkey, Bookmark.url_hash == urlhash)
    query.execute()
    message = 'Bookmark restored'
    all_tags[userkey] = get_tags_for_user(userkey)
    return RedirectResponse(request.url_for('bookmarks_page', userkey=userkey, message=message))


@app.get('/<userkey>/tags', response_class=HTMLResponse)
def tags_page(userkey):
    """Overview of all tags used by user."""
    tags = get_cached_tags(userkey)
    # public_tags = PublicTag.select().where(Bookmark.userkey == userkey)
    alltags = []
    for tag in tags:
        try:
            public_tag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
        except PublicTag.DoesNotExist:
            public_tag = None

        total = (
            Bookmark.select()
            .where(Bookmark.userkey == userkey, Bookmark.tags.contains(tag), Bookmark.status == Bookmark.VISIBLE)
            .count()
        )
        alltags.append({'tag': tag, 'public_tag': public_tag, 'total': total})
    totaltags = len(alltags)
    totalbookmarks = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE).count()
    totalpublic = PublicTag.select().where(PublicTag.userkey == userkey).count()
    totalstarred = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.starred).count()
    totaldeleted = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.status == Bookmark.DELETED).count()
    totalnotes = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.note != '').count()
    totalhttperrorstatus = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.http_status != 200).count()
    theme = get_theme(userkey)
    return templates.TemplateResponse(
        'tags.html',
        tags=alltags,
        totaltags=totaltags,
        totalpublic=totalpublic,
        totalbookmarks=totalbookmarks,
        totaldeleted=totaldeleted,
        totalstarred=totalstarred,
        totalhttperrorstatus=totalhttperrorstatus,
        totalnotes=totalnotes,
        userkey=userkey,
        theme=theme,
    )


@app.get('/<userkey>/tag/<tag>', response_class=HTMLResponse)
def tag_page(request: Request, userkey, tag):
    """Overview of all bookmarks with a certain tag."""
    bookmarks = (
        Bookmark.select()
        .where(Bookmark.userkey == userkey, Bookmark.tags.contains(tag), Bookmark.status == Bookmark.VISIBLE)
        .order_by(Bookmark.created_date.desc())
    )
    tags = get_cached_tags(userkey)
    pageheader = 'tag: ' + tag
    message = request.args.get('message')

    try:
        public_tag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
    except PublicTag.DoesNotExist:
        public_tag = None

    theme = get_theme(userkey)
    return templates.TemplateResponse(
        'bookmarks.html',
        bookmarks=bookmarks,
        userkey=userkey,
        tags=tags,
        tag=tag,
        public_tag=public_tag,
        action=pageheader,
        message=message,
        theme=theme,
        editable=True,
        showtags=True,
    )


def get_public_tag(tagkey):
    """Return tag and bookmarks in this public tag collection."""
    this_tag = PublicTag.get(PublicTag.tagkey == tagkey)
    bookmarks = (
        Bookmark.select()
        .where(
            Bookmark.userkey == this_tag.userkey,
            Bookmark.tags.contains(this_tag.tag),
            Bookmark.status == Bookmark.VISIBLE,
        )
        .order_by(Bookmark.created_date.desc())
    )
    return this_tag, bookmarks


@app.get('/pub/<tagkey>', response_class=HTMLResponse)
def public_tag_page(tagkey):
    """Read-only overview of the bookmarks in the userkey/tag of this PublicTag."""
    # this_tag = get_object_or_404(PublicTag.select().where(PublicTag.tagkey == tagkey))
    try:
        this_tag, bookmarks = get_public_tag(tagkey)
        # theme = themes[DEFAULT_THEME]
        theme = {}
        return templates.TemplateResponse(
            'publicbookmarks.html',
            bookmarks=bookmarks,
            tag=this_tag.tag,
            action=this_tag.tag,
            tagkey=tagkey,
            theme=theme,
        )
    except PublicTag.DoesNotExist:
        raise HTTPException(status_code=404, detail='Public tag not found')


@app.route('/api/v1/pub/<tagkey>')
def public_tag_json(tagkey):
    """Json representation of the Read-only overview of the bookmarks in the userkey/tag of this PublicTag."""
    try:
        this_tag, bookmarks = get_public_tag(tagkey)
        result = {
            # 'tag': this_tag,
            'tagkey': tagkey,
            'count': len(bookmarks),
            'items': [],
        }
        for bookmark in bookmarks:
            result['items'].append(bookmark.to_dict())
        return result
    except PublicTag.DoesNotExist:
        raise HTTPException(status_code=404, detail='Public tag not found')


@app.get('/pub/<tagkey>/feed')
async def public_tag_feed(request: Request, tagkey: str):
    """rss/atom representation of the Read-only overview of the bookmarks in the userkey/tag of this PublicTag."""
    try:
        this_tag = PublicTag.get(PublicTag.tagkey == tagkey)
        bookmarks = Bookmark.select().where(
            Bookmark.userkey == this_tag.userkey,
            Bookmark.tags.contains(this_tag.tag),
            Bookmark.status == Bookmark.VISIBLE,
        )

        feed = FeedGenerator()
        feed.title(this_tag.tag)
        feed.id(request.url)
        feed.link(href=request.url, rel='self')
        feed.link(href=make_external(request, app.url_path_for('public_tag_page', tagkey=tagkey)))

        for bookmark in bookmarks:
            entry = feed.add_entry()

            updated_date = bookmark.modified_date
            if not bookmark.modified_date:
                updated_date = bookmark.created_date
            bookmarktitle = '{} (no title)'.format(bookmark.url)
            if bookmark.title:
                bookmarktitle = bookmark.title

            entry.id(bookmark.url)
            entry.title(bookmarktitle)
            entry.link(href=bookmark.url)
            entry.author(name='digimarks')
            entry.pubdate(bookmark.created_date.replace(tzinfo=tz.tzlocal()))
            entry.published(bookmark.created_date.replace(tzinfo=tz.tzlocal()))
            entry.updated(updated_date.replace(tzinfo=tz.tzlocal()))

        response = Response(data=feed.atom_str(pretty=True), media_type='application/xml')

        response.headers.set('Content-Type', 'application/atom+xml')
        return response
    except PublicTag.DoesNotExist:
        raise HTTPException(status_code=404, detail='Tag not found')


@app.get('/<userkey>/<tag>/makepublic')
@app.post('/<userkey>/<tag>/makepublic')
async def add_public_tag(userkey: str, tag: str):
    try:
        User.get(User.key == userkey)
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail='User not found')
    try:
        public_tag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
    except PublicTag.DoesNotExist:
        public_tag = None
    if not public_tag:
        new_public_tag = PublicTag()
        new_public_tag.generate_key()
        new_public_tag.userkey = userkey
        new_public_tag.tag = tag
        new_public_tag.save()

        message = 'Public link to this tag created'
        success = True
        # return RedirectResponse(url=url_path_for('tag_page', userkey=userkey, tag=tag, message=message))
    else:
        message = 'Public link already existed'
        success = False
    # return redirect(url_for('tag_page', userkey=userkey, tag=tag, message=message))
    url = app.url_path_for('tag_page', userkey=userkey, tag=tag, message=message)
    return {'success': success, 'message': message, 'url': url}


@app.route('/<userkey>/<tag>/removepublic/<tagkey>', methods=['GET', 'POST'])
def remove_public_tag(request: Request, userkey, tag, tagkey):
    q = PublicTag.delete().where(PublicTag.userkey == userkey, PublicTag.tag == tag, PublicTag.tagkey == tagkey)
    q.execute()
    message = f'Public link {tagkey} has been deleted'
    url = request.url_for('tag_page', userkey=userkey, tag=tag)
    return {'message': message, 'url': url}


@app.route('/<systemkey>/adduser')
def add_user(systemkey):
    """Add user endpoint, convenience."""
    if systemkey == settings.SYSTEMKEY:
        new_user = User()
        new_user.generate_key()
        new_user.username = 'Nomen Nescio'
        new_user.save()
        all_tags[new_user.key] = []
        return {'user': f'/{new_user.key.decode("utf-8")}'}
    raise HTTPException(status_code=404, detail='I can\'t let you do that Dave')


@app.route('/<systemkey>/refreshfavicons')
def refresh_favicons(systemkey):
    """Add user endpoint, convenience."""
    if systemkey == settings.SYSTEMKEY:
        bookmarks = Bookmark.select()
        for bookmark in bookmarks:
            if bookmark.favicon:
                try:
                    filename = os.path.join(settings.media_dir, 'favicons', bookmark.favicon)
                    os.remove(filename)
                except OSError as e:
                    print(e)
            bookmark.set_favicon()
        return {'message': 'Done refreshing icons'}
    raise HTTPException(status_code=404, detail='I can\'t let you do that Dave')


@app.route('/<systemkey>/findmissingfavicons')
def find_missing_favicons(request: Request, systemkey: str):
    """Add user endpoint, convenience."""
    if systemkey == settings.SYSTEMKEY:
        bookmarks = Bookmark.select()
        for bookmark in bookmarks:
            try:
                if not bookmark.favicon or not os.path.isfile(
                        os.path.join(settings.media_dir, 'favicons', bookmark.favicon)
                ):
                    # This favicon is missing
                    # Clear favicon, so fallback can be used instead of showing a broken image
                    bookmark.favicon = None
                    bookmark.save()
                    # Try to fetch and save new favicon
                    bookmark.set_favicon(request)
                    bookmark.save()
            except OSError as e:
                print(e)
        return {'message': 'Done finding missing icons'}
    raise HTTPException(status_code=404, detail='I can\'t let you do that Dave')

# Initialisation == create the bookmark, user and public tag tables if they do not exist
# TODO: switch to alembic migrations
# Bookmark.create_table(True)
# User.create_table(True)
# PublicTag.create_table(True)

# users = User.select()
# print('Current user keys:')
# for user in users:
#     all_tags[user.key] = get_tags_for_user(user.key)
#     usersettings[user.key] = {'theme': user.theme}
#     print(user.key)

# Run when called standalone
# if __name__ == '__main__':
# run the application
# app.run(host='0.0.0.0', port=9999, debug=True)
