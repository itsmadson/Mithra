"""What this machine can run.

The point of these tests is the refusal. A detector that needs a GPU on a
machine without one must fail before the run starts, with a sentence an
operator can act on — not after loading eight gigabytes of weights.
"""

import pytest

from mithra_ml.catalog import DETECTORS, DETECTORS_BY_KEY, Runtime
from mithra_ml.hardware import (
    Machine,
    best_detector_for,
    capability,
    fitness,
    measure,
)

LAPTOP = Machine(cpu_count=4, ram_gb=8.0, has_gpu=False)
WORKSTATION = Machine(cpu_count=16, ram_gb=64.0, has_gpu=True, gpu_name="RTX 4090", vram_gb=24.0)
SMALL_GPU = Machine(cpu_count=8, ram_gb=16.0, has_gpu=True, gpu_name="T4", vram_gb=4.0)


def test_the_machine_is_measured_not_configured():
    machine = measure()
    assert machine.cpu_count >= 1
    assert machine.tier in {"gpu", "small_gpu", "strong_cpu", "modest"}


def test_a_gpu_detector_is_refused_on_a_machine_without_one():
    verdict = fitness(DETECTORS_BY_KEY["sam3"], LAPTOP)
    assert not verdict.runnable
    assert "GPU" in verdict.reason or "memory" in verdict.reason


def test_the_same_detector_runs_on_a_workstation():
    assert fitness(DETECTORS_BY_KEY["sam3"], WORKSTATION).runnable


def test_a_gpu_too_small_is_refused_with_the_numbers():
    """Having a GPU is not the same as having enough of one."""
    verdict = fitness(DETECTORS_BY_KEY["sam3"], SMALL_GPU)
    assert not verdict.runnable
    assert "VRAM" in verdict.reason
    assert "T4" in verdict.reason


def test_a_cpu_detector_runs_anywhere():
    assert fitness(DETECTORS_BY_KEY["ndwi-water"], LAPTOP).runnable
    assert fitness(DETECTORS_BY_KEY["ndwi-water"], WORKSTATION).runnable


def test_a_slow_detector_says_it_is_slow_rather_than_hiding_it():
    """An operator told "minutes per tile" can decide for themselves."""
    verdict = fitness(DETECTORS_BY_KEY["clip-zeroshot"], LAPTOP)
    assert verdict.runnable
    assert verdict.speed == "slow"
    assert fitness(DETECTORS_BY_KEY["clip-zeroshot"], WORKSTATION).speed == "fast"


def test_an_unbuilt_detector_is_refused_everywhere():
    verdict = fitness(DETECTORS_BY_KEY["tree-sam"], WORKSTATION)
    assert not verdict.runnable
    assert "not built into this release" in verdict.reason


# --- choosing the best model per target --------------------------------------


def test_the_best_runnable_detector_is_chosen_by_published_accuracy():
    key, evidence = best_detector_for("water", WORKSTATION)
    assert key is not None
    assert "%" in evidence  # the number that justified the choice


def test_a_laptop_falls_back_to_what_it_can_run():
    """Water is answerable on any machine; the index needs no GPU."""
    key, _ = best_detector_for("water", LAPTOP)
    assert key == "ndwi-water"


def test_a_target_with_no_runnable_detector_says_why():
    key, reason = best_detector_for("tree", LAPTOP)
    assert key is None
    assert reason


def test_an_unknown_target_is_refused():
    key, reason = best_detector_for("dragon", WORKSTATION)
    assert key is None
    assert "no detector" in reason


# --- the registry itself -----------------------------------------------------


def test_every_gpu_detector_declares_how_much_vram_it_needs():
    """"Needs a GPU" is not actionable; "needs 8 GB" is."""
    for detector in DETECTORS:
        if detector.runtime is Runtime.GPU:
            assert detector.vram_gb > 0, f"{detector.key} does not say how much VRAM"


def test_every_accuracy_claim_names_the_benchmark_that_produced_it():
    """An accuracy without its dataset is marketing."""
    for detector in DETECTORS:
        for benchmark in detector.benchmarks:
            assert benchmark.dataset, f"{detector.key} claims {benchmark.metric} with no dataset"
            assert 0.0 <= benchmark.value <= 1.0


def test_the_capability_report_covers_every_detector():
    body = capability(LAPTOP)
    assert body["machine"]["tier"] == "modest"
    assert len(body["detectors"]) == len(DETECTORS)
    assert all("runnable" in d for d in body["detectors"])
