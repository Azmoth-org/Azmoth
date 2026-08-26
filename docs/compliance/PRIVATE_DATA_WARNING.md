# ⚠️ Synthetic data only

**This system is not cleared to process real patient data. Not in development, not in a demo, not
in a "quick test with one real invoice".**

Everything below is a statement of what does not exist yet, so that nobody has to discover it by
being surprised.

## What the system is today

A deterministic GOÄ coding engine plus a PADnext auditor, with a test suite, a receipt hash, an
approval boundary, and — since the Postgres migration — a durable proposal record and an append-only
audit log. All of its bundled data is synthetic: three hand-written clinical cases and one
hand-written PADnext delivery, each stating in its own text that it is synthetic, with a test that
fails if a fixture starts to look like a real record.

**Neither the database nor the login changes whether real data may be processed.** Three items below
have moved since this file was written; every other one is untouched, and the answer to "can we try
one real invoice" is still no.

## What is NOT implemented

| Missing | Consequence |
| --- | --- |
| **Access control** | **partially closed.** The web application requires a Better Auth session — email and password, sessions in the same Postgres — and every screen and every `/api/engine/*` proxy route refuses a request without one. Four things are still missing. **Sign-up is open**: anyone who can reach `/signup` can make an account, so there is authentication but no *authorisation* to be here at all; an invite flow or an SSO integration is what closes it. **There are no roles**: every account can approve, reject and export, so there is no separation between a reviewer and an administrator and no tenant boundary. **The engine itself authenticates nobody**: it trusts an `X-User-ID` header the web tier sets, which is sound only because the engine is not published to a browser and that proxy is its only caller — a Bearer token the engine verifies is the next step (`apps/engine/app/api/identity.py` says so at the point where it would go). And **`approved_by` is still a typed string**, not the session identity: the person who signs an approval and the account that was signed in are recorded separately and are not required to match. Google sign-in can now be switched on per deployment (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`, off unless both are set) and **does not close any of the four**: any Google account can register, not only one from a chosen Workspace domain, so it is a second way through the same open door rather than an authorisation boundary. Enabling it does add a third party — see the AVV row |
| **Audit logging** | **partially closed.** `audit_events` is an append-only log of every create, read, approval, rejection and export, with an actor and a timestamp, written in the same transaction as the change it records. The actor is now a real `user.id` for anything done through the UI — resolvable to a person by a join, and mirrored onto `proposals.created_by` and `batch_jobs.created_by` for the queries a data-subject request actually asks — rather than the `anonymous` it used to be. What is still missing is a defined retention period, and the caveat above about the engine trusting a header rather than verifying a token. `REVOKE UPDATE, DELETE` for the application role is documented in the migration and belongs to the deployment's grants |
| **Encryption at rest** | none. There is a database now (Postgres), and nothing encrypts it — not the volume, not a column, and there is no key management. Cached results still live in process memory |
| **Encryption in transit** | the service speaks plain HTTP; TLS is the deployment's job and no deployment exists. Note that this now carries a session cookie and a password on the sign-in request, so plain HTTP is a credential exposure and not only a data one. The cookie is marked `Secure` and `HttpOnly` under `NODE_ENV=production`, which is the half the application can enforce |
| **Pseudonymisation / anonymisation** | none. The input contract happens to carry no identifiers, which is not the same as a pseudonymisation scheme |
| **Retention and deletion** | no policy, no mechanism, no way to answer an erasure request. Note that there is now a `user` table holding names and email addresses, and that `audit_events` is append-only by construction — so an erasure request touching an actor id is a question this schema currently has no answer to |
| **Data minimisation review** | never done against a real record |
| **§ 203 StGB workflow** | **nothing.** No consent capture, no Schweigepflichtentbindung, no processor-role documentation, no vendor obligation chain |
| **AVV (Auftragsverarbeitungsvertrag, Art. 28 GDPR)** | none exists with anybody. A deployment that switches Google sign-in on adds Google as a recipient of authentication data — who signed in to this deployment, and when — which needs its own legal basis and contract before it is turned on anywhere that is not synthetic. No patient data crosses that boundary and Google is told nothing about what is being reviewed, which limits the exposure without removing it |
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
   retention period. *Partly built:* the log exists and is append-only (enforced in the ORM, and to
   be enforced again by `REVOKE UPDATE, DELETE` on the application role). "Tamper-evident" in the
   full sense — a hash chain or an external witness, so that a database owner cannot rewrite it
   undetectably — is not built, and neither is the retention period.
7. **Pseudonymisation at the boundary**, with the re-identification key held by the practice.
8. **Encryption** at rest and in transit, with a key-management story.
9. **Retention and deletion**, including a working answer to an Art. 17 erasure request.
10. ~~**A durable approval record.**~~ **Done.** Proposals and approvals are in Postgres, every
    decision writes an audit event in the same transaction, and the engine refuses to start in
    production on anything but Postgres. See
    [`../architecture/DATABASE.md`](../architecture/DATABASE.md). What this does *not* yet
    demonstrate is *who* approved — that needs item 5, because a name the service never verified
    identifies nobody.
11. **Breach detection and notification** capable of the Art. 33 72-hour window.
12. **Penetration test and security review** of the whole deployment.

## And, regardless of all of the above

The output is a **billing draft** (`status: DRAFT`), and rule coverage is `partial`. A physician
remains responsible for what is billed. Nothing this engine produces may be sent to a patient or a
Verrechnungsstelle without a named human having approved it — which is why `ProposalStatus` exists
and why `approved_by` is required rather than optional.
