"""How a target would be detected: sources, models, evidence.

The catalogue grew to seventy targets across ten domains. These tests are
about the claims it makes for them — particularly the one that is easy to get
wrong, which is quoting a model's score from a task it was not measured on.
"""

import pytest

from mithra_ml.catalog import DETECTORS, TARGETS, Domain, detectors_for
from mithra_ml.hardware import Machine, best_detector_for, detection_plan

GPU = Machine(cpu_count=16, ram_gb=64.0, has_gpu=True, gpu_name="A100", vram_gb=40.0)
LAPTOP = Machine(cpu_count=4, ram_gb=8.0, has_gpu=False)


# --- the taxonomy ------------------------------------------------------------


def test_the_catalogue_covers_the_domains_a_city_asks_about():
    domains = {t.domain for t in TARGETS}
    for expected in (
        Domain.LAND_COVER, Domain.LAND_USE, Domain.BUILDING,
        Domain.TRANSPORT, Domain.CONDITION, Domain.STREET,
        Domain.ENERGY, Domain.AGRICULTURE,
    ):
        assert expected in domains, f"nothing answers {expected}"


def test_every_target_has_a_detector_that_claims_it():
    """A target nobody can attempt should not be offered."""
    for target in TARGETS:
        assert detectors_for(target.key), f"{target.key} has no detector"


def test_building_types_are_distinguished_not_lumped():
    keys = {t.key for t in TARGETS}
    assert {"building_residential", "building_commercial", "building_industrial"} <= keys
    assert "school" in keys and "hospital" in keys


def test_asphalt_condition_is_answerable_from_the_street():
    """The question the panoramas exist to answer."""
    plan = detection_plan("pavement_distress", GPU)
    assert plan["viewpoints"] == ["street"]
    assert any(s["usable"] for s in plan["sources"])
    assert any("pavement" in m["key"] for m in plan["models"])


def test_road_surface_type_is_street_only():
    """Asphalt versus gravel is not readable from above."""
    plan = detection_plan("road_surface", GPU)
    assert plan["viewpoints"] == ["street"]
    overhead = [s for s in plan["sources"] if s["viewpoint"] == "overhead"]
    assert overhead and not any(s["usable"] for s in overhead)


# --- the plan ----------------------------------------------------------------


def test_a_plan_names_the_imagery_and_the_model():
    plan = detection_plan("water", LAPTOP)
    assert plan["known"]
    assert [s for s in plan["sources"] if s["usable"]]
    assert plan["recommended"]["detector"] == "ndwi-water"
    assert "%" in plan["recommended"]["evidence"]


def test_an_unknown_target_is_reported_not_invented():
    assert detection_plan("unicorn", GPU)["known"] is False


def test_a_plan_says_why_a_source_cannot_be_used():
    plan = detection_plan("car", GPU)
    coarse = next(s for s in plan["sources"] if s["key"] == "sentinel2")
    assert not coarse["usable"]
    assert "sharper" in coarse["reason"]


def test_the_licence_position_travels_with_each_source():
    plan = detection_plan("building", GPU)
    assert all(s["licence"] for s in plan["sources"])
    assert any(s["bulk_use"] == "check_your_licence" for s in plan["sources"])


# --- the integrity of the evidence -------------------------------------------


def test_a_generalists_score_is_marked_as_measured_elsewhere():
    """SAM's building IoU says nothing about cracks in asphalt.

    Presenting it beside a crack benchmark would compare two different
    questions, which is the failure this registry exists to prevent.
    """
    plan = detection_plan("pavement_distress", GPU)
    sam = next(m for m in plan["models"] if m["key"] == "sam3")
    assert sam["benchmark"]["measures_this_target"] is False

    specialist = next(m for m in plan["models"] if m["key"] == "pavement-distress")
    assert specialist["benchmark"]["measures_this_target"] is True


def test_the_recommendation_admits_when_it_is_a_generalist():
    _, evidence = best_detector_for("pavement_distress", GPU)
    assert "general-purpose" in evidence
    assert "not built into this release" in evidence


def test_a_specialist_is_quoted_plainly_when_it_is_the_choice():
    _, evidence = best_detector_for("water", LAPTOP)
    assert "general-purpose" not in evidence


def test_every_benchmark_names_its_dataset():
    for detector in DETECTORS:
        for benchmark in detector.benchmarks:
            assert benchmark.dataset
            assert 0.0 <= benchmark.value <= 1.0
