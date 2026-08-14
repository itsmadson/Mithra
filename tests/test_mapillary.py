import json
import os
from pathlib import Path

import httpx
import pytest
import respx

from mithra_worker.mapillary import (
    GRAPH,
    MapillaryAuthError,
    MapillaryClient,
    MapillaryRateLimited,
)

BBOX = (59.600, 36.293, 59.605, 36.298)


@pytest.fixture
def client():
    return MapillaryClient(token="MLY|test|secret", max_retries=3, backoff_base=0.0)


@respx.mock
def test_sends_oauth_header_not_bearer(client):
    route = respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    client.get_sign_features(BBOX)
    assert route.calls[0].request.headers["authorization"] == "OAuth MLY|test|secret"


@respx.mock
def test_requests_only_the_traffic_sign_layer(client):
    route = respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    client.get_sign_features(BBOX)
    assert route.calls[0].request.url.params["object_types"] == "trafficsign"


@respx.mock
def test_non_sign_features_are_filtered_out(client):
    """Mapillary ignores the object_types query parameter.

    Verified against the live API: passing 'trafficsign', 'traffic_sign',
    'points', or nothing at all returns byte-identical results. In one central
    Mashhad tile that is 454 features of which only 58 are actually features — the
    rest are panoptic and mvd_fast detections of street furniture. Filtering has
    to happen here, or a survey reports an eightfold overcount.
    """
    respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "feature",
                        "object_value": "regulatory--stop--g1",
                        "object_type": "trafficsign",
                        "geometry": {"type": "Point", "coordinates": [59.601, 36.294]},
                    },
                    {
                        "id": "streetlight",
                        "object_value": "object--street-light",
                        "object_type": "panoptic",
                        "geometry": {"type": "Point", "coordinates": [59.602, 36.295]},
                    },
                    {
                        "id": "bench",
                        "object_value": "object--bench",
                        "object_type": "mvd_fast",
                        "geometry": {"type": "Point", "coordinates": [59.603, 36.296]},
                    },
                ]
            },
        )
    )
    features = client.get_sign_features(BBOX)
    assert [f["id"] for f in features] == ["feature"]


@respx.mock
def test_features_without_an_object_type_are_dropped(client):
    respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"id": "mystery", "object_value": "regulatory--stop--g1"}]},
        )
    )
    assert client.get_sign_features(BBOX) == []


@respx.mock
def test_returns_feature_dicts(client):
    respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "1",
                        "object_value": "information--parking--g1",
                        "object_type": "trafficsign",
                        "geometry": {"type": "Point", "coordinates": [59.601, 36.294]},
                        "images": {"data": [{"id": "img1"}]},
                    },
                ]
            },
        )
    )
    features = client.get_sign_features(BBOX)
    assert features[0]["id"] == "1"
    assert features[0]["geometry"]["coordinates"] == [59.601, 36.294]


@respx.mock
def test_auth_failure_raises_immediately_without_retry(client):
    route = respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(401, json={"error": "bad token"})
    )
    with pytest.raises(MapillaryAuthError):
        client.get_sign_features(BBOX)
    assert route.call_count == 1


@respx.mock
def test_rate_limit_is_retried_then_succeeds(client):
    route = respx.get(f"{GRAPH}/map_features").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json={"data": []}),
        ]
    )
    assert client.get_sign_features(BBOX) == []
    assert route.call_count == 3


@respx.mock
def test_rate_limit_beyond_retries_raises(client):
    respx.get(f"{GRAPH}/map_features").mock(return_value=httpx.Response(429))
    with pytest.raises(MapillaryRateLimited):
        client.get_sign_features(BBOX)


@respx.mock
def test_server_error_is_retried(client):
    route = respx.get(f"{GRAPH}/map_features").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"data": []}),
        ]
    )
    client.get_sign_features(BBOX)
    assert route.call_count == 2


@respx.mock
def test_get_detections_hits_the_image_scoped_endpoint(client):
    route = respx.get(f"{GRAPH}/img1/detections").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "d1",
                        "geometry": "GmYKBHRlc3Q=",
                        "value": "information--parking--g1",
                    },
                ]
            },
        )
    )
    detections = client.get_detections("img1")
    assert detections[0]["geometry"] == "GmYKBHRlc3Q="
    assert route.called


@respx.mock
def test_get_image_meta_requests_dimensions_and_thumb(client):
    route = respx.get(f"{GRAPH}/img1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "img1",
                "width": 4096,
                "height": 3072,
                "thumb_2048_url": "https://cdn.example/img1.jpg",
            },
        )
    )
    meta = client.get_image_meta("img1")
    assert meta["width"] == 4096
    fields = route.calls[0].request.url.params["fields"]
    assert "thumb_2048_url" in fields and "width" in fields and "height" in fields


@respx.mock
def test_token_is_not_included_in_exception_messages(client):
    respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(401, json={"error": "bad token"})
    )
    with pytest.raises(MapillaryAuthError) as exc:
        client.get_sign_features(BBOX)
    assert "secret" not in str(exc.value)


CASSETTE = Path(__file__).parent / "fixtures" / "mashhad_features.json"


@pytest.mark.skipif(
    os.environ.get("RECORD_CASSETTES") != "1",
    reason="recording tool: set RECORD_CASSETTES=1 with a real token to refresh the fixture",
)
def test_record_live_mashhad_cassette():
    """Not a test — a recording tool that happens to assert.

    It calls the live API and rewrites a fixture, so it runs only when asked.
    Guarding on the token merely being *set* was not enough: any environment
    with a placeholder token, CI included, ran it and failed against a service
    it could never reach.
    """
    live = MapillaryClient(token=os.environ["MAPILLARY_TOKEN"])
    features = live.get_sign_features(BBOX)
    CASSETTE.parent.mkdir(parents=True, exist_ok=True)
    CASSETTE.write_text(json.dumps(features[:50], indent=2))
    for feature in features:
        assert feature["object_type"] == "trafficsign"
        assert feature["geometry"]["type"] == "Point"
