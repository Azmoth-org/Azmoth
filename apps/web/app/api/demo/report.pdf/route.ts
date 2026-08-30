/**
 * `POST /api/demo/report.pdf` → `POST {ENGINE_BASE_URL}/api/v1/demo/report.pdf`
 *
 * **Public**, for the same reason and under the same constraint as `/api/demo/audit`: the engine
 * endpoint takes no input and renders one committed synthetic delivery.
 *
 * The bytes come back untouched, with the engine's own `Content-Disposition` so the browser saves
 * the file under the name the engine chose. The demo notice is rendered *into* the document rather
 * than stamped over it — a PDF outlives the page it was downloaded from, and a forwarded copy has
 * to still say that it describes synthetic data.
 */

import { proxyPublicEngineDownload } from "@/lib/engine"

export async function POST(): Promise<Response> {
  return proxyPublicEngineDownload("/api/v1/demo/report.pdf")
}
