"""digimarks data models and accompanying convenience functions"""

import binascii
import os
import datetime

from peewee import *  # noqa

from . import themes


try:
    # Python 3
    from urllib.parse import urljoin, urlparse, urlunparse
except ImportError:
    # Python 2
    from urlparse import urljoin, urlparse, urlunparse


DATABASE_PATH = os.path.dirname(os.path.realpath(__file__))
if 'DIGIMARKS_DB_PATH' in os.environ:
    DATABASE_PATH = os.environ['DIGIMARKS_DB_PATH']
database = SqliteDatabase(os.path.join(DATABASE_PATH, 'bookmarks.db'))


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
    b"\x1f\x8b\x08": "gz",
    b"\x42\x5a\x68": "bz2",
    b"\x50\x4b\x03\x04": "zip"
    }

max_len = max(len(x) for x in magic_dict)


def file_type(filename):
    with open(filename, "rb") as f:
        file_start = f.read(max_len)
    for magic, filetype in magic_dict.items():
        if file_start.startswith(magic):
            return filetype
    return "no match"


class BaseModel(Model):
    class Meta:
        database = database


class User(BaseModel):
    """ User account """
    username = CharField()
    key = CharField()
    theme = CharField(default=themes.DEFAULT_THEME)
    created_date = DateTimeField(default=datetime.datetime.now)

    def generate_key(self):
        """ Generate userkey """
        self.key = binascii.hexlify(os.urandom(24))
        return self.key


class Bookmark(BaseModel):
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
    HTTP_ACCEPTED = 202
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

    def set_hash(self):
        """ Generate hash """
        self.url_hash = hashlib.md5(self.url.encode('utf-8')).hexdigest()

    def set_title_from_source(self):
        """ Request the title by requesting the source url """
        try:
            result = requests.get(self.url, headers={'User-Agent': DIGIMARKS_USER_AGENT})
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

    def set_status_code(self):
        """ Check the HTTP status of the url, as it might not exist for example """
        try:
            result = requests.head(self.url, headers={'User-Agent': DIGIMARKS_USER_AGENT})
            self.http_status = result.status_code
        except requests.ConnectionError:
            self.http_status = self.HTTP_CONNECTIONERROR
        return self.http_status

    def _set_favicon_with_iconsbetterideaorg(self, domain):
        """ Fetch favicon for the domain """
        fileextension = '.png'
        meta = requests.head(
            'http://icons.better-idea.org/icon?size=60&url=' + domain,
            allow_redirects=True,
            headers={'User-Agent': DIGIMARKS_USER_AGENT}
        )
        if meta.url[-3:].lower() == 'ico':
            fileextension = '.ico'
        response = requests.get(
            'http://icons.better-idea.org/icon?size=60&url=' + domain,
            stream=True,
            headers={'User-Agent': DIGIMARKS_USER_AGENT}
        )
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
            with open(filename, 'wb') as new:
                new.write(origcontent)
        self.favicon = domain + fileextension

    def _set_favicon_with_realfavicongenerator(self, domain):
        """ Fetch favicon for the domain """
        response = requests.get(
            'https://realfavicongenerator.p.mashape.com/favicon/icon?platform=android_chrome&site=' + domain,
            stream=True,
            headers={'User-Agent': DIGIMARKS_USER_AGENT, 'X-Mashape-Key': settings.MASHAPE_API_KEY}
        )
        if response.status_code == 404:
            # Fall back to desktop favicon
            response = requests.get(
                'https://realfavicongenerator.p.mashape.com/favicon/icon?platform=desktop&site=' + domain,
                stream=True,
                headers={'User-Agent': DIGIMARKS_USER_AGENT, 'X-Mashape-Key': settings.MASHAPE_API_KEY}
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
            with open(filename, 'wb') as new:
                new.write(origcontent)
        self.favicon = domain + fileextension

    def set_favicon(self):
        """ Fetch favicon for the domain """
        u = urlparse(self.url)
        domain = u.netloc
        if os.path.isfile(os.path.join(MEDIA_ROOT, 'favicons/' + domain + '.png')):
            # If file exists, don't re-download it
            self.favicon = domain + '.png'
            return
        if os.path.isfile(os.path.join(MEDIA_ROOT, 'favicons/' + domain + '.ico')):
            # If file exists, don't re-download it
            self.favicon = domain + '.ico'
            return
        #self._set_favicon_with_iconsbetterideaorg(domain)
        self._set_favicon_with_realfavicongenerator(domain)

    def set_tags(self, newtags):
        """ Set tags from `tags`, strip and sort them """
        tags_split = newtags.split(',')
        tags_clean = clean_tags(tags_split)
        self.tags = ','.join(tags_clean)

    def get_redirect_uri(self):
        if self.redirect_uri:
            return self.redirect_uri
        if self.http_status == 301 or self.http_status == 302:
            result = requests.head(self.url, allow_redirects=True, headers={'User-Agent': DIGIMARKS_USER_AGENT})
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
        """ Get the tags as a list, iterable in template """
        if self.tags:
            return self.tags.split(',')
        return []

    def to_dict(self):
        result = {
            'title': self.title,
            'url': self.url,
            'created':  self.created_date.strftime('%Y-%m-%d %H:%M:%S'),
            'url_hash': self.url_hash,
            'tags': self.tags.split(','),
            'favicon': self.favicon,
            'http_status': self.http_status,
            'redirect_uri': self.redirect_uri,
        }
        return result

    @property
    def serialize(self):
        return self.to_dict()


class PublicTag(BaseModel):
    """ Publicly shared tag """
    tagkey = CharField()
    userkey = CharField()
    tag = CharField()
    created_date = DateTimeField(default=datetime.datetime.now)

    def generate_key(self):
        """ Generate hash-based key for publicly shared tag """
        self.tagkey = binascii.hexlify(os.urandom(16))


def get_tags_for_user(userkey):
    """ Extract all tags from the bookmarks """
    bookmarks = Bookmark.select().filter(Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE)
    tags = []
    for bookmark in bookmarks:
        tags += bookmark.tags_list
    return clean_tags(tags)
