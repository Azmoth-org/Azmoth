"""The public demo surface. Two endpoints, no credential, and no way to send it a file.

This is the third authentication boundary in the service, and it is the only one that authenticates
nobody at all — so it is worth being explicit about what stops it being a liability.

**It takes no input.** Neither endpoint declares a body, a query parameter or a path parameter.
`app.services.demo` audits one committed synthetic delivery whose path is a constant. There is
therefore no request a visitor can compose that makes this service process *their* document, which
is what keeps a public demo outside GDPR Art. 9 and § 203 StGB rather than merely careful about
them. A public endpoint that accepted an upload would be a medical-data processor open to the
internet; this one is a fixed document served by a solver, and the difference is structural.

**It has no tenant, so it bills nobody.** `app.core.observability._meter` writes a usage row only
when the request context carries an `organization_id`, and nothing here sets one. A demo visitor
therefore cannot appear in `api_usage_logs` at all — not as a free row to be filtered out later,
but as no row. `tests/test_demo.py` pins that, because "it happens not to be metered" and "it
cannot be metered" are different properties and only the second one survives a refactor.

**It cannot exhaust the solver.** The report is memoised for the process lifetime (see
`app.services.demo` on why that is sound rather than a cache with a correctness cost), so a request
is a serialisation rather than a Soufflé subprocess. That matters because the engine's rate limiter
counts per API key and a demo visitor has none — without the memo this would be the one unmetered
path in the service that spawns a process.

**It is not the partner API.** These routes are outside `docs/api/PARTNER_API.md`'s contract and
may change with the marketing site that consumes them. A PVS vendor evaluating the engine gets a
sandbox key and the real `/api/v1/audit/*` surface; this is for a visitor who has not spoken to
anyone yet.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import pipeline
from app.schemas import PadnextAuditReport
from app.services.demo import DEMO_DELIVERY_FILENAME, DemoUnavailable, demo_report
from app.services.pdf import render_single_report

log = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])

#: Stamped under the title of the demo PDF. In the document rather than as a watermark, because a
#: watermark is the first thing a photocopy or a screenshot loses, and this sentence is the one
#: that has to survive the report being forwarded to somebody who never saw the screen.
DEMO_PDF_NOTE = (
    "DEMONSTRATION — synthetische Testdaten, keine echten Patienten- oder Abrechnungsdaten."
)

#: What goes on the demo report's "Praxis / Konto" line.
#:
#: The demo has no tenant by construction — that is the whole of why it may be public — so this
#: line had nothing to print and printed an em dash. An em dash beside "Erstellt am —" reads as a
#: document that failed to load its own header, on the one page a prospect forwards to a colleague.
#: Naming the account as the demo is both true and the more useful statement.
#:
#: Not routed through `organization_label`: that function's job is to refuse a *caller-asserted*
#: organisation the shape of a sentence (see `app.api.tenancy`), and this is a constant in our own
#: source with no request anywhere near it.
DEMO_PDF_ORGANIZATION = "Azmoth Demo (synthetische Daten)"


def _unavailable(exc: DemoUnavailable) -> HTTPException:
    """A 503, never a 500.

    Both ways `DemoUnavailable` is raised are deployment faults — an image built without `logic/`,
    or a fixture that is not synthetic — and neither is caused by the caller or fixable by them.
    A 503 says "this deployment cannot serve the demo right now" and leaves every other route
    reporting healthy, which is the truth.
    """
    log.error("public demo unavailable: %s", exc)
    return HTTPException(
        status_code=503,
        detail={
            "error": "demo_unavailable",
            "error_code": "DEMO_UNAVAILABLE",
            "message": (
                "Die Demo-Prüfung steht in dieser Installation nicht zur Verfügung. Die "
                "mitgelieferte Beispiel-Lieferung konnte nicht geladen werden."
            ),
            "details": {"delivery": DEMO_DELIVERY_FILENAME},
        },
    )


@router.post(
    "/audit",
    response_model=PadnextAuditReport,
    summary="Beispiel-Lieferung prüfen (öffentlich, ohne Anmeldung)",
)
def demo_audit() -> PadnextAuditReport:
    """Die mitgelieferte synthetische Beispiel-Lieferung, geprüft.

    **Ohne Anmeldung erreichbar und ohne Eingabe.** Der Endpunkt nimmt keine Datei entgegen — er
    prüft ausschliesslich die im Repository hinterlegte synthetische Lieferung mit ihren neun
    bewusst eingebauten Fehlern. Es gibt daher keine Anfrage, mit der ein Besucher eigene Daten in
    dieses System bringen könnte; das ist der Grund, warum diese Demo öffentlich sein darf.

    Die Antwort ist derselbe `PadnextAuditReport`, den `/api/v1/audit/single` für dieselbe Datei
    liefert, aus demselben Code gegen denselben Katalog — gleiche Verdikte, gleicher
    `receipt_hash`. Die Demo zeigt also das Produkt und nicht eine Nachbildung davon.

    ---

    The bundled nine-error synthetic delivery, audited. No authentication, and — more importantly —
    no request body, so this cannot be turned into an upload endpoint by a caller. Deterministic
    and memoised: see `app.services.demo`.
    """
    try:
        return demo_report(pipeline())
    except DemoUnavailable as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/report.pdf",
    response_class=Response,
    summary="Beispiel-Prüfbericht als PDF (öffentlich, ohne Anmeldung)",
    responses={
        200: {
            "description": "Der Prüfbericht als PDF, `azmoth_demo_pruefbericht.pdf`.",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        },
        503: {"description": "Die Beispiel-Lieferung ist in dieser Installation nicht verfügbar."},
    },
)
def demo_pdf() -> Response:
    """Derselbe Bericht als druckbares PDF, mit dem Demo-Hinweis im Dokument.

    `POST` statt `GET`, wie beim Stapelbericht: der Endpunkt rendert ein Dokument, statt ein
    gespeichertes zu lesen. Die Prüfung selbst ist deterministisch — dieselbe Lieferung ergibt
    dieselben Verdikte und denselben `receipt_hash`; das Dokument trägt zusätzlich den
    Erstellungszeitpunkt, sodass sich zwei Abrufe genau darin unterscheiden.

    ---

    The same report as a printable PDF. The demo note is rendered *into* the document rather than
    stamped over it, so that a forwarded copy still says what it is.

    **Two downloads are no longer byte-identical, and that is the trade this endpoint now makes.**
    The document used to carry no clock at all, which made it reproducible and made its header read
    "Erstellt am —". A Prüfbericht with no date on it is not a document somebody files; it is one
    they ask you to send again properly. So the wall clock is stamped, exactly as the authenticated
    `/padnext/audit.pdf` has always stamped it, and what stays reproducible is the thing that
    actually has to be — the audit: same verdicts, same euros, same `receipt_hash`, which is the
    value a reader compares two copies by.
    """
    try:
        report = demo_report(pipeline())
    except DemoUnavailable as exc:
        raise _unavailable(exc) from exc

    document = render_single_report(
        report,
        note=DEMO_PDF_NOTE,
        # A demo PDF whose header read "Erstellt am —" and "Praxis / Konto —" looked like a
        # document with two failed lookups in it, which is the opposite of the impression a
        # prospect should take from the one artefact they are allowed to keep. Both are stated
        # rather than left blank: the clock is real, and the account line names the demo as a
        # demo.
        organization=DEMO_PDF_ORGANIZATION,
        generated_at=datetime.now(timezone.utc),
        # The store the audit actually ran against, so § 1's "geprüft gegen N durchgesetzte Regeln"
        # and § 2's per-family counts are this deployment's real figures rather than a report-time
        # echo. `pipeline()` is memoised, so this is the same object `demo_report` just used.
        rules=pipeline().rules,
    )
    return Response(
        content=document,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="azmoth_demo_pruefbericht.pdf"',
            "Cache-Control": "no-store",
        },
    )
