"""What this server can do.

The console asks before it offers anything, because the honest answer differs
between deployments: the same build on a laptop and on a GPU host supports
different targets, and an operator who is not told will start a run that cannot
finish.
"""

from fastapi import APIRouter, Depends

from mithra_api.auth import current_user
from mithra_ml.catalog import TARGETS
from mithra_ml.hardware import best_detector_for, capability

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/capability")
def system_capability(_user=Depends(current_user)) -> dict:
    """The machine, every detector's fitness on it, and the best per target."""
    body = capability()

    recommended = {}
    for target in TARGETS:
        key, evidence = best_detector_for(target.key)
        recommended[target.key] = {
            "detector": key,
            "evidence": evidence,
            "available": key is not None,
        }
    body["recommended"] = recommended
    return body
