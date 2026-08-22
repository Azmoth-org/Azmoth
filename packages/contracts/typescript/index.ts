/**
 * Named aliases for the engine types a client actually uses.
 *
 * `schema.ts` is generated and exhaustive; reaching into
 * `components["schemas"]["…"]` at every call site is noise. This file is the only hand-written
 * one in the package, and it contains no shapes of its own — every alias resolves into the
 * generated schema, so it cannot drift from the API.
 *
 * Regenerate with:
 *   (apps/engine)  python scripts/export_openapi.py
 *   (repo root)    pnpm --filter @workspace/contracts generate
 */

import type { components, operations, paths } from "./schema";

export type { components, operations, paths };

type Schemas = components["schemas"];

/* -- the coding path ----------------------------------------------------------------------- */

/** Request body of `POST /api/v1/solve`. Clinical entities only — no billing fields. */
export type SolveRequest = Schemas["SolveRequest"];

/**
 * The extraction models come in two variants because FastAPI publishes two: on the way IN an
 * entity `id` is optional (the engine assigns one), on the way OUT it is always present. Writing
 * a request against the `-Output` shape would demand ids the caller has no business inventing, so
 * the `Input` aliases are what a client builds and the `Output` aliases are what it reads back.
 */
export type ClinicalExtraction = Schemas["ClinicalExtraction-Input"];
export type ClinicalExtractionOutput = Schemas["ClinicalExtraction-Output"];
export type Patient = Schemas["Patient"];
export type Consultation = Schemas["Consultation-Input"];
export type Examination = Schemas["Examination-Input"];
export type Procedure = Schemas["Procedure-Input"];
export type LabTest = Schemas["LabTest-Input"];
export type Diagnosis = Schemas["Diagnosis-Input"];
export type JustificationFactor = Schemas["JustificationFactor-Input"];

/**
 * What `POST /api/v1/solve` returns. A **draft**, not an invoice: `status` is `DRAFT` until a
 * named person approves it. Never render an unapproved proposal as a bill.
 */
export type Proposal = Schemas["Proposal"];
export type ProposalStatus = Schemas["ProposalStatus"];
export type ApprovalRequest = Schemas["ApprovalRequest"];
export type RejectionRequest = Schemas["RejectionRequest"];

export type CodingResponse = Schemas["CodingResponse"];
export type Coding = Schemas["Coding"];
export type InvoiceLine = Schemas["InvoiceLine"];
export type Totals = Schemas["Totals"];
export type BlockedCode = Schemas["BlockedCode"];
export type AnalogDecision = Schemas["AnalogDecision"];
export type ProofStep = Schemas["ProofStep"];
export type AuditTrail = Schemas["AuditTrail"];

/**
 * Why a line carries the Steigerungsfaktor it does. A closed union, so a client can label every
 * value exhaustively — it was an open `string` until the engine's contract was tightened.
 */
export type FactorBasis = InvoiceLine["factor_basis"];

/** A gap in the record, never a suggestion to charge more. See the engine docs. */
export type MissingDocumentation = Schemas["MissingDocumentation"];

/**
 * How much of the rule set is actually enforced. `enforced_rule_count` can suppress a position;
 * `advisory_rule_count` only warns. A UI must not present an advisory rule as enforced.
 */
export type RuleCoverage = Schemas["RuleCoverage"];

/** Named `Warning_` in Python to avoid shadowing the builtin. */
export type EngineWarning = Schemas["Warning_"];
export type WarningSeverity = EngineWarning["severity"];

/* -- PADnext ------------------------------------------------------------------------------- */

export type PadnextAuditReport = Schemas["PadnextAuditReport"];
export type PadnextAuditedPosition = Schemas["PadnextAuditedPosition"];
export type PadnextFinding = Schemas["PadnextFinding"];
/** Closed union: every value needs a label, or a verdict renders as a raw identifier. */
export type PadnextVerdict = PadnextAuditedPosition["verdict"];

/**
 * Which of the three honest financial buckets a claimed position was counted into.
 *
 * Distinct from `PadnextVerdict`, and the distinction is the point: a verdict says what the
 * *enforced* rules concluded, a bucket says how much weight that conclusion can bear. A position
 * the rules failed to confirm is `blocked` in the verdict but only `unconfirmed` here — and a UI
 * must never render `unconfirmed` as a defect. See `PadnextAuditReport.unconfirmed_eur`.
 */
export type PadnextPositionBucket = PadnextAuditedPosition["bucket"];

/* -- PADnext, in batch --------------------------------------------------------------------- */

/**
 * The `202` body of `POST /api/v1/padnext/batch`: a handle to poll, and nothing more.
 *
 * The audit has not started when this is returned. Do not render a dashboard from it.
 */
export type BatchAuditAccepted = Schemas["BatchAuditAccepted"];

/** What `GET /api/v1/padnext/batch/{batch_id}` returns: progress, then the roll-up and the files. */
export type BatchAuditJob = Schemas["BatchAuditJob"];
export type BatchJobStatus = Schemas["BatchJobStatus"];
export type BatchFileStatus = Schemas["BatchFileStatus"];

/** One uploaded delivery and what became of it. `report` is null until the job is terminal. */
export type BatchFileResult = Schemas["BatchFileResult"];

/**
 * The three honest buckets, summed across every file that could be audited.
 *
 * It carries the same three fields as `PadnextAuditReport` and the same prohibition: they must
 * never be added back together into a single "at risk" headline. At batch scale `unconfirmed_eur`
 * is the engine's own rule-coverage gap summed over a year of invoices, and presenting it as
 * exposure would be a six-figure false statement about a practice. `confirmed_wrong_eur` is the
 * only figure here that may be shown as a defect.
 *
 * `failed_file_count` is part of the summary, not only of the job, because the roll-up covers the
 * completed files alone — a reader has to be able to see what it is missing.
 */
export type BatchAggregateSummary = Schemas["BatchAggregateSummary"];

/* -- catalog and vocabulary ---------------------------------------------------------------- */

export type HealthResponse = Schemas["HealthResponse"];
export type CatalogResponse = Schemas["CatalogResponse"];
export type ZifferResponse = Schemas["ZifferResponse"];
export type VocabularyResponse = Schemas["VocabularyResponse"];
export type EntityTypeOption = Schemas["EntityTypeOption"];
export type LabelledOption = Schemas["LabelledOption"];
export type BilingualOption = Schemas["BilingualOption"];
export type ComplexityRef = Schemas["ComplexityRef"];

/* -- shared enums -------------------------------------------------------------------------- */

export type Setting = NonNullable<SolveRequest["setting"]>;
export type Complexity = NonNullable<Procedure["complexity"]>;
export type Severity = NonNullable<JustificationFactor["severity"]>;

/* -- routes -------------------------------------------------------------------------------- */

/** Every path the engine serves, as a literal union — no string typos at a call site. */
export type EnginePath = keyof paths;

export const ENGINE_ROUTES = {
  health: "/api/v1/health",
  solve: "/api/v1/solve",
  proposals: "/api/v1/proposals",
  padnextAudit: "/api/v1/padnext/audit",
  padnextBatch: "/api/v1/padnext/batch",
  catalog: "/api/v1/catalog",
  vocabulary: "/api/v1/vocabulary",
} as const satisfies Record<string, EnginePath>;
