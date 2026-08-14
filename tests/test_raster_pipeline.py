"""The raster path: refuse first, then fetch, then detect.

The refusal tests need no network and are the ones that matter most — they are
what stops the product from spending an hour to return a misleading empty
layer.
"""

import numpy as np
import pytest

from mithra_worker.imagery import Chip, ImageryError
from mithra_worker.raster_pipeline import (
    RunRefused,
    check_targets,
    detect_over_area,
    detector_for,
    fetch_chip,
)


# --- refusals ----------------------------------------------------------------


def test_trees_on_sentinel_2_are_refused_before_any_work():
    with pytest.raises(RunRefused, match="1 m/pixel or sharper"):
        check_targets("sentinel2", ["tree"], None)


def test_the_refusal_names_the_question_that_can_be_answered():
    with pytest.raises(RunRefused, match="try forest_cover instead"):
        check_targets("sentinel2", ["tree"], None)


def test_water_on_sentinel_2_is_allowed():
    check_targets("sentinel2", ["water"], None)  # does not raise


def test_land_cover_from_street_imagery_is_refused():
    with pytest.raises(RunRefused, match="not visible from street"):
        check_targets("mapillary", ["water"], None)


def test_one_impossible_target_refuses_the_whole_run():
    """Half an answer to a two-part question is worse than a clear refusal."""
    with pytest.raises(RunRefused):
        check_targets("sentinel2", ["water", "car"], None)


def test_an_unknown_source_is_refused():
    with pytest.raises(RunRefused, match="unknown imagery source"):
        check_targets("telescope", ["water"], None)


def test_an_upload_can_do_what_its_resolution_allows():
    """Nothing until the file reports itself; then judged on that."""
    with pytest.raises(RunRefused):
        check_targets("upload", ["tree"], None)
    check_targets("upload", ["tree"], 0.3)


# --- detectors ---------------------------------------------------------------


def test_the_water_detector_is_available():
    detector = detector_for("ndwi-water")
    assert "water" in detector.targets


def test_a_declared_but_unbuilt_detector_says_so_plainly():
    """The catalogue lists SAM 3; this build does not ship it, and admits it."""
    with pytest.raises(RunRefused, match="not implemented in this build"):
        detector_for("sam3")


# --- fetching ----------------------------------------------------------------


def test_a_cog_source_needs_a_url():
    with pytest.raises(ImageryError, match="needs a url"):
        fetch_chip("cog", {}, (0, 0, 0.01, 0.01))


def test_an_upload_source_needs_a_path():
    with pytest.raises(ImageryError, match="needs a stored path"):
        fetch_chip("upload", {}, (0, 0, 0.01, 0.01))


def test_street_imagery_is_not_a_raster_source():
    with pytest.raises(ImageryError, match="cannot be read as a raster"):
        fetch_chip("mapillary", {}, (0, 0, 0.01, 0.01))


def test_a_cloudless_window_with_no_scenes_is_reported_not_guessed(monkeypatch):
    """An empty search is a fact about the sky, and has to be said out loud."""
    monkeypatch.setattr("mithra_worker.raster_pipeline.search_stac", lambda *a, **k: [])
    with pytest.raises(ImageryError, match="no sentinel2 scene under"):
        fetch_chip("sentinel2", {"max_cloud": 5}, (59.6, 36.29, 59.61, 36.30))


# --- the whole path, with the network stubbed --------------------------------


def _fake_chip(mask_value: bool = True) -> Chip:
    mask = np.zeros((80, 80), dtype=bool)
    if mask_value:
        mask[10:60, 10:60] = True
    green = np.where(mask, 3000, 1000).astype("uint16")
    nir = np.where(mask, 300, 4000).astype("uint16")
    return Chip(data=np.stack([green, nir]), bounds=(49.40, 37.40, 49.41, 37.41), gsd_m=10.0)


def test_a_run_returns_detections_and_the_provenance_of_the_imagery(monkeypatch):
    monkeypatch.setattr(
        "mithra_worker.raster_pipeline.fetch_chip",
        lambda *a, **k: (_fake_chip(), {"scene_id": "S2_TEST", "captured": "2026-07-03"}),
    )
    found, provenance = detect_over_area(
        "sentinel2", {}, (49.40, 37.40, 49.41, 37.41), ["water"], "ndwi-water"
    )

    assert found and found[0].class_name == "water"
    # A count that cannot name the image it came from is not auditable.
    assert provenance["scene_id"] == "S2_TEST"
    assert provenance["gsd_m"] == 10.0
    assert provenance["pixels"] == [80, 80]


def test_an_area_with_no_water_returns_nothing_rather_than_failing(monkeypatch):
    monkeypatch.setattr(
        "mithra_worker.raster_pipeline.fetch_chip",
        lambda *a, **k: (_fake_chip(mask_value=False), {"scene_id": "S2_DRY"}),
    )
    found, provenance = detect_over_area(
        "sentinel2", {}, (49.40, 37.40, 49.41, 37.41), ["water"], "ndwi-water"
    )
    assert found == []
    assert provenance["scene_id"] == "S2_DRY"


# --- the worker writing detections into the database -------------------------


def test_geojson_becomes_the_well_known_text_postgis_wants():
    """Handing PostGIS raw JSON fails at insert with a parse error that names
    neither the run nor the detection."""
    from mithra_worker.raster_pipeline import geometry_to_ewkt

    ewkt = geometry_to_ewkt(
        {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
    )
    assert ewkt.startswith("SRID=4326;POLYGON")


def test_a_raster_run_writes_features_with_area_and_provenance(monkeypatch, tmp_path):
    """The whole worker path, against a real database."""
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import Session as DbSession

    from tests.conftest import DB_URL

    from mithra_api.db import Base
    from mithra_api.models import Feature, Run, RunStatus

    monkeypatch.setattr(
        "mithra_worker.raster_pipeline.fetch_chip",
        lambda *a, **k: (_fake_chip(), {"scene_id": "S2_TEST", "captured": "2026-07-03"}),
    )

    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    try:
        from mithra_worker.pipeline import run_job

        with DbSession(engine) as session:
            run = Run(
                name="Anzali water",
                kind="bbox",
                source_kind="sentinel2",
                source_config={},
                targets=["water"],
                detector="ndwi-water",
                bbox_west=49.40, bbox_south=37.40, bbox_east=49.41, bbox_north=37.41,
            )
            session.add(run)
            session.commit()
            run_id = run.id

            run_job(session, run_id, client=None, classifier=None, crop_dir=tmp_path)

            session.expire_all()
            done = session.get(Run, run_id)
            assert done.status == RunStatus.SUCCEEDED
            assert done.gsd_m == 10.0

            features = session.scalars(select(Feature).where(Feature.run_id == run_id)).all()
            assert features, "the run found nothing"
            assert features[0].class_name == "water"
            assert features[0].area_m2 > 0
            # The image the count came from, on every row.
            assert features[0].source_value == "S2_TEST"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_an_impossible_run_finishes_refused_rather_than_crashing(monkeypatch, tmp_path):
    """A refusal is an answer — "this cannot be asked of this imagery" — and it
    belongs on the row, not in a stack trace."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session as DbSession

    from tests.conftest import DB_URL

    from mithra_api.db import Base
    from mithra_api.models import Run, RunStatus

    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    try:
        from mithra_worker.pipeline import run_job

        with DbSession(engine) as session:
            run = Run(
                name="trees from space",
                kind="bbox",
                source_kind="sentinel2",
                targets=["tree"],
                detector="ndwi-water",
                bbox_west=49.40, bbox_south=37.40, bbox_east=49.41, bbox_north=37.41,
            )
            session.add(run)
            session.commit()
            run_id = run.id

            run_job(session, run_id, client=None, classifier=None, crop_dir=tmp_path)

            session.expire_all()
            assert session.get(Run, run_id).status == RunStatus.FAILED
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
