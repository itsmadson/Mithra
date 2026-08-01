"""Insert one finished job so the e2e run never depends on Mapillary."""

import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from bina_api.db import Base
from bina_api.models import Job, JobStatus, Sign, User, UserRole
from bina_api.security import hash_password

DB_URL = "postgresql+psycopg://bina:bina@localhost:5434/bina"
JOB_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
E2E_EMAIL = "e2e@example.com"
E2E_PASSWORD = "a-long-enough-password"


def main() -> None:
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.query(Sign).filter(Sign.job_id == JOB_ID).delete()
        session.query(Job).filter(Job.id == JOB_ID).delete()
        session.commit()
        session.add(
            Job(
                id=JOB_ID,
                bbox_west=59.600,
                bbox_south=36.293,
                bbox_east=59.609,
                bbox_north=36.302,
                status=JobStatus.SUCCEEDED,
                tile_count=1,
                failed_tile_count=0,
            )
        )
        session.commit()
        for i, (sign_class, confidence) in enumerate(
            [
                ("street_name", 0.91),
                ("street_name", 0.88),
                ("direction_guide", 0.79),
                ("unknown", 0.12),
            ]
        ):
            session.add(
                Sign(
                    job_id=JOB_ID,
                    mapillary_feature_id=f"seed{i}",
                    geom=f"SRID=4326;POINT(59.60{i} 36.29{i})",
                    sign_class=sign_class,
                    confidence=confidence,
                    model_version="seed-v1",
                    needs_review=(sign_class == "unknown"),
                )
            )
        session.commit()
    # Every route now requires a session, so the browser suite needs an
    # account to sign in with.
    with Session(engine) as session:
        if session.query(User).filter(User.email == E2E_EMAIL).first() is None:
            session.add(
                User(
                    email=E2E_EMAIL,
                    name="E2E",
                    password_hash=hash_password(E2E_PASSWORD),
                    role=UserRole.ADMIN,
                )
            )
            session.commit()

    print(f"seeded job {JOB_ID} and account {E2E_EMAIL}")


if __name__ == "__main__":
    main()
