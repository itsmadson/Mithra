import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tests.conftest import DB_URL

from bina_api.db import Base, get_session
from bina_api.main import app
from bina_api.models import Job, Session as DbSession, User, UserRole

GOOD_PASSWORD = "a-long-enough-password"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    monkeypatch.setattr("bina_api.routes.jobs.enqueue", lambda job_id: None)
    test_client = TestClient(app)
    test_client.engine = engine
    yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def register_first(client, email="admin@example.com") -> dict:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": GOOD_PASSWORD, "name": "First"},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- first-run ---------------------------------------------------------------


def test_a_fresh_instance_reports_that_it_needs_setup(client):
    assert client.get("/api/auth/setup").json()["needs_setup"] is True


def test_the_first_account_becomes_an_administrator(client):
    assert register_first(client)["role"] == UserRole.ADMIN


def test_the_first_account_is_signed_in_immediately(client):
    register_first(client)
    assert client.get("/api/auth/me").status_code == 200


def test_setup_closes_once_an_account_exists(client):
    register_first(client)
    assert client.get("/api/auth/setup").json()["needs_setup"] is False


def test_open_registration_closes_after_the_first_account(client):
    """Otherwise anyone who can reach the API can grant themselves access."""
    register_first(client)
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/register",
        json={"email": "intruder@example.com", "password": GOOD_PASSWORD},
    )
    assert response.status_code == 401


def test_an_administrator_can_create_further_accounts(client):
    register_first(client)
    response = client.post(
        "/api/auth/register",
        json={"email": "operator@example.com", "password": GOOD_PASSWORD},
    )
    assert response.status_code == 201
    assert response.json()["role"] == UserRole.OPERATOR


# --- credentials -------------------------------------------------------------


def test_login_succeeds_with_the_right_password(client):
    register_first(client)
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": GOOD_PASSWORD}
    )
    assert response.status_code == 200


def test_login_fails_with_the_wrong_password(client):
    register_first(client)
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_an_unknown_email_is_indistinguishable_from_a_wrong_password(client):
    """Different answers would enumerate which addresses have accounts."""
    register_first(client)
    client.post("/api/auth/logout")
    wrong = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "wrong-password"}
    )
    missing = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"]


def test_a_short_password_is_refused_at_registration(client):
    response = client.post(
        "/api/auth/register", json={"email": "a@example.com", "password": "short"}
    )
    assert response.status_code == 422


def test_an_email_can_only_be_registered_once(client):
    register_first(client)
    response = client.post(
        "/api/auth/register",
        json={"email": "admin@example.com", "password": GOOD_PASSWORD},
    )
    assert response.status_code == 409


def test_the_password_is_never_stored_in_the_clear(client):
    register_first(client)
    with Session(client.engine) as session:
        user = session.scalars(select(User)).one()
        assert GOOD_PASSWORD not in user.password_hash


def test_a_disabled_account_cannot_sign_in(client):
    register_first(client)
    client.post("/api/auth/register", json={"email": "op@example.com", "password": GOOD_PASSWORD})
    with Session(client.engine) as session:
        user = session.scalar(select(User).where(User.email == "op@example.com"))
        user.is_active = False
        session.commit()

    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login", json={"email": "op@example.com", "password": GOOD_PASSWORD}
    )
    assert response.status_code == 403


# --- sessions ----------------------------------------------------------------


def test_the_session_cookie_is_not_readable_by_javascript(client):
    register_first(client)
    cookie = client.cookies.jar._cookies  # noqa: SLF001 - inspecting the raw jar
    assert cookie, "no cookie was set"
    # httponly is not exposed by the cookie jar, so assert on the raw header.
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": GOOD_PASSWORD}
    )
    assert "httponly" in response.headers["set-cookie"].lower()


def test_only_the_hash_of_the_session_token_is_stored(client):
    register_first(client)
    token = client.cookies.get("bina_session")
    with Session(client.engine) as session:
        stored = session.scalars(select(DbSession)).one()
        assert stored.token_hash != token
        assert token not in stored.token_hash


def test_logout_ends_the_session_server_side(client):
    register_first(client)
    client.post("/api/auth/logout")
    with Session(client.engine) as session:
        assert session.scalars(select(DbSession)).all() == []
    assert client.get("/api/auth/me").status_code == 401


def test_an_expired_session_does_not_authenticate(client):
    from datetime import UTC, datetime, timedelta

    register_first(client)
    with Session(client.engine) as session:
        stored = session.scalars(select(DbSession)).one()
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_a_forged_session_cookie_does_not_authenticate(client):
    client.cookies.set("bina_session", "not-a-real-token")
    assert client.get("/api/auth/me").status_code == 401


# --- the boundary itself -----------------------------------------------------


ANONYMOUS_FORBIDDEN = [
    ("get", "/api/jobs"),
    ("get", "/api/stats"),
    ("get", "/api/signs"),
    ("get", "/api/labels/queue"),
    ("get", "/api/streets/search?q=test"),
]


@pytest.mark.parametrize("method,path", ANONYMOUS_FORBIDDEN)
def test_data_endpoints_refuse_anonymous_requests(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_creating_a_survey_requires_a_session(client):
    response = client.post("/api/jobs", json={"bbox": [59.60, 36.29, 59.61, 36.30]})
    assert response.status_code == 401


def test_a_survey_records_who_ran_it(client):
    user = register_first(client)
    client.post("/api/jobs", json={"bbox": [59.60, 36.29, 59.61, 36.30]})
    with Session(client.engine) as session:
        job = session.scalars(select(Job)).one()
        assert str(job.owner_id) == user["id"]


def test_only_the_owner_or_an_administrator_may_delete_a_survey(client):
    register_first(client)
    client.post("/api/jobs", json={"bbox": [59.60, 36.29, 59.61, 36.30]})
    with Session(client.engine) as session:
        job_id = str(session.scalars(select(Job)).one().id)

    # A second operator must not be able to destroy someone else's work.
    client.post("/api/auth/register", json={"email": "op@example.com", "password": GOOD_PASSWORD})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "op@example.com", "password": GOOD_PASSWORD})
    assert client.delete(f"/api/jobs/{job_id}").status_code == 403

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": GOOD_PASSWORD}
    )
    assert client.delete(f"/api/jobs/{job_id}").status_code == 204


# --- administration ----------------------------------------------------------


def test_an_operator_cannot_list_accounts(client):
    register_first(client)
    client.post("/api/auth/register", json={"email": "op@example.com", "password": GOOD_PASSWORD})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "op@example.com", "password": GOOD_PASSWORD})
    assert client.get("/api/auth/users").status_code == 403


def test_an_administrator_can_list_and_disable_accounts(client):
    register_first(client)
    created = client.post(
        "/api/auth/register", json={"email": "op@example.com", "password": GOOD_PASSWORD}
    ).json()

    assert len(client.get("/api/auth/users").json()["items"]) == 2
    response = client.patch(f"/api/auth/users/{created['id']}", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_an_administrator_cannot_lock_themselves_out(client):
    admin = register_first(client)
    assert client.patch(f"/api/auth/users/{admin['id']}", json={"is_active": False}).status_code == 422
    assert client.patch(f"/api/auth/users/{admin['id']}", json={"role": "operator"}).status_code == 422


def test_a_label_records_who_made_it(client):
    from bina_api.models import Label, Sign

    user = register_first(client)
    client.post("/api/jobs", json={"bbox": [59.60, 36.29, 59.61, 36.30]})
    with Session(client.engine) as session:
        job = session.scalars(select(Job)).one()
        sign = Sign(
            job_id=job.id,
            mapillary_feature_id="f1",
            geom="SRID=4326;POINT(59.601 36.294)",
            sign_class="unknown",
            confidence=0.1,
            model_version="v1",
            needs_review=True,
        )
        session.add(sign)
        session.commit()
        sign_id = str(sign.id)

    client.post("/api/labels", json={"sign_id": sign_id, "sign_class": "city_entry"})
    with Session(client.engine) as session:
        label = session.scalars(select(Label)).one()
        assert str(label.labelled_by_id) == user["id"]
