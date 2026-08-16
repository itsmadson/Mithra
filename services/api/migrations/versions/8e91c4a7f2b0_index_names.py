"""rename indexes left behind by the jobs->runs rename

Revision ID: 8e91c4a7f2b0
Revises: 7d68844c2dba
Create Date: 2026-08-16

The tables became runs and features several migrations ago, but their indexes
kept the names they were created with, so the database still had
ix_signs_sign_class on a table called features. Nothing breaks; it just lies to
whoever reads the schema next.

Renamed rather than dropped and recreated: a rename is instant and metadata
only, while a rebuild would take a lock and a table scan for no benefit, and
would leave a window with no index on a table the inventory queries constantly.
Every rename is guarded, so a database created after the rename — where the
indexes already carry the new names — is left alone.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "8e91c4a7f2b0"
down_revision: Union[str, Sequence[str], None] = "7d68844c2dba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RENAMES = [
    ("idx_signs_geom", "idx_features_geom"),
    ("ix_signs_job_id", "ix_features_run_id"),
    ("ix_signs_mapillary_feature_id", "ix_features_source_feature_id"),
    ("ix_signs_needs_review", "ix_features_needs_review"),
    ("ix_signs_sign_class", "ix_features_class_name"),
    ("ix_labels_sign_id", "ix_labels_feature_id"),
    ("ix_job_tiles_job_id", "ix_run_tiles_run_id"),
    ("idx_jobs_geom", "idx_runs_geom"),
    ("ix_jobs_kind", "ix_runs_kind"),
    ("ix_jobs_org_id", "ix_runs_org_id"),
    ("ix_jobs_owner_id", "ix_runs_owner_id"),
    ("ix_jobs_status", "ix_runs_status"),
]


def _rename(old: str, new: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_class WHERE relname = '{old}')
               AND NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = '{new}') THEN
                ALTER INDEX {old} RENAME TO {new};
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    for old, new in RENAMES:
        _rename(old, new)


def downgrade() -> None:
    for old, new in RENAMES:
        _rename(new, old)
