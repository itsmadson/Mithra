import type { SignClass } from "./api";

/**
 * One source of truth for how each class is coloured, everywhere it appears:
 * map pin, legend swatch, list rail, detail header. A class that is amber on
 * the map and orange in the table is two classes as far as the eye is
 * concerned.
 */
export const CLASS_COLOR: Record<SignClass, string> = {
  direction_guide: "var(--c-direction)",
  street_name: "var(--c-street)",
  city_entry: "var(--c-city)",
  informational: "var(--c-info)",
  unknown: "var(--c-unknown)",
};

/** Literal hex per class, for MapLibre paint expressions, which cannot read CSS vars. */
export const CLASS_HEX: Record<SignClass, { dark: string; light: string }> = {
  direction_guide: { dark: "#4da3ff", light: "#0b6bd3" },
  street_name: { dark: "#ffb547", light: "#a35f00" },
  city_entry: { dark: "#5fd39a", light: "#0d6d49" },
  informational: { dark: "#b78bff", light: "#6135bd" },
  unknown: { dark: "#7b8b9c", light: "#61728a" },
};

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
