#!/usr/bin/env python3
"""Write a synthetic PADnext test delivery — for the pilot's "generate a test delivery" card.

    ./scripts/generate_synthetic_delivery.py
    ./scripts/generate_synthetic_delivery.py -o meine-testlieferung.xml
    ./scripts/generate_synthetic_delivery.py --positions 5 --seed 7

Writes one bare `*_padx.xml` payload — the same shape `scripts/anonymize_padnext.py` reads and
produces, and the one the upload screens at `/padnext` and `/padnext/batch` accept. It is built
from nothing rather than derived from a real delivery: there is no patient to anonymise here, only
invented GOÄ positions against an invented invoice number, so the pilot's "generate a test
delivery" card has something to hand a reader who has never touched a PVS export and does not want
to.

── Zero dependencies, on purpose ────────────────────────────────────────────────────────────────
Same requirement as the anonymiser this sits beside, and the same reason: a person trying the pilot
should be able to run this on their own machine — Python 3.9 or newer, standard library only, one
file, no network access.

── `echtdaten="false"` from the moment it exists ────────────────────────────────────────────────
The anonymiser stamps that attribute onto a delivery that might have said otherwise; this one never
has anything else to say. `PADNEXT_ALLOW_REAL_DATA=false` is what every pilot deployment runs with
(`docs/pilot/PILOT_DEMO_GUIDE.md`), so a file this script writes uploads cleanly on the first try.

── What is inside, and what is not ──────────────────────────────────────────────────────────────
One `<rechnung>` with `--positions` GOÄ line items (three by default), each a real Ziffer from a
small hand-picked list, a plausible Steigerungsfaktor and a `<gesamtbetrag>` computed the same way
the engine recomputes one — Punkte × Punktwert × Faktor, rounded to the cent. The patient block
carries an invented name that is obviously invented ("Testpatient", never a real German name list)
rather than nothing at all, because `apps/engine/app/padnext/reader.py` expects the element to be
there; no field in it is read for anything but display.

`--seed` makes a run reproducible — the same seed always writes the same positions and the same
`<datum>` values — which is the only thing worth pinning in a file that otherwise exists to be
disposable.
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PAD_NS = "http://padinfo.de/ns/pad"

#: The statutory Punktwert (§ 5 Abs. 1 GOÄ), in euro-cents-per-Punkt. Unchanged since 1996 — see
#: `apps/engine/scripts/make_temporal_fixtures.py`, which carries the same number for the same
#: reason. A synthetic delivery still owes a reader an amount that is arithmetically honest.
POINT_VALUE = Decimal("0.0582873")


@dataclass(frozen=True)
class ZifferEntry:
    ziffer: str
    text: str
    punktzahl: int


#: A small, ordinary handful of GOÄ Ziffern — not the whole catalog, just enough that a generated
#: delivery reads like a real one instead of the same single line repeated.
CATALOG = (
    ZifferEntry("1", "Beratung", 80),
    ZifferEntry("5", "Symptombezogene Untersuchung", 150),
    ZifferEntry("7", "Vollständige Untersuchung eines Organsystems", 200),
    ZifferEntry("75", "Ausführliche Beratung", 240),
    ZifferEntry("250", "Blutentnahme", 30),
    ZifferEntry("410", "Sonographische Untersuchung", 210),
)

#: Obviously synthetic. Never a name that could coincide with a real patient's — see the module
#: docstring on why the field is populated at all.
PATIENT_NAME = "Testpatient"
PATIENT_ID = "SYN-0001"

#: The factor range this picks from. 1.0–2.3 needs no justification on the invoice (§ 5 Abs. 2
#: GOÄ); above 2.3 does, which is why `begruendung` only appears on those lines below.
FACTOR_CHOICES = (Decimal("1.0"), Decimal("1.8"), Decimal("2.3"), Decimal("3.5"))


def line_amount(punktzahl: int, faktor: Decimal) -> Decimal:
    return (Decimal(punktzahl) * POINT_VALUE * faktor).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def build_position(index: int, entry: ZifferEntry, faktor: Decimal, when: date) -> str:
    amount = line_amount(entry.punktzahl, faktor)
    begruendung = (
        f'\n          <begruendung>Erhöhter Aufwand, synthetischer Testfall {index}.'
        f"</begruendung>"
        if faktor > Decimal("2.3")
        else ""
    )
    return f"""        <goziffer positionsnr="{index}" go="GOÄ" ziffer="{entry.ziffer}">
          <datum>{when.isoformat()}</datum>
          <anzahl>1</anzahl>
          <text>{entry.text}</text>
          <faktor>{faktor}</faktor>{begruendung}
          <punktzahl>{entry.punktzahl}</punktzahl>
          <punktwert>{POINT_VALUE}</punktwert>
          <gesamtbetrag>{amount}</gesamtbetrag>
        </goziffer>"""


def build_delivery(positions: int, rng: random.Random, invoice_id: str) -> str:
    today = date.today()
    entries = [rng.choice(CATALOG) for _ in range(positions)]
    blocks = [
        build_position(
            index=i + 1,
            entry=entry,
            faktor=rng.choice(FACTOR_CHOICES),
            when=today - timedelta(days=rng.randint(0, 30)),
        )
        for i, entry in enumerate(entries)
    ]

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rechnungen anzahl="1" echtdaten="false" xmlns="{PAD_NS}">
  <nachrichtentyp version="02.12">ADL</nachrichtentyp>
  <rechnungsersteller><name>Azmoth Pilot — synthetische Testdaten</name></rechnungsersteller>
  <rechnung id="{invoice_id}">
    <patient patid="{PATIENT_ID}">
      <patient_name>{PATIENT_NAME}</patient_name>
    </patient>
    <abrechnungsfall>
      <behandlungsart>0</behandlungsart>
      <vertragsart>1</vertragsart>
      <positionen posanzahl="{positions}">
{chr(10).join(blocks)}
      </positionen>
    </abrechnungsfall>
  </rechnung>
</rechnungen>
"""


def default_filename(invoice_id: str) -> str:
    # `<kundennr>_<datum>_<typ>_<nr>_padx.xml`, the convention `anonymize_padnext.py` documents —
    # a made-up customer number, today's date, `ADL` for the message type, and a running number.
    stamp = date.today().strftime("%Y%m%d")
    return f"00000000_{stamp}_ADL_{invoice_id}_padx.xml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="output path (default: derived from today's date)"
    )
    parser.add_argument(
        "--positions",
        type=int,
        default=3,
        help="how many GOÄ line items to write (default: 3)",
    )
    parser.add_argument(
        "--seed", type=int, help="fix the random choices, for a reproducible delivery"
    )
    args = parser.parse_args(argv)

    if args.positions < 1:
        parser.error("--positions must be at least 1")

    rng = random.Random(args.seed)
    invoice_id = f"{rng.randint(1, 999999):06d}"
    document = build_delivery(args.positions, rng, invoice_id)

    output = args.output or Path(default_filename(invoice_id))
    output.write_text(document, encoding="utf-8")

    print(f"wrote {output} ({args.positions} Position(en), echtdaten=\"false\")")
    print("Hochladen unter /padnext oder /padnext/batch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
