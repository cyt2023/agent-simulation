import os
import sys

import pytest
from flask import Flask


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


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
