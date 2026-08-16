"""The audit log: what it records, and who may read it.

An audit log is only worth keeping if it is complete, scoped, and impossible to
edit from inside the application. Each of those is tested here, because each
fails silently — a missing record looks exactly like an action nobody took.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tests.conftest import DB_URL

from mithra_api.db import Base, get_session
from mithra_api.main import app
from mithra_api.models import AuditEvent, Feature, Organisation, Run, RunStatus, User, UserRole
from mithra_api.security import hash_password

PASSWORD = "a-long-enough-password"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    monkeypatch.setattr("mithra_api.routes.runs.enqueue", lambda run_id: None)
    test_client = TestClient(app)
    test_client.engine = engine
    yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def admin(client):
    client.post(
        "/api/auth/register",
        json={"email": "admin@example.com", "password": PASSWORD, "org_name": "City A"},
    )
    return client.get("/api/auth/me").json()


def events(client, query=""):
    response = client.get(f"/api/audit?{query}")
    assert response.status_code == 200, response.text
    return response.json()


def actions_of(client) -> list[str]:
    return [item["action"] for item in events(client)["items"]]


# --- what gets recorded ------------------------------------------------------


def test_the_first_account_records_both_its_creation_and_its_sign_in(client, admin):
    recorded = actions_of(client)
    assert "account.created" in recorded
    assert "auth.login" in recorded


def test_signing_in_is_recorded(client, admin):
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
    assert actions_of(client).count("auth.login") == 2


def test_a_failed_sign_in_is_recorded_with_the_address_that_was_tried(client, admin):
    """A run of failures against one address is the signal somebody comes here
    looking for, and it cannot be reconstructed after the fact."""
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong-one"})
    failures = [e for e in events(client)["items"] if e["action"] == "auth.login_failed"]
    assert len(failures) == 1
    assert failures[0]["actor_email"] == "admin@example.com"


def test_a_failed_sign_in_for_an_unknown_address_records_nothing_readable(client, admin):
    """No organisation owns it, so it belongs to the deployment, not a tenant."""
    client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert "auth.login_failed" not in actions_of(client)


def test_signing_out_is_recorded_against_the_person_who_did_it(client, admin):
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
    logouts = [e for e in events(client)["items"] if e["action"] == "auth.logout"]
    assert logouts and logouts[0]["actor_email"] == "admin@example.com"


def test_creating_an_account_names_the_administrator_who_did_it(client, admin):
    client.post(
        "/api/auth/register", json={"email": "colleague@example.com", "password": PASSWORD}
    )
    created = [e for e in events(client)["items"] if e["action"] == "account.created"]
    # Two: the first account, then the colleague.
    assert len(created) == 2
    newest = created[0]
    assert newest["actor_email"] == "admin@example.com"
    assert newest["detail"]["email"] == "colleague@example.com"


def test_a_role_change_records_what_it_was_before(client, admin):
    """"Role changed" without the values answers none of the questions anyone
    asks a log."""
    colleague = client.post(
        "/api/auth/register", json={"email": "colleague@example.com", "password": PASSWORD}
    ).json()
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
    client.patch(f"/api/auth/users/{colleague['id']}", json={"role": "admin"})

    changes = [e for e in events(client)["items"] if e["action"] == "account.updated"]
    assert changes[0]["detail"]["changes"]["role"] == {"from": "operator", "to": "admin"}


def test_a_patch_that_changes_nothing_records_nothing(client, admin):
    colleague = client.post(
        "/api/auth/register", json={"email": "colleague@example.com", "password": PASSWORD}
    ).json()
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
    client.patch(f"/api/auth/users/{colleague['id']}", json={"role": "operator"})
    assert "account.updated" not in actions_of(client)


def test_starting_a_run_records_what_was_asked_for(client, admin):
    client.post("/api/runs", json={"bbox": [59.60, 36.29, 59.61, 36.30]})
    runs = [e for e in events(client)["items"] if e["action"] == "run.created"]
    assert len(runs) == 1
    assert runs[0]["subject_type"] == "run"


def test_relabelling_records_the_class_it_replaced(client, admin):
    """The row is overwritten in place, so the model's original answer exists
    nowhere else afterwards."""
    with Session(client.engine) as session:
        run = Run(
            name="survey",
            org_id=admin["org_id"],
            bbox_west=59.6,
            bbox_south=36.29,
            bbox_east=59.61,
            bbox_north=36.30,
            status=RunStatus.SUCCEEDED,
        )
        session.add(run)
        session.commit()
        feature = Feature(
            run_id=run.id,
            source_feature_id="f1",
            geom="SRID=4326;POINT(59.601 36.294)",
            class_name="unknown",
            confidence=0.2,
            needs_review=True,
            model_version="clip-v1",
        )
        session.add(feature)
        session.commit()
        feature_id = str(feature.id)

    client.post("/api/labels", json={"feature_id": feature_id, "class_name": "city_entry"})
    labelled = [e for e in events(client)["items"] if e["action"] == "feature.labelled"]
    assert labelled[0]["detail"]["from"] == "unknown"
    assert labelled[0]["detail"]["to"] == "city_entry"
    assert labelled[0]["detail"]["model_version"] == "clip-v1"


def test_deleting_a_run_records_how_much_it_destroyed(client, admin):
    created = client.post("/api/runs", json={"bbox": [59.60, 36.29, 59.61, 36.30]}).json()
    client.delete(f"/api/runs/{created['id']}")
    deleted = [e for e in events(client)["items"] if e["action"] == "run.deleted"]
    assert len(deleted) == 1
    assert "features" in deleted[0]["detail"]


def test_reads_are_not_recorded(client, admin):
    """Recording every list request buries the four events somebody actually
    comes looking for."""
    before = events(client)["total"]
    client.get("/api/features")
    client.get("/api/runs")
    client.get("/api/overview")
    assert events(client)["total"] == before


# --- who may read it ---------------------------------------------------------


def test_an_operator_may_not_read_the_log(client, admin):
    client.post("/api/auth/register", json={"email": "op@example.com", "password": PASSWORD})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "op@example.com", "password": PASSWORD})
    assert client.get("/api/audit").status_code == 403


def test_signed_out_callers_may_not_read_the_log(client, admin):
    client.post("/api/auth/logout")
    assert client.get("/api/audit").status_code == 401


def test_another_organisations_events_are_not_visible(client, admin):
    """The log names people and addresses; leaking it across tenants is worse
    than leaking the inventory it describes."""
    with Session(client.engine) as session:
        other = Organisation(name="City B")
        session.add(other)
        session.flush()
        session.add(
            User(
                email="b@example.com",
                name="B",
                password_hash=hash_password(PASSWORD),
                role=UserRole.ADMIN,
                org_id=other.id,
            )
        )
        session.add(
            AuditEvent(
                org_id=other.id,
                actor_email="b@example.com",
                action="run.deleted",
                detail={"name": "their survey"},
            )
        )
        session.commit()

    assert all(e["actor_email"] != "b@example.com" for e in events(client)["items"])
    assert "run.deleted" not in actions_of(client)


def test_the_action_filter_only_offers_what_this_organisation_did(client, admin):
    body = client.get("/api/audit/actions").json()
    assert {item["key"] for item in body["actions"]} <= {
        "auth.login",
        "auth.logout",
        "auth.login_failed",
        "account.created",
        "account.updated",
        "run.created",
        "run.deleted",
        "feature.labelled",
    }


# --- shape -------------------------------------------------------------------


def test_the_log_is_newest_first(client, admin):
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
    stamps = [event["created_at"] for event in events(client)["items"]]
    assert stamps == sorted(stamps, reverse=True)


def test_filtering_by_action_narrows_the_log(client, admin):
    client.post("/api/runs", json={"bbox": [59.60, 36.29, 59.61, 36.30]})
    body = events(client, "action=run.created")
    assert body["total"] == 1
    assert body["items"][0]["action"] == "run.created"


def test_there_is_no_way_to_write_or_delete_through_the_api(client, admin):
    """Append-only is a property of the routes, not a convention."""
    event_id = events(client)["items"][0]["id"]
    assert client.post("/api/audit", json={}).status_code in (404, 405)
    assert client.delete(f"/api/audit/{event_id}").status_code in (404, 405)
    assert client.patch(f"/api/audit/{event_id}", json={}).status_code in (404, 405)


def test_an_event_outlives_the_account_that_made_it(client, admin):
    """Deleting an account must not erase what it did."""
    colleague = client.post(
        "/api/auth/register", json={"email": "colleague@example.com", "password": PASSWORD}
    ).json()
    with Session(client.engine) as session:
        session.delete(session.get(User, colleague["id"]))
        session.commit()

        remaining = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "account.created")
        ).all()
        # The row survives, its actor link is cleared, and the email it recorded
        # is still readable.
        assert any(event.detail and event.detail.get("email") == "colleague@example.com"
                   for event in remaining)


def test_recording_never_breaks_the_action_it_describes(client, admin, monkeypatch):
    """An audit write that can fail a survey turns a log into an availability
    risk. The gap is reported to the application log instead."""
    from mithra_api import audit

    def explode(*args, **kwargs):
        raise RuntimeError("audit table is on fire")

    monkeypatch.setattr(audit.AuditEvent, "__init__", explode)
    response = client.post("/api/runs", json={"bbox": [59.60, 36.29, 59.61, 36.30]})
    assert response.status_code == 201
