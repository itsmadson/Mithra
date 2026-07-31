/**
 * Basemap configuration shared by both maps.
 *
 * OpenStreetMap raster tiles, recoloured in the raster layer's own paint
 * properties. Carto's ready-made dark basemap would be the obvious pick, but it
 * answers with a 103-byte placeholder from this network while OSM serves real
 * tiles, so the map came up blank. Adjusting OSM here keeps the dark console
 * without depending on a host that is not reachable, and because the adjustment
 * lives on the basemap layer, the sign pins drawn above it keep full saturation.
 *
 * Raster rather than vector is also deliberate: vector labels need MapLibre's
 * RTL text plugin fetched at runtime before Persian street names shape
 * correctly, and a survey tool should not depend on a third script loading
 * before its map is legible.
 */

export const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

export const OSM_ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

export const SIGNS_ATTRIBUTION = `${OSM_ATTRIBUTION} · signs © <a href="https://www.mapillary.com">Mapillary</a>`;

const PAINT = {
  dark: { "raster-saturation": -0.72, "raster-contrast": 0.05 },
  light: { "raster-saturation": -0.32, "raster-contrast": 0.02 },
} as const;

export function basemapStyle(theme: "dark" | "light", attribution: string) {
  return {
    version: 8 as const,
    sources: {
      base: {
        type: "raster" as const,
        tiles: [OSM_TILES],
        tileSize: 256,
        attribution,
      },
    },
    layers: [
      {
        id: "base",
        type: "raster" as const,
        source: "base",
        paint: { ...PAINT[theme] },
      },
    ],
  };
}
