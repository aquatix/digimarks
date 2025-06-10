"""digimarks main module."""

import binascii
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated, Optional, Sequence, Type, TypeVar
from urllib.parse import urlparse, urlunparse

import bs4
import httpx
from extract_favicon import from_html
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import AnyUrl, DirectoryPath, FilePath, computed_field
from pydantic_settings import BaseSettings
from sqlmodel import AutoString, Field, Session, SQLModel, create_engine, desc, select

DIGIMARKS_USER_AGENT = 'digimarks/2.0.0-dev'
DIGIMARKS_VERSION = '2.0.0a1'

DEFAULT_THEME = 'freshgreen'


class Settings(BaseSettings):
    """Configuration needed for digimarks to find its database, favicons, API integrations."""

    # outside the codebase
    database_file: FilePath
    favicons_dir: DirectoryPath

    # inside the codebase
    static_dir: DirectoryPath = 'static'
    template_dir: DirectoryPath = 'templates'

    media_url: str = '/static/'

    system_key: str

    debug: bool = False


settings = Settings()
print(settings.model_dump())

engine = create_engine(f'sqlite:///{settings.database_file}', connect_args={'check_same_thread': False})


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
app.mount('/static', StaticFiles(directory=settings.static_dir), name='static')
app.mount('/content/favicons', StaticFiles(directory=settings.favicons_dir), name='favicons')
templates = Jinja2Templates(directory=settings.template_dir)

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


def i_filter_false(predicate, iterable):
    """Filter an iterable if predicate returns True.

    i_filter_false(lambda x: x%2, range(10)) --> 0 2 4 6 8
    """
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
        for element in i_filter_false(seen.__contains__, iterable):
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


def generate_key() -> str:
    """Generate a key to be used for a user or tag."""
    return str(binascii.hexlify(os.urandom(24)))


# Type var used for building custom types for the DB
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


def get_favicon(html_content: str, root_url: str) -> str:
    """Fetch the favicon from `html_content` using `root_url`."""
    favicons = from_html(html_content, root_url=root_url, include_fallbacks=True)
    for favicon in favicons:
        print(favicon.url, favicon.width, favicon.height)
    # TODO: save the preferred image to file and return


class User(SQLModel, table=True):
    """User account."""

    __tablename__ = 'user'

    id: int = Field(primary_key=True)
    username: str
    key: str
    theme: str = Field(default=DEFAULT_THEME)
    created_date: datetime


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

    created_date: datetime = Field(default=datetime.now(UTC))
    modified_date: datetime = Field(default=None)
    deleted_date: datetime = Field(default=None)

    status: int = Field(default=Visibility.VISIBLE)

    @computed_field
    @property
    def tag_list(self) -> list:
        """The tags but as a proper list."""
        if self.tags:
            return self.tags.split(',')
        # Not tags, return empty list instead of [''] that split returns in that case
        return []


async def set_information_from_source(bookmark: Bookmark, request: Request) -> Bookmark:
    """Request the title by requesting the source url."""
    logger.info('Extracting information from url %s', bookmark.url)
    try:
        result = await request.app.requests_client.get(bookmark.url, headers={'User-Agent': DIGIMARKS_USER_AGENT})
        bookmark.http_status = result.status_code
    except httpx.HTTPError as err:
        # For example, 'MissingSchema: Invalid URL 'abc': No schema supplied. Perhaps you meant http://abc?'
        logger.error('Exception when trying to retrieve title for %s. Error: %s', bookmark.url, str(err))
        bookmark.http_status = 404
        bookmark.title = ''
        return bookmark
    if bookmark.http_status == 200 or bookmark.http_status == 202:
        html = bs4.BeautifulSoup(result.text, 'html.parser')
        try:
            bookmark.title = html.title.text.strip()
        except AttributeError:
            bookmark.title = ''

        url_parts = urlparse(str(bookmark.url))
        root_url = url_parts.scheme + '://' + url_parts.netloc
        favicon = get_favicon(result.text, root_url)
        # filename = os.path.join(settings.media_dir, 'favicons/', domain + file_extension)
        # with open(filename, 'wb') as out_file:
        #     shutil.copyfileobj(response.raw, out_file)

    # Extraction was successful
    logger.info('Extracting information was successful')
    return bookmark


def set_tags(bookmark: Bookmark, new_tags: str) -> None:
    """Set tags from `tags`, strip and sort them.

    :param Bookmark bookmark: Bookmark to modify
    :param str new_tags: New tags to sort and set.
    """
    tags_split = new_tags.split(',')
    tags_clean = clean_tags(tags_split)
    bookmark.tags = ','.join(tags_clean)


def strip_url_params(url: str) -> str:
    """Strip URL params from URL.

    :param url: URL to strip URL params from.
    :return: clean URL
    :rtype: str
    """
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, '', parsed.fragment))


def update_bookmark_with_info(bookmark: Bookmark, request: Request, strip_params: bool = False):
    """Automatically update title, favicon, etc."""
    if not bookmark.title:
        # Title was empty, automatically fetch it from the url, will also update the status code
        set_information_from_source(bookmark, request)

    if strip_params:
        # Strip URL parameters, e.g., tracking params
        bookmark.url = AnyUrl(strip_url_params(str(bookmark.url)))

    # Sort and deduplicate tags
    set_tags(bookmark, bookmark.tags)


class PublicTag(SQLModel, table=True):
    """Public tag object."""

    __tablename__ = 'public_tag'

    id: int = Field(primary_key=True)
    tagkey: str
    userkey: str = Field(foreign_key='user.key')
    tag: str
    created_date: datetime = Field(default=datetime.now(UTC))


@app.get('/', response_class=HTMLResponse)
@app.head('/', response_class=HTMLResponse)
def index(request: Request):
    """Homepage, point visitors to project page."""
    return templates.TemplateResponse(
        request=request,
        name='index.html',
        context={'language': 'en', 'version': DIGIMARKS_VERSION, 'theme': DEFAULT_THEME},
    )


@app.get('/api/v1/admin/{system_key}/users/{user_id}', response_model=User)
def get_user(session: SessionDep, system_key: str, user_id: int) -> Type[User]:
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
) -> Sequence[User]:
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
    limit: Annotated[int, Query(le=10000)] = 100,
) -> list[Bookmark]:
    """List all bookmarks in the database. By default gives back 100 items."""
    bookmarks = session.exec(
        select(Bookmark)
        .where(Bookmark.userkey == user_key, Bookmark.status != Visibility.DELETED)
        .offset(offset)
        .limit(limit)
    ).all()
    return bookmarks


@app.get('/api/v1/{user_key}/bookmarks/{url_hash}')
def get_bookmark(
    session: SessionDep,
    user_key: str,
    url_hash: str,
) -> Bookmark:
    """Show bookmark details."""
    bookmark = session.exec(
        select(Bookmark).where(
            Bookmark.userkey == user_key, Bookmark.url_hash == url_hash, Bookmark.status != Visibility.DELETED
        )
    ).first()
    # bookmark = session.get(Bookmark, {'url_hash': url_hash, 'userkey': user_key})
    return bookmark


@app.post('/api/v1/{user_key}/autocomplete_bookmark/', response_model=Bookmark)
def autocomplete_bookmark(
    session: SessionDep,
    request: Request,
    user_key: str,
    bookmark: Bookmark,
    strip_params: bool = False,
):
    """Autofill some fields for this (new) bookmark for user `user_key`."""
    bookmark.userkey = user_key

    # Auto-fill title, fix tags etc.
    update_bookmark_with_info(bookmark, request, strip_params)

    url_hash = generate_hash(str(bookmark.url))
    bookmark_db = session.exec(
        select(Bookmark).where(
            Bookmark.userkey == user_key, Bookmark.url_hash == url_hash, Bookmark.status != Visibility.DELETED
        )
    ).first()
    if bookmark_db:
        # Bookmark with this URL already exists, provide the hash so the frontend can look it up and the user can
        # merge them if so wanted
        bookmark.url_hash = url_hash

    return bookmark


@app.post('/api/v1/{user_key}/bookmarks/', response_model=Bookmark)
def add_bookmark(
    session: SessionDep,
    request: Request,
    user_key: str,
    bookmark: Bookmark,
    strip_params: bool = False,
):
    """Add new bookmark for user `user_key`."""
    bookmark.userkey = user_key

    # Auto-fill title, fix tags etc.
    update_bookmark_with_info(bookmark, request, strip_params)
    bookmark.url_hash = generate_hash(str(bookmark.url))

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
    strip_params: bool = False,
):
    """Update existing bookmark `bookmark_key` for user `user_key`."""
    bookmark_db = session.exec(
        select(Bookmark).where(
            Bookmark.userkey == user_key, Bookmark.url_hash == url_hash, Bookmark.status != Visibility.DELETED
        )
    ).first()
    if not bookmark_db:
        raise HTTPException(status_code=404, detail='Bookmark not found')

    bookmark.modified_date = datetime.now(UTC)

    # 'patch' endpoint, which means that you can send only the data that you want to update, leaving the rest intact
    bookmark_data = bookmark.model_dump(exclude_unset=True)
    # Merge the changed fields into the existing object
    bookmark_db.sqlmodel_update(bookmark_data)

    # Autofill title, fix tags, etc. where (still) needed
    update_bookmark_with_info(bookmark, request, strip_params)

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
    bookmark.deleted_date = datetime.now(UTC)
    bookmark.status = Visibility.DELETED
    session.add(bookmark)
    session.commit()
    return {'ok': True}


@app.get('/api/v1/{user_key}/latest_changes/')
def bookmarks_changed_since(
    session: SessionDep,
    user_key: str,
):
    """Last update on server, so the (browser) client knows whether to fetch an update."""
    latest_modified_bookmark = session.exec(
        select(Bookmark)
        .where(Bookmark.userkey == user_key, Bookmark.status != Visibility.DELETED)
        .order_by(desc(Bookmark.modified_date))
    ).first()
    latest_created_bookmark = session.exec(
        select(Bookmark)
        .where(Bookmark.userkey == user_key, Bookmark.status != Visibility.DELETED)
        .order_by(desc(Bookmark.created_date))
    ).first()

    latest_modification = max(latest_modified_bookmark.modified_date, latest_created_bookmark.created_date)

    return {
        'current_time': datetime.now(UTC),
        'latest_change': latest_modified_bookmark.modified_date,
        'latest_created': latest_created_bookmark.created_date,
        'latest_modification': latest_modification,
    }


@app.get('/api/v1/{user_key}/tags/')
def list_tags_for_user(
    session: SessionDep,
    user_key: str,
) -> list[str]:
    """List all tags in use by the user."""
    bookmarks = session.exec(
        select(Bookmark).where(Bookmark.userkey == user_key, Bookmark.status != Visibility.DELETED)
    ).all()
    tags = []
    for bookmark in bookmarks:
        tags += bookmark.tag_list
    return clean_tags(tags)


@app.get('/api/v1/{user_key}/tags/{tag_key}')
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


@app.get('/{user_key}', response_class=HTMLResponse)
def page_user_landing(
    session: SessionDep,
    request: Request,
    user_key: str,
):
    user = session.exec(select(User).where(User.key == user_key)).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    language = 'en'
    return templates.TemplateResponse(
        request=request,
        name='user_index.html',
        context={'language': language, 'version': DIGIMARKS_VERSION, 'user_key': user_key},
    )
