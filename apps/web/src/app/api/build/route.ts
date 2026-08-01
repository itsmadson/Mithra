import { NextResponse } from "next/server";
import { currentBuildId } from "../../../lib/buildId";

// Never cached: the entire point is to report what is running right now.
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(
    { id: await currentBuildId() },
    { headers: { "cache-control": "no-store" } },
  );
}
