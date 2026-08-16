"""The inventory query: filters, facets, sorting and export.

These matter more than they look. The inventory is the screen the product is
for, and every bug in here is silent: a filter that drops rows, a total that
disagrees with the list, or a sort that leads with blanks all produce a page
that looks perfectly reasonable and is wrong.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tests.conftest import DB_URL

from mithra_api.db import Base, get_session
from mithra_api.main import app
from mithra_api.models import Feature, Run, RunStatus

PASSWORD = "a-long-enough-password"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    monkeypatch.setattr("mithra_api.routes.runs.enqueue", lambda run_id: None)
    test_client = TestClient(app)
    test_client.engine = engine
    yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def inventory(client):
    """Two runs: a water survey and a land-cover survey, with known values."""
    client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": PASSWORD, "org_name": "City A"},
    )
    user = client.get("/api/auth/me").json()

    rows = []
    with Session(client.engine) as session:
        water_run = Run(
            name="Anzali water",
            org_id=user["org_id"],
            bbox_west=49.4,
            bbox_south=37.4,
            bbox_east=49.6,
            bbox_north=37.5,
            status=RunStatus.SUCCEEDED,
            detector="ndwi-water",
        )
        cover_run = Run(
            name="Mashhad cover",
            org_id=user["org_id"],
            bbox_west=59.5,
            bbox_south=36.2,
            bbox_east=59.7,
            bbox_north=36.4,
            status=RunStatus.SUCCEEDED,
            detector="spectral-landcover",
        )
        session.add_all([water_run, cover_run])
        session.commit()

        # Areas chosen so the ordering is unambiguous, and one point detection
        # with no area at all — the row that breaks a naive sort.
        spec = [
            (water_run, "water", 0.67, 20_000.0, False),
            (water_run, "water", 0.67, 5_000.0, False),
            (cover_run, "forest_cover", 0.79, 90_000.0, False),
            (cover_run, "cropland", 0.65, 12_000.0, False),
            (cover_run, "street_name", 0.20, None, True),
        ]
        for index, (run, class_name, confidence, area, unsure) in enumerate(spec):
            feature = Feature(
                run_id=run.id,
                source_feature_id=f"f{index}",
                geom="SRID=4326;POINT(59.601 36.294)",
                class_name=class_name,
                confidence=confidence,
                area_m2=area,
                needs_review=unsure,
                model_version="test",
            )
            session.add(feature)
            rows.append(feature)
        session.commit()
        return {"water_run": str(water_run.id), "cover_run": str(cover_run.id)}


def items(client, query=""):
    response = client.get(f"/api/features?{query}")
    assert response.status_code == 200, response.text
    return response.json()


# --- filtering ---------------------------------------------------------------


def test_the_total_counts_everything_not_just_the_page(client, inventory):
    body = items(client, "limit=2")
    assert len(body["items"]) == 2
    assert body["total"] == 5


def test_filtering_by_class_narrows_both_the_rows_and_the_total(client, inventory):
    body = items(client, "class_name=water")
    assert body["total"] == 2
    assert {row["class_name"] for row in body["items"]} == {"water"}


def test_several_classes_can_be_asked_for_at_once(client, inventory):
    body = items(client, "class_name=water&class_name=cropland")
    assert body["total"] == 3


def test_filtering_by_run_scopes_to_that_survey(client, inventory):
    body = items(client, f"run_id={inventory['water_run']}")
    assert body["total"] == 2


def test_filtering_by_detector_reaches_through_to_the_run(client, inventory):
    body = items(client, "detector=spectral-landcover")
    assert body["total"] == 3


def test_the_confidence_floor_excludes_what_is_below_it(client, inventory):
    body = items(client, "min_confidence=0.66")
    assert body["total"] == 3  # 0.67, 0.67, 0.79


def test_search_matches_the_run_name_as_well_as_the_class(client, inventory):
    """An operator searching "anzali" is looking for a survey, not a class."""
    assert items(client, "q=anzali")["total"] == 2
    assert items(client, "q=forest")["total"] == 1


def test_search_is_case_insensitive(client, inventory):
    assert items(client, "q=ANZALI")["total"] == 2


def test_needs_review_selects_only_what_a_person_must_judge(client, inventory):
    body = items(client, "needs_review=true")
    assert body["total"] == 1
    assert body["items"][0]["needs_review"] is True


# --- sorting -----------------------------------------------------------------


def test_sorting_by_area_puts_the_largest_first(client, inventory):
    body = items(client, "sort=area_m2&direction=desc")
    areas = [row["area_m2"] for row in body["items"] if row["area_m2"] is not None]
    assert areas == sorted(areas, reverse=True)
    assert body["items"][0]["area_m2"] == 90_000.0


def test_rows_without_an_area_sort_last_not_first(client, inventory):
    """Postgres puts nulls first on a descending sort, so "largest first" opened
    on a page of blanks — which reads as a broken sort rather than missing data."""
    body = items(client, "sort=area_m2&direction=desc")
    assert body["items"][-1]["area_m2"] is None


def test_rows_without_an_area_sort_last_ascending_too(client, inventory):
    body = items(client, "sort=area_m2&direction=asc")
    assert body["items"][0]["area_m2"] == 5_000.0
    assert body["items"][-1]["area_m2"] is None


def test_an_unknown_sort_key_falls_back_rather_than_failing(client, inventory):
    """The sort key comes from a URL. It is whitelisted, so a bad one is simply
    not honoured — an ORDER BY interpolated from a query string is how a filter
    becomes a read of somebody else's data."""
    assert items(client, "sort='; drop table features; --")["total"] == 5


def test_paging_does_not_repeat_or_skip_rows(client, inventory):
    first = items(client, "limit=2&offset=0")["items"]
    second = items(client, "limit=2&offset=2")["items"]
    third = items(client, "limit=2&offset=4")["items"]
    seen = [row["id"] for row in first + second + third]
    assert len(seen) == len(set(seen)) == 5


# --- what the rows carry -----------------------------------------------------


def test_a_row_names_the_run_it_came_from(client, inventory):
    body = items(client, "class_name=water&limit=1")
    assert body["items"][0]["run_name"] == "Anzali water"


def test_a_row_carries_the_catalogue_name_in_both_languages(client, inventory):
    """A Persian operator reading "forest_cover" is reading a database key."""
    body = items(client, "class_name=forest_cover&limit=1")
    row = body["items"][0]
    assert row["label_en"] == "Forest cover"
    assert row["label_fa"] == "پوشش جنگلی"
    assert row["domain"] == "land_cover"


def test_a_class_the_catalogue_never_named_carries_no_label(client, inventory):
    """The original sign classes predate the catalogue; the console names those
    from its own message files, and inventing one here would hide that."""
    body = items(client, "class_name=street_name&limit=1")
    assert body["items"][0]["label_en"] is None


# --- facets ------------------------------------------------------------------


def facets(client, query=""):
    response = client.get(f"/api/features/facets?{query}")
    assert response.status_code == 200, response.text
    return response.json()


def test_facets_count_what_is_present_not_the_catalogue(client, inventory):
    body = facets(client)
    assert {f["key"] for f in body["classes"]} == {
        "water",
        "forest_cover",
        "cropland",
        "street_name",
    }


def test_facet_counts_agree_with_the_list_they_filter(client, inventory):
    """A panel saying "water 24" beside a table of 19 rows is worse than no
    counts at all, so both are built from the same predicate."""
    for facet in facets(client)["classes"]:
        listed = items(client, f"class_name={facet['key']}")["total"]
        assert listed == facet["count"], facet["key"]


def test_class_facets_ignore_the_class_filter_so_a_search_can_be_widened(client, inventory):
    """Hiding every option you have not already chosen makes it impossible to
    add a second class."""
    body = facets(client, "class_name=water")
    assert len(body["classes"]) == 4


def test_facets_respect_every_other_filter(client, inventory):
    body = facets(client, f"run_id={inventory['water_run']}")
    assert {f["key"] for f in body["classes"]} == {"water"}


def test_run_facets_carry_the_name_a_person_recognises(client, inventory):
    names = {f["label"] for f in facets(client)["runs"]}
    assert names == {"Anzali water", "Mashhad cover"}


def test_domain_totals_add_up_to_the_classes_they_group(client, inventory):
    body = facets(client)
    land_cover = next(d for d in body["domains"] if d["key"] == "land_cover")
    assert land_cover["count"] == 1  # forest_cover only; cropland is agriculture


def test_the_unsure_count_is_the_queue_length(client, inventory):
    assert facets(client)["needs_review"] == 1


# --- export ------------------------------------------------------------------


def test_the_export_carries_the_filters_that_were_on_screen(client, inventory):
    """An export that ignores the filters is a different dataset from the one
    the operator was looking at, and they find out in a report."""
    response = client.get("/api/features/export.csv?class_name=water")
    assert response.status_code == 200
    lines = [line for line in response.text.strip().split("\n") if line]
    assert len(lines) == 3  # header plus two water rows
    assert "water" in lines[1]


def test_the_export_names_its_columns(client, inventory):
    header = client.get("/api/features/export.csv").text.split("\n")[0]
    assert "domain" in header and "area_m2" in header and "run" in header


# --- tenancy -----------------------------------------------------------------


def test_another_organisations_detections_are_not_counted(client, inventory):
    """The inventory is the widest read in the product: it crosses every run,
    so it is the one most able to leak across organisations."""
    from mithra_api.models import Organisation, User, UserRole
    from mithra_api.security import hash_password

    with Session(client.engine) as session:
        other_org = Organisation(name="City B")
        session.add(other_org)
        session.flush()
        session.add(
            User(
                email="b@example.com",
                name="B",
                password_hash=hash_password(PASSWORD),
                role=UserRole.ADMIN,
                org_id=other_org.id,
            )
        )
        other_run = Run(
            name="Somebody else's survey",
            org_id=other_org.id,
            bbox_west=0,
            bbox_south=0,
            bbox_east=1,
            bbox_north=1,
            status=RunStatus.SUCCEEDED,
        )
        session.add(other_run)
        session.commit()
        session.add(
            Feature(
                run_id=other_run.id,
                source_feature_id="theirs",
                geom="SRID=4326;POINT(0.5 0.5)",
                class_name="water",
                confidence=0.9,
                area_m2=999_999.0,
                model_version="test",
            )
        )
        session.commit()

    assert items(client)["total"] == 5
    assert facets(client)["total"] == 5
    assert all(row["run_name"] != "Somebody else's survey" for row in items(client)["items"])
    # And the largest area in the export is ours, not theirs.
    assert "999999" not in client.get("/api/features/export.csv").text
