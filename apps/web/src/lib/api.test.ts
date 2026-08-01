import { afterEach, describe, expect, it, vi } from "vitest";
import { createBboxJob, createStreetJob, getJob, listSigns, postLabel } from "./api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(body: unknown, ok = true, status = 200) {
  const spy = vi.fn().mockResolvedValue({ ok, status, json: async () => body });
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("api client", () => {
  it("posts the bbox as an array", async () => {
    const spy = mockFetch({ id: "abc", status: "queued" });
    await createBboxJob([59.6, 36.29, 59.64, 36.33]);
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.bbox).toEqual([59.6, 36.29, 59.64, 36.33]);
  });

  it("returns the created job id", async () => {
    mockFetch({ id: "abc", status: "queued" });
    expect((await createBboxJob([59.6, 36.29, 59.64, 36.33])).id).toBe("abc");
  });

  it("reads job counts", async () => {
    mockFetch({
      id: "abc",
      status: "succeeded",
      counts: { street_name: 3 },
      total: 3,
      failed_count: 0,
    });
    expect((await getJob("abc")).counts.street_name).toBe(3);
  });

  it("passes the class filter as a query param", async () => {
    const spy = mockFetch({ items: [] });
    await listSigns("abc", { signClass: "city_entry" });
    expect(String(spy.mock.calls[0][0])).toContain("sign_class=city_entry");
  });

  it("throws on a non-ok response", async () => {
    mockFetch({ detail: "job not found" }, false, 404);
    await expect(getJob("missing")).rejects.toThrow();
  });

  it("posts a street survey with the OSM way and an anchor point", async () => {
    const spy = mockFetch({ id: "abc", status: "queued" });
    await createStreetJob(
      {
        osm_id: 25576226,
        osm_type: "way",
        display_name: "خیابان سعدی، مشهد",
        name: "خیابان سعدی",
        name_fa: "خیابان سعدی",
        name_en: "Saadi St",
        category: "highway",
        type: "residential",
        lat: 36.2945,
        lon: 59.6014,
      },
      30,
    );
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.osm_id).toBe(25576226);
    expect(body.street_name).toBe("خیابان سعدی");
    expect(body.buffer_m).toBe(30);
    // The anchor is what the worker searches around for the rest of the street.
    expect(body.lat).toBeCloseTo(36.2945);
    expect(body.lon).toBeCloseTo(59.6014);
  });

  it("posts labels with snake_case keys the API expects", async () => {
    const spy = mockFetch({ status: "ok" });
    await postLabel("sign-1", "city_entry");
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body).toEqual({ sign_id: "sign-1", sign_class: "city_entry" });
  });
});
