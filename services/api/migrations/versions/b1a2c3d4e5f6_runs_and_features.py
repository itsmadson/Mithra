"""Generalise surveys into runs and signs into features.

A rename rather than a rebuild: existing rows are surveys of road signs, and
they stay exactly that — the same inventory, described in words that also fit a
lake outline or a tree crown.

Revision ID: b1a2c3d4e5f6
Revises: 13de18a5b43a
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "13de18a5b43a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("jobs", "runs")
    op.rename_table("job_tiles", "run_tiles")
    op.rename_table("signs", "features")

    op.alter_column("run_tiles", "job_id", new_column_name="run_id")
    op.alter_column("features", "job_id", new_column_name="run_id")
    op.alter_column("features", "sign_class", new_column_name="class_name")
    op.alter_column("features", "mapillary_feature_id", new_column_name="source_feature_id")
    op.alter_column("features", "mapillary_value", new_column_name="source_value")
    op.alter_column("labels", "sign_id", new_column_name="feature_id")
    op.alter_column("labels", "sign_class", new_column_name="class_name")

    # A class is free text now: it comes from the catalogue, which grows with
    # every detector added, and an enum-width column would have to be migrated
    # every time somebody wants to find swimming pools.
    op.alter_column("features", "class_name", type_=sa.String(64))
    op.alter_column("labels", "class_name", type_=sa.String(64))
    op.alter_column("features", "source_feature_id", type_=sa.String(120))

    # A detection is a location or an outline. Forcing a lake into a point
    # loses the answer the question was asking for.
    op.execute(
        "ALTER TABLE features ALTER COLUMN geom TYPE geometry(Geometry, 4326) "
        "USING geom::geometry(Geometry, 4326)"
    )
    op.add_column("features", sa.Column("area_m2", sa.Float(), nullable=True))

    # What the run read, and what it was looking for.
    op.add_column(
        "runs",
        sa.Column("source_kind", sa.String(24), nullable=False, server_default="mapillary"),
    )
    op.add_column(
        "runs",
        sa.Column(
            "source_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("runs", sa.Column("gsd_m", sa.Float(), nullable=True))
    op.add_column(
        "runs",
        sa.Column(
            "targets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='["sign"]',
        ),
    )
    op.add_column(
        "runs",
        sa.Column("detector", sa.String(40), nullable=False, server_default="clip-zeroshot"),
    )
    op.create_index("ix_runs_source_kind", "runs", ["source_kind"])

    # Existing rows are Mapillary street surveys; say so explicitly rather than
    # leaving them to a default that might change later.
    op.execute(
        "UPDATE runs SET source_kind = 'mapillary', gsd_m = 0.05, "
        "targets = '[\"sign\"]'::jsonb, detector = 'clip-zeroshot'"
    )

    op.drop_constraint("uq_sign_per_job", "features", type_="unique")
    op.create_unique_constraint(
        "uq_feature_per_run", "features", ["run_id", "source_feature_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_feature_per_run", "features", type_="unique")
    op.create_unique_constraint(
        "uq_sign_per_job", "features", ["run_id", "source_feature_id"]
    )
    op.drop_index("ix_runs_source_kind", table_name="runs")
    for column in ("detector", "targets", "gsd_m", "source_config", "source_kind"):
        op.drop_column("runs", column)
    op.drop_column("features", "area_m2")
    op.execute(
        "ALTER TABLE features ALTER COLUMN geom TYPE geometry(Point, 4326) "
        "USING geom::geometry(Point, 4326)"
    )
    op.alter_column("labels", "class_name", new_column_name="sign_class", type_=sa.String(32))
    op.alter_column("labels", "feature_id", new_column_name="sign_id")
    op.alter_column("features", "source_value", new_column_name="mapillary_value")
    op.alter_column(
        "features", "source_feature_id", new_column_name="mapillary_feature_id",
        type_=sa.String(64),
    )
    op.alter_column("features", "class_name", new_column_name="sign_class", type_=sa.String(32))
    op.alter_column("features", "run_id", new_column_name="job_id")
    op.alter_column("run_tiles", "run_id", new_column_name="job_id")
    op.rename_table("features", "signs")
    op.rename_table("run_tiles", "job_tiles")
    op.rename_table("runs", "jobs")
