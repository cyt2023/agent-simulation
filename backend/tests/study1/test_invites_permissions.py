from concurrent.futures import ThreadPoolExecutor

from study1.models import HUMAN_ROLES
from study1.services import Study1ServiceError, hash_invite_token


def test_three_invites_bind_three_distinct_roles_and_store_only_hash(memory_service):
    result = memory_service.create_session("study-one")
    invites = result["invites"]
    assert {item["role"] for item in invites} == {role.value for role in HUMAN_ROLES}
    assert len({item["participant_id"] for item in invites}) == 3
    assert len({item["token"] for item in invites}) == 3
    stored = memory_service.repository.invites
    for item in invites:
        assert item["token"] not in stored
        assert hash_invite_token(item["token"]) in stored


def test_invite_cannot_be_exchanged_twice(memory_service):
    invite = memory_service.create_session("study-one")["invites"][0]
    first = memory_service.exchange_invite(invite["token"])
    assert first["identity"]["role"] == invite["role"]
    try:
        memory_service.exchange_invite(invite["token"])
        raise AssertionError("second exchange unexpectedly succeeded")
    except Study1ServiceError as error:
        assert error.code == "INVITE_ALREADY_USED"
        assert error.status == 409


def test_concurrent_exchange_has_exactly_one_success(memory_service):
    invite = memory_service.create_session("study-one")["invites"][0]

    def redeem():
        try:
            memory_service.exchange_invite(invite["token"])
            return "ok"
        except Study1ServiceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: redeem(), range(2)))
    assert sorted(results) == ["INVITE_ALREADY_USED", "ok"]


def _researcher_token(client):
    response = client.post(
        "/api/study1/auth/researcher", json={"key": "researcher-test-key"}
    )
    assert response.status_code == 200
    return response.get_json()["token"]


def test_create_session_requires_server_verified_researcher(study1_client):
    denied = study1_client.post("/api/study1/sessions", json={"session_name": "x"})
    assert denied.status_code == 401
    token = _researcher_token(study1_client)
    created = study1_client.post(
        "/api/study1/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_name": "x"},
    )
    assert created.status_code == 201
    assert len(created.get_json()["invites"]) == 3


def test_me_identity_ignores_client_role_and_rejects_other_session(study1_client):
    researcher = _researcher_token(study1_client)
    headers = {"Authorization": f"Bearer {researcher}"}
    created = study1_client.post(
        "/api/study1/sessions", headers=headers, json={"session_name": "x"}
    ).get_json()
    invite = next(i for i in created["invites"] if i["role"] == "principal")
    exchange = study1_client.post(
        f"/api/study1/invites/{invite['token']}/exchange",
        json={"role": "researcher"},
    ).get_json()
    participant_headers = {"Authorization": f"Bearer {exchange['token']}"}
    me = study1_client.get(
        f"/api/study1/sessions/{invite['session_id']}/me",
        headers=participant_headers,
    )
    assert me.status_code == 200
    assert me.get_json()["identity"]["role"] == "principal"
    mismatch = study1_client.get(
        "/api/study1/sessions/not-my-session/me", headers=participant_headers
    )
    assert mismatch.status_code == 403
