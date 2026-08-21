# ⚠️ Synthetic data only

**This system is not cleared to process real patient data. Not in development, not in a demo, not
in a "quick test with one real invoice".**

Everything below is a statement of what does not exist yet, so that nobody has to discover it by
being surprised.

## What the system is today

A deterministic GOÄ coding engine plus a PADnext auditor, with a test suite, a receipt hash and an
approval boundary. All of its bundled data is synthetic: three hand-written clinical cases and one
hand-written PADnext delivery, each stating in its own text that it is synthetic, with a test that
fails if a fixture starts to look like a real record.

## What is NOT implemented

| Missing | Consequence |
| --- | --- |
| **Access control** | every endpoint answers unauthenticated. There is no user, no role, no tenant, no session |
| **Audit logging** | nothing records who read or solved what. The approval record is in memory and dies with the process |
| **Encryption at rest** | no database, therefore no encrypted one. Cached results live in process memory |
| **Encryption in transit** | the service speaks plain HTTP; TLS is the deployment's job and no deployment exists |
| **Pseudonymisation / anonymisation** | none. The input contract happens to carry no identifiers, which is not the same as a pseudonymisation scheme |
| **Retention and deletion** | no policy, no mechanism, no way to answer an erasure request |
| **Data minimisation review** | never done against a real record |
| **§ 203 StGB workflow** | **nothing.** No consent capture, no Schweigepflichtentbindung, no processor-role documentation, no vendor obligation chain |
| **AVV (Auftragsverarbeitungsvertrag, Art. 28 GDPR)** | none exists with anybody |
| **DPIA (Datenschutz-Folgenabschätzung, Art. 35 GDPR)** | not started. Health data is Art. 9 special-category data; a DPIA is not optional |
| **EU / Germany-only hosting guarantee** | not established. There is no hosting at all |
| **Backup, disaster recovery, breach notification** | none |
| **Penetration test / security review** | never performed |

## § 203 StGB specifically

Medical confidentiality in Germany is criminal law, not only data-protection law. § 203 StGB makes
unauthorised disclosure of a patient secret by a physician — or by a person assisting them — a
criminal offence, and § 203 Abs. 4 extends liability to *mitwirkende Personen*: an IT service
provider processing patient data on a practice's behalf is inside that circle.

Consequences that are not yet addressed anywhere in this repository:

- A physician needs a lawful basis to involve a processor at all, and the processor's staff must be
  bound to confidentiality (§ 203 Abs. 4 Satz 1 Nr. 1) — in writing, demonstrably, per person.
- The practice must be able to show that only what was necessary was disclosed.
- A sub-processor (a cloud provider, an LLM API, a monitoring service, an error tracker) is a further
  disclosure and needs the same treatment. **Sending a real Befund to any third-party API is a
  disclosure.** That is one of the reasons the free-text extraction path was not migrated into this
  service and no LLM SDK is a dependency.

None of this is engineering work that can be done first and reviewed later. It is a legal
determination that has to happen before the first real record enters the system.

## The guards that exist, and what they are worth

The engine does refuse some things outright. These are safety rails, **not** compliance:

- **PADnext production data is refused.** `auftrag/@echtdaten="1"` marks a delivery as production
  data; `app/padnext/audit.py` raises `RealDataRefused` and the API answers `422`. The refusal can be
  lifted with `PADNEXT_ALLOW_REAL_DATA=1`, which exists so the decision is explicit, traceable and
  somebody's. Setting it does not create a lawful basis.
- **No patient identity is parsed.** The PADnext models have no field that could hold a name, an
  address or a date of birth. A real `abrechnungsfall` carries all three; none of it is needed to
  decide whether a position is chargeable, so none of it is read. `test_padnext.py` asserts this.
- **The input contract carries no identifiers.** `ClinicalExtraction` has age, sex and setting — no
  name, no insurance number, no date of birth.
- **Licensed data cannot be committed by accident.** `data/licensed/` is gitignored except its README,
  and a test fails if that stops being true.
- **No credential is held anywhere.** A test enumerates the settings schema and fails if a field
  containing `key`, `secret`, `token`, `password` or `credential` appears.

A system that reads no names can still be a § 203 problem: a Befund is a patient secret whether or
not a name is attached, and re-identification from a small clinical record is often trivial.

## What a real pilot requires, before any patient data

1. **Legal review** — § 203 StGB, GDPR Art. 9, and the applicable Landesdatenschutzgesetz and
   Berufsordnung. This is first, not last.
2. **AVV** with the practice, and with every sub-processor, plus per-person confidentiality
   undertakings under § 203 Abs. 4.
3. **DPIA** for Art. 9 special-category processing.
4. **EU hosting** with a documented data-residency guarantee, and no third-country transfer without a
   valid mechanism.
5. **Authentication and authorisation** — per-practice tenancy, per-user roles, least privilege.
6. **Tamper-evident audit logging** of every read, solve, approval and export, with a defined
   retention period.
7. **Pseudonymisation at the boundary**, with the re-identification key held by the practice.
8. **Encryption** at rest and in transit, with a key-management story.
9. **Retention and deletion**, including a working answer to an Art. 17 erasure request.
10. **A durable approval record.** The current in-memory store cannot demonstrate who approved what,
    and an approval that cannot be demonstrated is not one.
11. **Breach detection and notification** capable of the Art. 33 72-hour window.
12. **Penetration test and security review** of the whole deployment.

## And, regardless of all of the above

The output is a **billing draft** (`status: DRAFT`), and rule coverage is `partial`. A physician
remains responsible for what is billed. Nothing this engine produces may be sent to a patient or a
Verrechnungsstelle without a named human having approved it — which is why `ProposalStatus` exists
and why `approved_by` is required rather than optional.
