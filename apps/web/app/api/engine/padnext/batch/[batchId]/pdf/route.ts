/**
 * `POST /api/engine/padnext/batch/{batchId}/pdf`
 *   → `POST {ENGINE_BASE_URL}/api/v1/padnext/batch/{batchId}/report.pdf`
 *
 * Answers with `{batchId}_pruefbericht.pdf`, or a `409` when the batch has not completed — the
 * same refusal, for the same reason, as the CSV export beside it: a running batch would produce
 * totals that are a snapshot of an unidentifiable moment.
 *
 * No body on the way in, and nothing to attribute: like the export, this is read-only and writes no
 * audit row, so the same document can be downloaded repeatedly and is byte-identical each time. The
 * report dates itself by the job's completion, not by the clock, which is what makes that true.
 */

import { proxyEngineDownload } from "@/lib/engine"

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ batchId: string }> }
): Promise<Response> {
  const { batchId } = await params
  return proxyEngineDownload(
    `/api/v1/padnext/batch/${encodeURIComponent(batchId)}/report.pdf`,
    { method: "POST" }
  )
}
