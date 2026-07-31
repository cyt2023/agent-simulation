import os
import sys

import pytest
from flask import Flask
from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPOSITORY_ROOT = os.path.dirname(BACKEND_ROOT)
for path in (BACKEND_ROOT, REPOSITORY_ROOT):
    while path in sys.path:
        sys.path.remove(path)
sys.path.insert(0, BACKEND_ROOT)
sys.path.insert(0, REPOSITORY_ROOT)


@pytest.fixture
def token_manager():
    from study1.permissions import Study1TokenManager

    return Study1TokenManager(secret="test-only-secret", max_age_seconds=3600)


@pytest.fixture
def memory_service(token_manager):
    from study1.services import InMemoryStudy1Repository, Study1Service

    return Study1Service(InMemoryStudy1Repository(), token_manager)


@pytest.fixture
def study1_client(memory_service, monkeypatch):
    from study1.routes import set_service_for_testing, study1_bp

    monkeypatch.setenv("STUDY1_TOKEN_SECRET", "test-only-secret")
    monkeypatch.setenv("STUDY1_RESEARCHER_KEY", "researcher-test-key")
    monkeypatch.setenv("STUDY1_INTERNAL_API_KEY", "internal-test-key")
    app = Flask(__name__)
    app.register_blueprint(study1_bp)
    set_service_for_testing(memory_service)
    try:
        yield app.test_client()
    finally:
        set_service_for_testing(None)


@pytest.fixture
def study1_sqlite_engine():
    """SQLite database with the production schema attached as a real namespace."""
    from services.db import get_app_schema
    from study1.models import (
        Study1ArtifactRow,
        Study1EventRow,
        Study1IncidentRow,
        Study1InviteRow,
        Study1MarkerRow,
        Study1MaterialRow,
        Study1ReplayPlanRow,
        Study1SubmissionRow,
    )

    schema = get_app_schema()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _attach_schema(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'ATTACH DATABASE ":memory:" AS "{schema}"')
        cursor.close()

    legacy_metadata = MetaData()
    Table(
        "research_sessions",
        legacy_metadata,
        Column("session_id", String(36), primary_key=True),
        Column("session_name", String(512), nullable=False),
        Column("payload", JSON, nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        schema=schema,
    )
    legacy_metadata.create_all(engine)
    for model in (
        Study1InviteRow,
        Study1EventRow,
        Study1SubmissionRow,
        Study1ArtifactRow,
        Study1IncidentRow,
        Study1MaterialRow,
        Study1MarkerRow,
        Study1ReplayPlanRow,
    ):
        model.__table__.create(engine, checkfirst=True)

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def sql_service(study1_sqlite_engine, token_manager):
    from study1.schema_migrations import run_study1_migrations
    from study1.services import SqlAlchemyStudy1Repository, Study1Service

    run_study1_migrations(study1_sqlite_engine)
    repository = SqlAlchemyStudy1Repository.__new__(SqlAlchemyStudy1Repository)
    repository.SessionLocal = sessionmaker(
        bind=study1_sqlite_engine, autoflush=False, autocommit=False
    )
    return Study1Service(repository, token_manager)
