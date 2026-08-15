#!/usr/bin/env python
"""Prove SAM works on this host before anybody trusts a count from it.

Run once on a new GPU server. It reports what the machine is, whether SAM
loads, and what it finds on a real scene — so the first honest number comes
from a deliberate check rather than from a production run.

    python scripts/check_sam.py
"""

import sys

sys.path[:0] = ["services/api", "services/worker", "packages/ml"]


def main() -> int:
    from mithra_ml.hardware import measure

    machine = measure()
    print(f"machine: {machine.tier} — {machine.cpu_count} cpus, {machine.ram_gb} GB RAM")
    print(f"gpu: {machine.gpu_name or 'none'} ({machine.vram_gb} GB VRAM)")
    if not machine.has_gpu:
        print("\nNo GPU. SAM will be refused by the capability check, which is correct:")
        print("it would take hours per tile here. Run this on the GPU host instead.")
        return 1

    from mithra_ml.sam import Sam3Detector, SamUnavailable
    from mithra_worker.imagery import read_xyz, zoom_for_gsd

    print("\nloading SAM…")
    detector = Sam3Detector()
    try:
        detector._load()  # noqa: SLF001 - this script exists to test loading
    except SamUnavailable as exc:
        print(f"FAILED: {exc}")
        return 1
    print("loaded.")

    # A neighbourhood with obvious buildings and trees.
    bbox = (59.600, 36.290, 59.606, 36.296)
    print(f"\nreading imagery for {bbox}…")
    chip = read_xyz(
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png", bbox, zoom=zoom_for_gsd(0.6, 36.3)
    )
    print(f"chip {chip.width}x{chip.height} at {chip.gsd_m:.2f} m/px")

    for target in ("building", "tree"):
        found = detector.detect(chip, [target])
        total = sum(d.area_m2 or 0 for d in found)
        print(f"  {target:<10} {len(found):>4} detections, {total/10000:.2f} ha")

    print("\nIf those numbers look plausible against the imagery, SAM is working here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
