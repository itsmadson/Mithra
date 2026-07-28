export function advance<T>(items: T[], index: number): number {
  return Math.min(index + 1, items.length);
}

export function needsRefill<T>(items: T[], index: number): boolean {
  return index >= items.length;
}
