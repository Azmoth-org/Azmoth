import { NextRequest, NextResponse } from "next/server";
import { execSync } from "child_process";

/**
 * One-time endpoint to push Prisma schema to the database.
 * Call GET /api/setup?key=<SECRET_KEY> once after deploy.
 */
export async function GET(request: NextRequest) {
  const key = request.nextUrl.searchParams.get("key");
  if (key !== process.env.SETUP_SECRET) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const result = execSync("npx prisma db push --accept-data-loss", {
      encoding: "utf8",
      env: { ...process.env },
      timeout: 30000,
    });
    return NextResponse.json({ ok: true, output: result });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
