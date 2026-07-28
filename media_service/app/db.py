from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import Settings
from .models import Base


def create_database_engine(settings: Settings) -> Engine:
    url = settings.media_database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs.update(
            {
                "connect_args": {"check_same_thread": False},
                "poolclass": StaticPool,
            }
        )
    engine = create_engine(url, **kwargs)
    schema = None if url.startswith("sqlite") else settings.media_database_schema
    return engine.execution_options(schema_translate_map={"media": schema})


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_database_engine(settings)
        self.session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, class_=Session
        )

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        with self.session_factory() as value:
            yield value
