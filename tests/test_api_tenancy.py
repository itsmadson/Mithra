"""One organisation must never see another's inventory.

These tests build two organisations with real surveys and signs, then try every
route from the wrong side. A tenancy bug is not a bug that shows up in normal
use — it shows up as one city reading another city's survey — so the boundary
is tested route by route rather than trusted to a shared helper.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tests.conftest import DB_URL

from bina_api.db import Base, get_session
from bina_api.main import app
from bina_api.models import Job, JobStatus, Sign, User

PASSWORD = "a-long-enough-password"


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


def sign_in(client, email):
    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def two_orgs(client):
    """City A (first account, its own organisation) and City B (a second one).

    A second organisation cannot be created through the API by design — open
    registration is closed — so it is built directly, which is what a real
    second deployment tenant would be.
    """
    client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": PASSWORD, "org_name": "City A"},
    )
    a = client.get("/api/auth/me").json()

    from bina_api.models import Organisation, UserRole
    from bina_api.security import hash_password

    with Session(client.engine) as session:
        org_b = Organisation(name="City B")
        session.add(org_b)
        session.flush()
        session.add(
            User(
                email="b@example.com",
                name="B",
                password_hash=hash_password(PASSWORD),
                role=UserRole.ADMIN,
                org_id=org_b.id,
            )
        )
        session.commit()
        org_b_id = org_b.id

    # One survey with one sign in each organisation.
    ids = {}
    for label, org_id in (("a", a["org_id"]), ("b", str(org_b_id))):
        with Session(client.engine) as session:
            job = Job(
                name=f"survey {label}",
                org_id=org_id,
                bbox_west=59.60,
                bbox_south=36.29,
                bbox_east=59.61,
                bbox_north=36.30,
                status=JobStatus.SUCCEEDED,
            )
            session.add(job)
            session.commit()
            sign = Sign(
                job_id=job.id,
                mapillary_feature_id=f"feature-{label}",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class="street_name",
                confidence=0.3,
                model_version="v1",
                needs_review=True,
                crop_path=f"data/crops/{label}/1.jpg",
            )
            session.add(sign)
            session.commit()
            ids[label] = {"job": str(job.id), "sign": str(sign.id)}
    return ids


# --- reads -------------------------------------------------------------------


def test_the_survey_list_shows_only_your_own(client, two_orgs):
    sign_in(client, "a@example.com")
    names = [item["name"] for item in client.get("/api/jobs").json()["items"]]
    assert names == ["survey a"]


def test_another_organisations_survey_reads_as_absent(client, two_orgs):
    """404 rather than 403: "you may not see this" still confirms it exists."""
    sign_in(client, "a@example.com")
    assert client.get(f"/api/jobs/{two_orgs['b']['job']}").status_code == 404


def test_the_cross_survey_sign_list_is_scoped(client, two_orgs):
    sign_in(client, "a@example.com")
    items = client.get("/api/signs").json()["items"]
    assert len(items) == 1


def test_the_review_queue_is_scoped(client, two_orgs):
    """Both signs need review; only one belongs to this organisation."""
    sign_in(client, "a@example.com")
    items = client.get("/api/labels/queue").json()["items"]
    assert [item["id"] for item in items] == [two_orgs["a"]["sign"]]


def test_the_overview_counts_only_your_own(client, two_orgs):
    sign_in(client, "a@example.com")
    body = client.get("/api/overview").json()
    assert body["signs"]["total"] == 1
    assert body["surveys"]["total"] == 1


def test_features_and_export_refuse_another_organisations_survey(client, two_orgs):
    sign_in(client, "a@example.com")
    job_b = two_orgs["b"]["job"]
    assert client.get(f"/api/jobs/{job_b}/features").status_code == 404
    assert client.get(f"/api/jobs/{job_b}/export.csv").status_code == 404
    assert client.get(f"/api/jobs/{job_b}/signs").status_code == 404


def test_a_crop_from_another_organisation_is_not_served(client, two_orgs):
    sign_in(client, "a@example.com")
    assert client.get(f"/api/crops/{two_orgs['b']['sign']}").status_code == 404


# --- writes ------------------------------------------------------------------


def test_you_cannot_delete_another_organisations_survey(client, two_orgs):
    sign_in(client, "a@example.com")
    assert client.delete(f"/api/jobs/{two_orgs['b']['job']}").status_code == 404

    # And it is still there afterwards.
    with Session(client.engine) as session:
        assert session.get(Job, two_orgs["b"]["job"]) is not None


def test_you_cannot_label_another_organisations_sign(client, two_orgs):
    """Otherwise one tenant writes into another's training data."""
    sign_in(client, "a@example.com")
    response = client.post(
        "/api/labels",
        json={"sign_id": two_orgs["b"]["sign"], "sign_class": "city_entry"},
    )
    assert response.status_code == 404


def test_a_new_survey_belongs_to_your_organisation(client, two_orgs):
    user = sign_in(client, "a@example.com")
    client.post("/api/jobs", json={"bbox": [59.60, 36.29, 59.61, 36.30]})
    with Session(client.engine) as session:
        job = session.scalar(select(Job).order_by(Job.created_at.desc()))
        assert str(job.org_id) == user["org_id"]


# --- accounts ----------------------------------------------------------------


def test_an_administrator_sees_only_their_own_organisations_accounts(client, two_orgs):
    sign_in(client, "a@example.com")
    emails = [u["email"] for u in client.get("/api/auth/users").json()["items"]]
    assert emails == ["a@example.com"]


def test_an_administrator_cannot_modify_another_organisations_account(client, two_orgs):
    sign_in(client, "a@example.com")
    with Session(client.engine) as session:
        other = session.scalar(select(User).where(User.email == "b@example.com"))
        other_id = str(other.id)

    response = client.patch(f"/api/auth/users/{other_id}", json={"is_active": False})
    assert response.status_code == 404


def test_an_account_created_by_an_administrator_joins_their_organisation(client, two_orgs):
    user = sign_in(client, "a@example.com")
    created = client.post(
        "/api/auth/register", json={"email": "colleague@example.com", "password": PASSWORD}
    ).json()
    assert created["org_id"] == user["org_id"]


def test_the_first_account_names_its_organisation(client):
    client.post(
        "/api/auth/register",
        json={"email": "first@example.com", "password": PASSWORD, "org_name": "Mashhad"},
    )
    assert client.get("/api/auth/me").json()["org_name"] == "Mashhad"
