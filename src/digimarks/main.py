"""digimarks main module."""

import binascii
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated, Optional, Type, TypeVar

import bs4
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import AnyUrl, DirectoryPath, FilePath
from pydantic_settings import BaseSettings
from sqlmodel import AutoString, Field, Session, SQLModel, create_engine, select

DIGIMARKS_USER_AGENT = 'digimarks/2.0.0-dev'

DEFAULT_THEME = 'freshgreen'


class Settings(BaseSettings):
    """Configuration needed for digimarks to find its database, favicons, API integrations."""

    # database_file: FilePath = './bookmarks.db'
    database_file: FilePath
    media_dir: DirectoryPath
    media_url: str = '/static/'

    mashape_api_key: str

    system_key: str

    debug: bool = False


settings = Settings()
print(settings.model_dump())

engine = create_engine(f'sqlite:///{settings.database_file}', connect_args={'check_same_thread': False})
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session():
    """SQLAlchemy session factory."""
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(the_app: FastAPI):
    """Upon start, initialise an AsyncClient and assign it to an attribute named requests_client on the app object."""
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


def clean_tags(tags_list: list) -> list:
    """Generate a unique list of the tags.

    :param list tags_list: List with all tags
    :return: deduplicated list of the tags, without leading or trailing whitespace
    :rtype: list
    """
    tags_res = [x.strip() for x in tags_list]
    tags_res = list(unique_ever_seen(tags_res))
    tags_res.sort()
    if tags_res and tags_res[0] == '':
        del tags_res[0]
    return tags_res


def file_type(filename: str) -> str:
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


def generate_hash(input_text: str) -> str:
    """Generate a hash from string `input`, e.g., for a URL."""
    return hashlib.md5(input_text.encode('utf-8')).hexdigest()


def generate_key():
    """Generate a key to be used for a user or tag."""
    return binascii.hexlify(os.urandom(24))


T = TypeVar('T')


def build_custom_type(internal_type: Type[T]) -> Type[AutoString]:
    """Create a type that is compatible with the database.

    Based on https://github.com/fastapi/sqlmodel/discussions/847
    """

    class CustomType(AutoString):
        def process_bind_param(self, value, dialect) -> Optional[str]:
            if value is None:
                return None

            if isinstance(value, str):
                # Test if value is valid to avoid `process_result_value` failing
                try:
                    internal_type(value)  # type: ignore[call-arg]
                except ValueError as e:
                    raise ValueError(f'Invalid value for {internal_type.__name__}: {e}') from e

            return str(value)

        def process_result_value(self, value, dialect) -> Optional[T]:
            if value is None:
                return None

            return internal_type(value)  # type: ignore[call-arg]

    return CustomType


class User(SQLModel, table=True):
    """User account."""

    __tablename__ = 'user'

    id: int = Field(primary_key=True)
    username: str
    key: str
    theme: str = Field(default=DEFAULT_THEME)
    created_date: datetime

    def generate_key(self):
        """Generate user key."""
        self.key = binascii.hexlify(os.urandom(24))
        return self.key


class Visibility:
    """Options for visibility of an object."""

    VISIBLE = 0
    DELETED = 1


class Bookmark(SQLModel, table=True):
    """Bookmark object."""

    __tablename__ = 'bookmark'

    id: int = Field(primary_key=True)
    userkey: str = Field(foreign_key='user.key')
    title: str = Field(default='')
    url: AnyUrl = Field(default='', sa_type=build_custom_type(AnyUrl))
    note: str = Field(default='')
    # image: str = Field(default='')
    url_hash: str = Field(default='')
    tags: str = Field(default='')
    starred: bool = Field(default=False)

    favicon: str | None = Field(default=None)

    http_status: int = Field(default=HTTPStatus.OK)

    created_date: datetime = Field(default=datetime.now(timezone.utc))
    modified_date: datetime = Field(default=None)
    deleted_date: datetime = Field(default=None)

    status: int = Field(default=Visibility.VISIBLE)

    def set_title_from_source(self, request: Request) -> str:
        """Request the title by requesting the source url."""
        try:
            result = request.app.requests_client.get(self.url, headers={'User-Agent': DIGIMARKS_USER_AGENT})
            self.http_status = result.status_code
        except httpx.HTTPError as err:
            # For example, 'MissingSchema: Invalid URL 'abc': No schema supplied. Perhaps you meant http://abc?'
            logger.error('Exception when trying to retrieve title for %s. Error: %s', self.url, str(err))
            self.http_status = 404
            self.title = ''
            return self.title
        if self.http_status == 200 or self.http_status == 202:
            html = bs4.BeautifulSoup(result.text, 'html.parser')
            try:
                self.title = html.title.text.strip()
            except AttributeError:
                self.title = ''
        return self.title

    @property
    def tags_list(self):
        """Get the tags as a list, iterable in template."""
        if self.tags:
            return self.tags.split(',')
        return []


class PublicTag(SQLModel, table=True):
    """Public tag object."""

    __tablename__ = 'public_tag'

    id: int = Field(primary_key=True)
    tagkey: str
    userkey: str = Field(foreign_key='user.key')
    tag: str
    created_date: datetime = Field(default=datetime.now(timezone.utc))


@app.get('/')
def index():
    """Homepage, point visitors to project page."""
    # theme = themes[DEFAULT_THEME]
    # return render_template('index.html', theme=theme)
    return {}


@app.get('/api/v1/admin/{system_key}/users/{user_id}')
def get_user(session: SessionDep, system_key: str, user_id: int) -> User:
    """Show user information."""
    if system_key != settings.system_key:
        raise HTTPException(status_code=404)

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    return user


# @app.get('/admin/{system_key}/users/', response_model=list[User])
@app.get('/api/v1/admin/{system_key}/users/')
def list_users(
    session: SessionDep,
    system_key: str,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
) -> list[User]:
    """List all users in the database.

    :param SessionDep session:
    :param str system_key: secrit key
    :param int offset: [Optional] offset of pagination
    :param int limit: [Optional] limits the number of users to return, defaults to 100
    :return: list of users in the system
    :rtype: list[User]
    """
    if system_key != settings.system_key:
        raise HTTPException(status_code=404)

    users = session.exec(select(User).offset(offset).limit(limit)).all()
    return users


@app.get('/api/v1/{user_key}/bookmarks/')
def list_bookmarks(
    session: SessionDep,
    user_key: str,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
) -> list[Bookmark]:
    """List all bookmarks in the database."""
    bookmarks = session.exec(select(Bookmark).where(Bookmark.userkey == user_key).offset(offset).limit(limit)).all()
    return bookmarks


@app.get('/api/v1/{user_key}/bookmarks/{url_hash}')
def get_bookmark(
    session: SessionDep,
    user_key: str,
    url_hash: str,
) -> Bookmark:
    """Show bookmark details."""
    bookmark = session.exec(select(Bookmark).where(Bookmark.userkey == user_key, Bookmark.url_hash == url_hash)).first()
    # bookmark = session.get(Bookmark, {'url_hash': url_hash, 'userkey': user_key})
    return bookmark


@app.post('/api/v1/{user_key}/bookmarks/', response_model=Bookmark)
def add_bookmark(
    session: SessionDep,
    request: Request,
    user_key: str,
    bookmark: Bookmark,
):
    """Add new bookmark for user `user_key`."""
    bookmark.userkey = user_key
    bookmark.url_hash = generate_hash(str(bookmark.url))
    # if strip_params:
    #     url = Bookmark.strip_url_params(url)
    if not bookmark.title:
        # Title was empty, automatically fetch it from the url, will also update the status code
        bookmark.set_title_from_source(request)
    session.add(bookmark)
    session.commit()
    session.refresh(bookmark)
    return bookmark


@app.patch('/api/v1/{user_key}/bookmarks/{url_hash}', response_model=Bookmark)
def update_bookmark(
    session: SessionDep,
    request: Request,
    user_key: str,
    bookmark: Bookmark,
    url_hash: str,
):
    """Update existing bookmark `bookmark_key` for user `user_key`."""
    bookmark_db = session.get(Bookmark, {'url_hash': url_hash, 'userkey': user_key})
    if not bookmark_db:
        raise HTTPException(status_code=404, detail='Bookmark not found')
    bookmark_data = bookmark.model_dump(exclude_unset=True)
    bookmark_db.sqlmodel_update(bookmark_data)
    if not bookmark_db.title:
        # Title was empty, automatically fetch it from the url, will also update the status code
        bookmark.set_title_from_source(request)
    bookmark.modified_date = datetime.now(timezone.utc)
    session.add(bookmark_db)
    session.commit()
    session.refresh(bookmark_db)
    return bookmark_db


@app.delete('/api/v1/{user_key}/bookmarks/{url_hash}', response_model=Bookmark)
def delete_bookmark(
    session: SessionDep,
    user_key: str,
    url_hash: str,
):
    """(Soft)Delete bookmark `bookmark_key` for user `user_key`."""
    bookmark = session.get(Bookmark, {'url_hash': url_hash, 'userkey': user_key})
    if not bookmark:
        raise HTTPException(status_code=404, detail='Bookmark not found')
    bookmark.deleted_date = datetime.now(timezone.utc)
    bookmark.status = Visibility.DELETED
    session.add(bookmark)
    session.commit()
    return {'ok': True}


@app.get('/api/v1/{user_key}/tags/')
def list_tags_for_user(
    session: SessionDep,
    user_key: str,
) -> list[str]:
    """List all tags in use by the user."""
    bookmarks = session.exec(select(Bookmark).where(Bookmark.userkey == user_key)).all()
    tags = []
    for bookmark in bookmarks:
        tags += bookmark.tags_list
    return clean_tags(tags)
