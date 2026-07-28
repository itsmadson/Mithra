import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bina_api.db import Base
from bina_api.models import Job, JobStatus, Label, Sign

DB_URL = "postgresql+psycopg://bina:bina@localhost:5432/bina"


@pytest.fixture
def session():
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)


def make_job(session) -> Job:
    job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.64, bbox_north=36.33)
    session.add(job)
    session.commit()
    return job


def test_new_job_starts_queued(session):
    assert make_job(session).status == JobStatus.QUEUED


def test_sign_stores_a_geographic_point(session):
    job = make_job(session)
    session.add(
        Sign(
            job_id=job.id,
            mapillary_feature_id="f1",
            image_id="i1",
            geom="SRID=4326;POINT(59.601 36.294)",
            sign_class="street_name",
            confidence=0.8,
            model_version="clip-v1",
        )
    )
    session.commit()
    assert session.scalar(select(Sign)).sign_class == "street_name"


def test_a_feature_cannot_be_counted_twice_in_one_job(session):
    job = make_job(session)
    for _ in range(2):
        session.add(
            Sign(
                job_id=job.id,
                mapillary_feature_id="dup",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class="street_name",
                confidence=0.8,
                model_version="clip-v1",
            )
        )
    with pytest.raises(IntegrityError):
        session.commit()


def test_the_same_feature_may_appear_in_two_different_jobs(session):
    first, second = make_job(session), make_job(session)
    for job in (first, second):
        session.add(
            Sign(
                job_id=job.id,
                mapillary_feature_id="shared",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class="street_name",
                confidence=0.8,
                model_version="clip-v1",
            )
        )
    session.commit()
    assert len(session.scalars(select(Sign)).all()) == 2


def test_label_attaches_to_a_sign(session):
    job = make_job(session)
    sign = Sign(
        job_id=job.id,
        mapillary_feature_id="f1",
        geom="SRID=4326;POINT(59.601 36.294)",
        sign_class="unknown",
        confidence=0.1,
        model_version="clip-v1",
        needs_review=True,
    )
    session.add(sign)
    session.commit()
    session.add(Label(sign_id=sign.id, sign_class="city_entry"))
    session.commit()
    assert session.scalar(select(Label)).sign_class == "city_entry"
