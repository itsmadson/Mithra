"""Rasters an operator brings themselves.

The file decides what can be detected on it, so the interesting tests are the
ones where the file is not what it claims to be.
"""

import io

import pytest

from tests.test_api_runs import client  # noqa: F401 - reuse the app fixture


def geotiff_bytes(width: int = 64, height: int = 64, gsd_deg: float = 0.0001) -> bytes:
    """A small but genuinely georeferenced GeoTIFF."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    buffer = io.BytesIO()
    with rasterio.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff", width=width, height=height, count=3, dtype="uint8",
            crs="EPSG:4326", transform=from_origin(59.60, 36.30, gsd_deg, gsd_deg),
        ) as dataset:
            dataset.write(np.random.randint(0, 255, (3, height, width), dtype="uint8"))
        buffer.write(memfile.read())
    return buffer.getvalue()


def test_a_georeferenced_raster_is_stored_and_measured(client):  # noqa: F811
    response = client.post(
        "/api/uploads",
        files={"file": ("scene.tif", geotiff_bytes(), "image/tiff")},
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["bytes"] > 0
    assert len(body["bounds"]) == 4
    # Resolution comes from the header, so it can gate the catalogue.
    assert body["gsd_m"] and body["gsd_m"] > 0


def test_the_resolution_read_from_the_file_decides_what_it_can_detect(client):  # noqa: F811
    """The point of measuring on arrival: a fine raster unlocks fine targets."""
    fine = client.post(
        "/api/uploads",
        files={"file": ("drone.tif", geotiff_bytes(gsd_deg=0.000002), "image/tiff")},
    ).json()

    availability = client.get(
        f"/api/catalog/availability?source=upload&gsd_m={fine['gsd_m']}"
    ).json()
    by_key = {t["key"]: t for t in availability["targets"]}
    assert by_key["tree"]["available"] is True
    assert by_key["car"]["available"] is True


def test_a_coarse_raster_does_not_unlock_fine_targets(client):  # noqa: F811
    coarse = client.post(
        "/api/uploads",
        files={"file": ("sat.tif", geotiff_bytes(gsd_deg=0.0002), "image/tiff")},
    ).json()

    availability = client.get(
        f"/api/catalog/availability?source=upload&gsd_m={coarse['gsd_m']}"
    ).json()
    by_key = {t["key"]: t for t in availability["targets"]}
    assert by_key["car"]["available"] is False


def test_a_file_that_is_not_a_raster_is_refused(client):  # noqa: F811
    response = client.post(
        "/api/uploads", files={"file": ("notes.tif", b"this is not a raster", "image/tiff")}
    )
    assert response.status_code == 422
    assert "not a readable georeferenced raster" in response.json()["detail"]


def test_an_unsupported_extension_is_refused_before_it_is_read(client):  # noqa: F811
    response = client.post(
        "/api/uploads", files={"file": ("payload.exe", b"MZ", "application/octet-stream")}
    )
    assert response.status_code == 422
    assert "unsupported file type" in response.json()["detail"]


def test_uploading_requires_a_session(client):  # noqa: F811
    client.post("/api/auth/logout")
    response = client.post(
        "/api/uploads", files={"file": ("scene.tif", geotiff_bytes(), "image/tiff")}
    )
    assert response.status_code == 401


def test_uploads_are_namespaced_by_organisation(client):  # noqa: F811
    """Imagery someone paid for must not be readable across the boundary."""
    me = client.get("/api/auth/me").json()
    body = client.post(
        "/api/uploads", files={"file": ("scene.tif", geotiff_bytes(), "image/tiff")}
    ).json()
    assert me["org_id"] in body["path"]


def test_a_rejected_upload_leaves_nothing_behind(client, tmp_path):  # noqa: F811
    """A refused file must not sit on disk consuming space forever."""
    from mithra_api.routes.uploads import upload_dir

    before = set(p for p in upload_dir().rglob("*") if p.is_file())
    client.post("/api/uploads", files={"file": ("bad.tif", b"nope", "image/tiff")})
    after = set(p for p in upload_dir().rglob("*") if p.is_file())
    assert after == before
