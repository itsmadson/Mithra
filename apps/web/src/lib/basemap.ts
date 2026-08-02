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

/** A tile source the map can draw. The built-in one is always available. */
export interface BasemapChoice {
  id: string;
  name: string;
  url_template: string;
  attribution: string;
  /** Whether to recolour tiles to match the theme. */
  tint: boolean;
}

export const BUILT_IN_ID = "osm";

/** The fallback, and what a fresh organisation sees. */
export function builtInBasemap(name: string): BasemapChoice {
  return {
    id: BUILT_IN_ID,
    name,
    url_template: OSM_TILES,
    attribution: OSM_ATTRIBUTION,
    tint: true,
  };
}

/** Remembered per browser: an operator's choice of backdrop is their own. */
const STORAGE_KEY = "mithra-basemap";

export function storedBasemapId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeBasemapId(id: string) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* private mode: the choice lasts for this session only */
  }
}

export function basemapStyle(
  theme: "dark" | "light",
  attribution: string,
  basemap?: BasemapChoice | null,
) {
  const tiles = basemap?.url_template ?? OSM_TILES;
  // An operator's own imagery is credited alongside the sign source; an aerial
  // photo is not recoloured, because desaturating a photograph destroys the
  // thing it was added for.
  const credit = basemap?.attribution
    ? `${basemap.attribution} · ${attribution}`
    : attribution;
  const tint = basemap ? basemap.tint : true;

  return {
    version: 8 as const,
    sources: {
      base: {
        type: "raster" as const,
        tiles: [tiles],
        tileSize: 256,
        attribution: credit,
      },
    },
    layers: [
      {
        id: "base",
        type: "raster" as const,
        source: "base",
        paint: tint ? { ...PAINT[theme] } : {},
      },
    ],
  };
}
