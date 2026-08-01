import { readFile } from "node:fs/promises";
import { join } from "node:path";

/**
 * The identity of the build this server is running.
 *
 * Read from the file Next writes at build time rather than from an environment
 * variable, so it cannot drift: whoever starts the server is describing the
 * bundle actually on disk, with nothing to remember to set.
 *
 * Cached because it cannot change without the process restarting.
 */
let cached: string | null = null;

export async function currentBuildId(): Promise<string> {
  if (cached) return cached;
  try {
    cached = (await readFile(join(process.cwd(), ".next", "BUILD_ID"), "utf8")).trim();
  } catch {
    // The dev server has no BUILD_ID file and reloads modules itself, so there
    // is no skew to detect there.
    cached = "development";
  }
  return cached;
}
