from datetime import UTC, datetime
from http import HTTPStatus
from typing import Optional, Type, TypeVar

from pydantic import AnyUrl, computed_field
from sqlmodel import AutoString, Field, SQLModel

DEFAULT_THEME = 'freshgreen'


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


class PublicTag(SQLModel, table=True):
    """Public tag object."""

    __tablename__ = 'public_tag'

    id: int = Field(primary_key=True)
    tagkey: str
    userkey: str = Field(foreign_key='user.key')
    tag: str
    created_date: datetime = Field(default=datetime.now(UTC))
