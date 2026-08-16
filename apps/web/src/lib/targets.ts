/**
 * The catalogue, as the console needs it.
 *
 * Seventy-one classes cannot each have a colour a person can name, so colour
 * encodes the domain — ten of those — and the class is always written beside
 * it. The alternative, a hue per class, produces a legend nobody reads and two
 * greens that mean unrelated things.
 */

export const DOMAINS = [
  "water",
  "land_cover",
  "land_use",
  "building",
  "transport",
  "condition",
  "street",
  "energy",
  "agriculture",
  "vehicle",
] as const;

export type Domain = (typeof DOMAINS)[number];

/** Literal hex per domain, for MapLibre paint expressions, which cannot read CSS vars. */
export const DOMAIN_HEX: Record<string, { dark: string; light: string }> = {
  water: { dark: "#006dd2", light: "#005a9c" },
  land_cover: { dark: "#00ae60", light: "#009c5f" },
  land_use: { dark: "#b1425f", light: "#9b1a45" },
  building: { dark: "#ac70df", light: "#966bcb" },
  transport: { dark: "#535ab9", light: "#6233a4" },
  condition: { dark: "#dd6846", light: "#cd6130" },
  street: { dark: "#8e5600", light: "#7e4500" },
  energy: { dark: "#bb8800", light: "#b07c00" },
  agriculture: { dark: "#30762b", light: "#4a6400" },
  vehicle: { dark: "#009dc9", light: "#009eb3" },
  other: { dark: "#7b8b9c", light: "#61728a" },
};

export function domainColor(domain: string | null | undefined): string {
  const key = domain && domain in DOMAIN_HEX ? domain : "other";
  return `var(--d-${key})`;
}

export function domainHex(domain: string | null | undefined, theme: "dark" | "light"): string {
  const key = domain && domain in DOMAIN_HEX ? domain : "other";
  return DOMAIN_HEX[key][theme];
}

/**
 * A readable name for a class key.
 *
 * The catalogue is the authority and is fetched once, but a label must exist
 * before it arrives — and for legacy sign classes that predate the catalogue
 * entirely. Underscores become spaces rather than showing the raw key.
 */
export function humanise(key: string): string {
  return key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/**
 * The catalogue's name for a class, or null if it has none.
 *
 * Returning null rather than a guessed label is the point: the caller knows
 * what to do about an unnamed class — the five original sign classes are named
 * in the message files instead — and a function that silently invents a name
 * makes that impossible to detect.
 */
export function catalogueLabel(
  item: { label_en?: string | null; label?: string | null; label_fa?: string | null },
  fa: boolean,
): string | null {
  return (fa ? item.label_fa : (item.label_en ?? item.label)) || null;
}

/** Square metres, at the precision the number actually carries. */
export function formatArea(m2: number | null | undefined): string | null {
  if (m2 == null) return null;
  if (m2 >= 1_000_000) return `${(m2 / 1_000_000).toFixed(2)} km²`;
  if (m2 >= 10_000) return `${(m2 / 10_000).toFixed(2)} ha`;
  return `${Math.round(m2)} m²`;
}
