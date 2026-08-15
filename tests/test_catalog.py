"""What may be detected, and the refusals that keep the product honest.

The catalogue's job is not to list capabilities — it is to refuse the
combinations that cannot work, before a run starts, with a reason a person can
act on. These tests are mostly about the refusals.
"""

import pytest

from mithra_ml.catalog import (
    DETECTORS_BY_KEY,
    TARGETS,
    TARGETS_BY_KEY,
    Viewpoint,
    availability,
    catalogue_for,
    detectors_for,
)
from mithra_worker.sources import SOURCES, SOURCES_BY_KEY, BulkUse, resolve_gsd


# --- the resolution floor ----------------------------------------------------


def test_a_tree_cannot_be_found_on_sentinel_2():
    """A crown is about one pixel at 10 m. No model clears that."""
    result = availability("tree", 10.0)
    assert not result.available
    assert "sharper" in result.reason


def test_the_refusal_offers_the_question_that_can_be_answered():
    """Someone asking for trees at 10 m usually still wants canopy extent."""
    assert availability("tree", 10.0).alternative == "forest_cover"
    assert availability("building", 10.0).alternative == "built_up"


def test_every_alternative_is_genuinely_coarser():
    """Falling back to something equally demanding helps nobody."""
    for target in TARGETS:
        if not target.coarser_alternative:
            continue
        alternative = TARGETS_BY_KEY[target.coarser_alternative]
        assert alternative.min_gsd_m >= target.min_gsd_m, (
            f"{target.key} falls back to {alternative.key}, which needs sharper imagery"
        )


def test_following_the_alternatives_reaches_something_answerable():
    """Alternatives chain — a residential building falls back to a building,
    which falls back to built-up area. The chain has to end somewhere that
    coarse imagery can actually answer, or the refusal is a maze."""
    for target in TARGETS:
        seen = set()
        current = target
        while current.coarser_alternative:
            assert current.key not in seen, f"{target.key} loops through alternatives"
            seen.add(current.key)
            current = TARGETS_BY_KEY[current.coarser_alternative]

        # The end of the chain is either answerable on the coarsest free
        # imagery, or the target was never coarse enough to promise that.
        if target.min_gsd_m >= 10.0 or seen:
            assert availability(current.key, 10.0).available or current.min_gsd_m < 10.0, (
                f"{target.key} ends at {current.key}, which nothing coarse can answer"
            )


def test_water_is_detectable_on_sentinel_2():
    assert availability("water", 10.0).available


def test_a_car_needs_very_sharp_imagery():
    assert not availability("car", 1.0).available
    assert availability("car", 0.3).available


def test_exactly_the_declared_resolution_is_enough():
    """The floor is inclusive; 1.0 m imagery satisfies a 1.0 m requirement."""
    assert availability("tree", 1.0).available


# --- the viewpoint gate ------------------------------------------------------


def test_a_sign_face_is_invisible_from_above_at_any_resolution():
    """Resolution is not the only constraint, and this is the proof."""
    assert not availability("sign", 0.01, Viewpoint.OVERHEAD.value).available
    assert availability("sign", 0.05, Viewpoint.STREET.value).available


def test_land_cover_cannot_be_read_from_the_street():
    """Street panoramas are centimetre-sharp and still cannot see a lake."""
    for target in ("water", "cropland", "forest_cover", "built_up"):
        result = availability(target, 0.05, Viewpoint.STREET.value)
        assert not result.available, f"{target} should not be visible from the street"
        assert "not visible from" in result.reason


def test_some_targets_are_visible_from_both():
    for target in ("tree", "building", "car"):
        assert availability(target, 0.3, Viewpoint.STREET.value).available
        assert availability(target, 0.3, Viewpoint.OVERHEAD.value).available


# --- unknowns fail closed ----------------------------------------------------


def test_imagery_that_cannot_report_its_resolution_promises_nothing():
    """A source with no declared GSD is unknown, not permitted."""
    result = availability("tree", None)
    assert not result.available
    assert "does not report its resolution" in result.reason


def test_an_unknown_target_is_refused():
    assert not availability("dragon", 0.1).available


# --- the registries agree with each other ------------------------------------


def test_every_detector_names_targets_that_exist():
    for detector in DETECTORS_BY_KEY.values():
        for target in detector.targets:
            assert target in TARGETS_BY_KEY, f"{detector.key} claims unknown target {target}"


def test_every_target_has_at_least_one_detector():
    """A target nobody can find should not be offered to a user."""
    for target in TARGETS:
        assert detectors_for(target.key), f"{target.key} has no detector"


def test_the_street_source_offers_signs_and_the_satellite_sources_do_not():
    street = {a.target for a in catalogue_for(0.05, Viewpoint.STREET.value) if a.available}
    overhead = {a.target for a in catalogue_for(0.3, Viewpoint.OVERHEAD.value) if a.available}
    assert "sign" in street
    assert "sign" not in overhead
    assert "water" in {a.target for a in catalogue_for(10.0) if a.available}


# --- imagery sources ---------------------------------------------------------


def test_every_source_declares_a_licence_and_a_bulk_use_position():
    for source in SOURCES:
        assert source.licence
        assert isinstance(source.bulk_use, BulkUse)


def test_consumer_tile_services_are_not_declared_as_free_for_bulk_inference():
    """Running a model over someone's basemap usually breaks their terms."""
    assert SOURCES_BY_KEY["xyz"].bulk_use is BulkUse.CHECK_YOUR_LICENCE


def test_sentinel_2_is_free_to_use_in_bulk():
    assert SOURCES_BY_KEY["sentinel2"].bulk_use is BulkUse.ALLOWED


def test_a_declared_resolution_wins_over_a_claimed_one():
    """A Sentinel-2 scene is 10 m however the request describes it."""
    assert resolve_gsd("sentinel2", 0.1) == 10.0


def test_a_file_reports_its_own_resolution():
    assert resolve_gsd("upload", 0.08) == pytest.approx(0.08)
    assert resolve_gsd("upload", None) is None


def test_an_unknown_source_has_no_resolution():
    assert resolve_gsd("nope", 0.5) is None


# --- the endpoint the console gates itself on --------------------------------


from tests.test_api_runs import client  # noqa: E402, F401 - reuse the app fixture


def test_the_catalogue_requires_a_session(client):  # noqa: F811
    client.post("/api/auth/logout")
    assert client.get("/api/catalog").status_code == 401


def test_the_catalogue_lists_sources_targets_and_detectors(client):  # noqa: F811
    body = client.get("/api/catalog").json()
    assert {s["key"] for s in body["sources"]} >= {"sentinel2", "xyz", "upload", "mapillary"}
    assert {t["key"] for t in body["targets"]} >= {"tree", "water", "car", "sign"}
    assert {d["key"] for d in body["detectors"]} >= {"sam3", "deepforest"}


def test_availability_refuses_trees_on_sentinel_2_with_a_reason(client):  # noqa: F811
    body = client.get("/api/catalog/availability?source=sentinel2").json()
    tree = next(t for t in body["targets"] if t["key"] == "tree")
    assert tree["available"] is False
    assert "sharper" in tree["reason"]
    assert tree["alternative"] == "forest_cover"

    water = next(t for t in body["targets"] if t["key"] == "water")
    assert water["available"] is True


def test_availability_refuses_land_cover_on_street_imagery(client):  # noqa: F811
    body = client.get("/api/catalog/availability?source=mapillary").json()
    assert body["viewpoint"] == "street"
    water = next(t for t in body["targets"] if t["key"] == "water")
    assert water["available"] is False
    feature = next(t for t in body["targets"] if t["key"] == "sign")
    assert feature["available"] is True


def test_an_upload_reports_what_it_can_do_once_it_knows_its_resolution(client):  # noqa: F811
    """Before the file is read, an upload promises nothing."""
    blind = client.get("/api/catalog/availability?source=upload").json()
    assert all(t["available"] is False for t in blind["targets"])

    known = client.get("/api/catalog/availability?source=upload&gsd_m=0.08").json()
    assert known["gsd_m"] == 0.08
    assert next(t for t in known["targets"] if t["key"] == "car")["available"] is True


def test_a_declared_source_ignores_a_claimed_resolution(client):  # noqa: F811
    """Asking for Sentinel-2 'at 10 cm' does not make trees detectable."""
    body = client.get("/api/catalog/availability?source=sentinel2&gsd_m=0.1").json()
    assert body["gsd_m"] == 10.0
    assert next(t for t in body["targets"] if t["key"] == "tree")["available"] is False


def test_an_unknown_source_is_refused(client):  # noqa: F811
    assert client.get("/api/catalog/availability?source=nope").status_code == 404


def test_the_licence_position_travels_with_the_answer(client):  # noqa: F811
    """An operator must see the bulk-use position before starting a run."""
    body = client.get("/api/catalog/availability?source=xyz").json()
    assert body["bulk_use"] == "check_your_licence"
