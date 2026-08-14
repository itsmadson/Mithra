import type { FeatureClass } from "./api";

/**
 * One source of truth for how each class is coloured, everywhere it appears:
 * map pin, legend swatch, list rail, detail header. A class that is amber on
 * the map and orange in the table is two classes as far as the eye is
 * concerned.
 */
export const CLASS_COLOR: Record<FeatureClass, string> = {
  direction_guide: "var(--c-direction)",
  street_name: "var(--c-street)",
  city_entry: "var(--c-city)",
  informational: "var(--c-info)",
  unknown: "var(--c-unknown)",
};

/** Literal hex per class, for MapLibre paint expressions, which cannot read CSS vars. */
export const CLASS_HEX: Record<FeatureClass, { dark: string; light: string }> = {
  direction_guide: { dark: "#3690e3", light: "#0074ca" },
  street_name: { dark: "#c97500", light: "#ae5700" },
  city_entry: { dark: "#00a875", light: "#008d59" },
  informational: { dark: "#be67b7", light: "#a3489d" },
  // "unknown" is the reserved no-class slot, so it stays neutral by design and
  // is always direct-labelled rather than identified by colour alone.
  unknown: { dark: "#7b8b9c", light: "#61728a" },
};

/** The order classes are drawn in, everywhere. Colour follows the class, never its rank. */
export const CLASS_ORDER: FeatureClass[] = [
  "direction_guide",
  "street_name",
  "city_entry",
  "informational",
  "unknown",
];

/**
 * Mapillary's own category, derived from object_value ("regulatory--stop--g1").
 * Shown in the detail panel because it is independent evidence about the sign:
 * where it disagrees with our class, the operator can see that at a glance.
 */
export function mapillaryCategory(value: string | null | undefined): string | null {
  if (!value) return null;
  return value.split("--")[0] || null;
}

/** Human-readable sign name from a Mapillary object_value. */
export function mapillaryName(value: string | null | undefined): string | null {
  if (!value) return null;
  const parts = value.split("--");
  if (parts.length < 2) return value;
  return parts[1].replace(/-/g, " ");
}

/** The public Mapillary viewer for one image — lets an operator check the source. */
export function mapillaryImageUrl(imageId: string | null | undefined): string | null {
  return imageId ? `https://www.mapillary.com/app/?pKey=${imageId}&focus=photo` : null;
}

/**
 * A colour for any class, including ones the sign palette never named.
 *
 * The catalogue grows with every detector, so the palette cannot enumerate
 * every class ahead of time. Known classes keep their validated hue; anything
 * else gets a stable colour derived from its name, so the same class is the
 * same colour on every screen and between sessions.
 */
const EXTRA_HUES = [
  "var(--ai)",
  "var(--c-city)",
  "var(--c-direction)",
  "var(--c-info)",
  "var(--secondary)",
];

export function colorForClass(cls: string): string {
  if (cls in CLASS_COLOR) return CLASS_COLOR[cls as FeatureClass];
  let hash = 0;
  for (let i = 0; i < cls.length; i += 1) hash = (hash * 31 + cls.charCodeAt(i)) >>> 0;
  return EXTRA_HUES[hash % EXTRA_HUES.length];
}
