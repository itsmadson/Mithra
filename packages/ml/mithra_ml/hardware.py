"""What this machine can actually run.

The same product is deployed on a laptop and on a GPU server, and the
difference is not "slower". A detector that needs 8 GB of VRAM on a machine
with none does not take longer — it fails, an hour in, after the operator has
already gone home.

So the machine is measured once and the answer travels with the catalogue: the
console can then say "this server can do water and land cover today; trees and
vehicles need a GPU" before anybody starts a run.
"""

from __future__ import annotations

import functools
import os
import shutil
from dataclasses import dataclass, field

from mithra_ml.catalog import DETECTORS, Detector, Runtime


@dataclass(frozen=True)
class Machine:
    """The hardware, as measured rather than as configured."""

    cpu_count: int
    ram_gb: float
    has_gpu: bool
    gpu_name: str = ""
    vram_gb: float = 0.0
    disk_free_gb: float = 0.0

    @property
    def tier(self) -> str:
        """A word an operator can act on.

        Deliberately coarse. The useful question is not "how many teraflops" —
        it is "can I run the good models, or should I move this job".
        """
        if self.has_gpu and self.vram_gb >= 8:
            return "gpu"
        if self.has_gpu:
            return "small_gpu"
        if self.cpu_count >= 8 and self.ram_gb >= 16:
            return "strong_cpu"
        return "modest"


@functools.cache
def measure() -> Machine:
    """Read the machine once. Cached: hardware does not change mid-process."""
    cpu_count = os.cpu_count() or 1

    ram_gb = 0.0
    try:
        ram_gb = round(
            os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1
        )
    except (ValueError, OSError, AttributeError):  # pragma: no cover - non-POSIX
        pass

    has_gpu, gpu_name, vram_gb = _probe_gpu()

    disk_free_gb = 0.0
    try:
        disk_free_gb = round(shutil.disk_usage(".").free / 1024**3, 1)
    except OSError:  # pragma: no cover
        pass

    return Machine(
        cpu_count=cpu_count,
        ram_gb=ram_gb,
        has_gpu=has_gpu,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        disk_free_gb=disk_free_gb,
    )


def _probe_gpu() -> tuple[bool, str, float]:
    """Ask torch, and treat any failure as "no GPU".

    Importing torch is expensive and it may not be installed at all — the API
    container does not need it. A machine that cannot answer is treated as
    having no GPU, which is the safe direction: it under-promises rather than
    starting a run that cannot finish.
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return False, "", 0.0
        index = torch.cuda.current_device()
        properties = torch.cuda.get_device_properties(index)
        return True, properties.name, round(properties.total_memory / 1024**3, 1)
    except Exception:  # noqa: BLE001 - any failure means "assume none"
        return False, "", 0.0


@dataclass
class DetectorFitness:
    """Whether one detector can run here, and what it would cost."""

    detector: str
    runnable: bool
    reason: str = ""
    speed: str = "fast"
    requires: str = ""


def fitness(detector: Detector, machine: Machine | None = None) -> DetectorFitness:
    """Can this machine run this detector, and how well.

    Three answers rather than two: yes, yes-but-slowly, and no. The middle one
    matters most — a CPU-only server can run DeepForest, and an operator who is
    told "about a minute per tile" can decide for themselves whether to wait.
    """
    machine = machine or measure()

    if not detector.implemented:
        return DetectorFitness(
            detector.key,
            runnable=False,
            reason="declared in the catalogue but not built into this release",
            requires=detector.runtime.value,
        )

    if detector.ram_gb > machine.ram_gb > 0:
        return DetectorFitness(
            detector.key,
            runnable=False,
            reason=f"needs about {detector.ram_gb:g} GB of memory; this machine has {machine.ram_gb:g} GB",
            requires=detector.runtime.value,
        )

    if detector.runtime is Runtime.GPU:
        if not machine.has_gpu:
            return DetectorFitness(
                detector.key,
                runnable=False,
                reason=f"needs a GPU with about {detector.vram_gb:g} GB of VRAM; this machine has none",
                requires="gpu",
            )
        if detector.vram_gb > machine.vram_gb:
            return DetectorFitness(
                detector.key,
                runnable=False,
                reason=(
                    f"needs about {detector.vram_gb:g} GB of VRAM; "
                    f"{machine.gpu_name or 'this GPU'} has {machine.vram_gb:g} GB"
                ),
                requires="gpu",
            )
        return DetectorFitness(detector.key, runnable=True, speed="fast")

    if detector.runtime is Runtime.CPU_SLOW:
        # Honest about the middle case rather than hiding it behind "supported".
        speed = "fast" if machine.has_gpu or machine.cpu_count >= 8 else "slow"
        return DetectorFitness(
            detector.key,
            runnable=True,
            speed=speed,
            reason="" if speed == "fast" else "minutes per tile on this machine",
        )

    return DetectorFitness(detector.key, runnable=True, speed="fast")


def best_detector_for(target: str, machine: Machine | None = None) -> tuple[str | None, str]:
    """The most accurate detector for a target that this machine can run.

    Ranked by published accuracy on a named benchmark, not by preference: the
    registry carries the numbers, and where two detectors answer the same
    target the better-scoring one wins if the hardware allows it.
    """
    machine = machine or measure()
    candidates = [d for d in DETECTORS if target in d.targets]
    runnable = [d for d in candidates if fitness(d, machine).runnable]

    if not runnable:
        if not candidates:
            return None, "no detector in this build finds that"
        blocked = fitness(candidates[0], machine)
        return None, blocked.reason

    def score(d: Detector) -> tuple[int, float]:
        best = d.best_benchmark()
        # A purpose-trained detector outranks an open-vocabulary one for its
        # own target: the generalist's score was measured on another class.
        return (0 if d.open_vocabulary else 1, best.value if best else 0.0)

    winner = max(runnable, key=score)
    best = winner.best_benchmark()

    if best is None:
        evidence = "no published benchmark"
    elif winner.open_vocabulary:
        # Quoting a generalist's score as evidence for this target would be a
        # borrowed number. Say whose task it was measured on, and name the
        # specialist that would do better if it were available.
        specialists = [
            d for d in candidates if not d.open_vocabulary and d.best_benchmark()
        ]
        better = max(specialists, key=lambda d: d.best_benchmark().value, default=None)
        evidence = f"general-purpose model; its {best.metric} {best.value:.0%} was measured on {best.dataset}"
        if better is not None:
            b = better.best_benchmark()
            evidence += f" — {better.label} scores {b.metric} {b.value:.0%} on this task but is not built into this release"
    else:
        evidence = f"{best.metric} {best.value:.0%} on {best.dataset}"

    return winner.key, evidence


def capability(machine: Machine | None = None) -> dict:
    """The whole picture, for the console to render."""
    machine = machine or measure()
    return {
        "machine": {
            "tier": machine.tier,
            "cpu_count": machine.cpu_count,
            "ram_gb": machine.ram_gb,
            "has_gpu": machine.has_gpu,
            "gpu_name": machine.gpu_name,
            "vram_gb": machine.vram_gb,
            "disk_free_gb": machine.disk_free_gb,
        },
        "detectors": [
            {
                "key": d.key,
                "label": d.label,
                "targets": sorted(d.targets),
                "implemented": d.implemented,
                "runtime": d.runtime.value,
                "vram_gb": d.vram_gb,
                "open_vocabulary": d.open_vocabulary,
                "benchmark": (
                    {
                        "metric": d.best_benchmark().metric,
                        "value": d.best_benchmark().value,
                        "dataset": d.best_benchmark().dataset,
                        "source": d.best_benchmark().source,
                    }
                    if d.best_benchmark()
                    else None
                ),
                **{
                    k: v
                    for k, v in (
                        ("runnable", fitness(d, machine).runnable),
                        ("reason", fitness(d, machine).reason),
                        ("speed", fitness(d, machine).speed),
                    )
                },
                "notes": d.notes,
            }
            for d in DETECTORS
        ],
    }


def detection_plan(target_key: str, machine: Machine | None = None) -> dict:
    """How this target would actually be detected: source, model, evidence.

    The question a user asks when they pick "pothole" is not "is it supported"
    — it is "from what imagery, by which model, and how well". Answering it
    before the run is the difference between a tool and a slot machine.
    """
    from mithra_ml.catalog import TARGETS_BY_KEY, availability

    machine = machine or measure()
    target = TARGETS_BY_KEY.get(target_key)
    if target is None:
        return {"target": target_key, "known": False}

    # Imported here: the worker owns the source registry, and the catalogue
    # must not depend on it the other way round.
    try:
        from mithra_worker.sources import SOURCES
    except ImportError:  # pragma: no cover - ml package used standalone
        SOURCES = ()

    sources = []
    for source in SOURCES:
        verdict = availability(target_key, source.gsd_m, source.viewpoint)
        sources.append(
            {
                "key": source.key,
                "label_en": source.label_en,
                "label_fa": source.label_fa,
                "gsd_m": source.gsd_m,
                "viewpoint": source.viewpoint,
                "licence": source.licence,
                "bulk_use": source.bulk_use.value,
                "usable": verdict.available,
                "reason": verdict.reason,
            }
        )

    models = []
    for detector in DETECTORS:
        if target_key not in detector.targets:
            continue
        verdict = fitness(detector, machine)
        best = detector.best_benchmark()
        models.append(
            {
                "key": detector.key,
                "label": detector.label,
                "runtime": detector.runtime.value,
                "vram_gb": detector.vram_gb,
                "implemented": detector.implemented,
                "runnable_here": verdict.runnable,
                "reason": verdict.reason,
                "speed": verdict.speed,
                "open_vocabulary": detector.open_vocabulary,
                "benchmark": (
                    {
                        "metric": best.metric,
                        "value": best.value,
                        "dataset": best.dataset,
                        "source": best.source,
                        # An open-vocabulary model's published score was earned
                        # on some other class. SAM's building IoU says nothing
                        # about cracks in asphalt, and presenting it beside a
                        # crack benchmark would be a comparison of two
                        # different questions.
                        "measures_this_target": not detector.open_vocabulary,
                    }
                    if best
                    else None
                ),
                "notes": detector.notes,
            }
        )

    # Best first: what it scored, then whether it can run here. A model that
    # wins on paper but not on this machine still belongs in the list, marked.
    # Specialists before generalists, then by score. A model trained for this
    # target beats one that merely can attempt it, even when the generalist
    # publishes a bigger number — because that number was earned elsewhere.
    models.sort(
        key=lambda m: (
            m["runnable_here"],
            not m["open_vocabulary"],
            m["benchmark"]["value"] if m["benchmark"] else 0.0,
        ),
        reverse=True,
    )
    chosen, evidence = best_detector_for(target_key, machine)

    return {
        "target": target_key,
        "known": True,
        "label_en": target.label_en,
        "label_fa": target.label_fa,
        "domain": target.domain.value if target.domain else None,
        "geometry": target.geometry.value,
        "min_gsd_m": target.min_gsd_m,
        "viewpoints": sorted(target.viewpoints),
        "coarser_alternative": target.coarser_alternative,
        "notes_en": target.notes_en,
        "sources": sources,
        "models": models,
        "recommended": {"detector": chosen, "evidence": evidence},
    }
