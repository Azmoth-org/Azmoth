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

/**
 * What `GET /api/v1/proposals` returns: a page of proposals, newest first, plus the real `total`.
 *
 * `total` counts every proposal matching the request's `status` and `case_id` filters — not the
 * page, and not the table. That is the field a listing exists for: without it a client cannot tell
 * fifty drafts from the first fifty of nine hundred, and a review queue that cannot state its own
 * size is not a queue.
 *
 * Rows are the full `Proposal`, so a listing carries each draft's rule-coverage counts and its whole
 * `solver_result`. Ask for a small `limit`.
 */
export type ProposalList = Schemas["ProposalList"];

/**
 * Body of `POST /api/v1/proposals/{id}/export`. `exported_by` is required, for the same reason
 * `approved_by` is on an approval: it is recorded in the audit log. It is not authenticated.
 */
export type ExportRequest = Schemas["ExportRequest"];

/**
 * The downloadable record of one exported proposal — served as an attachment, not rendered.
 *
 * Carries what the `Proposal` response cannot: `input_hash`, the decision record, and the full
 * append-only audit log including the `EXPORTED` event the export itself wrote. A client that
 * needs to *display* a proposal should read `Proposal`; this type exists so a caller that
 * post-processes the downloaded file is typed against the same document the engine wrote.
 */
export type ProposalExport = Schemas["ProposalExport"];
export type ProposalExportDecision = Schemas["DecisionRecord"];
export type ProposalExportEngineIdentity = Schemas["EngineIdentity"];
export type ProposalExportAuditEvent = Schemas["AuditEventRecord"];

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
 * What `GET /api/v1/padnext/batch` returns: a page of batches, newest first, plus the real `total`.
 *
 * This is what makes a stored batch reachable again — the `batch_id` from the `202` lives in the
 * caller's memory, so before this endpoint a browser reload orphaned a finished batch whose roll-up
 * was still in Postgres. `total` is the whole table, never the page.
 */
export type BatchAuditJobList = Schemas["BatchAuditJobList"];

/**
 * One batch as a listing row: the header and the roll-up, and **no** `files`.
 *
 * Deliberately a distinct type from `BatchAuditJob` rather than one with an empty `files` array —
 * there is no field here to mistake for "this batch has no deliveries". Open a row with
 * `GET /api/v1/padnext/batch/{batch_id}` for the per-file detail. A row whose `error_message` reads
 * "Interrupted by server restart" was closed by the engine's startup recovery, not by an audit.
 */
export type BatchAuditJobSummary = Schemas["BatchAuditJobSummary"];

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

/* -- the rule verification workflow --------------------------------------------------------- */

/**
 * One unverified rule as the review queue presents it, with the GOÄ sentence it was extracted
 * from. The quote is the evidence a reviewer decides on — never render a truncated one.
 */
export type ReviewableRule = Schemas["ReviewableRule"];

/** Which rule table a reviewable rule came from. Closed union: every value needs a label. */
export type RuleKind = ReviewableRule["kind"];

/** `VERIFIED` | `REJECTED` | `PENDING`. `PENDING` decides nothing and leaves the rule queued. */
export type RuleReviewStatus = NonNullable<ReviewableRule["review_status"]>;

/** What `GET /api/v1/rules/review-queue` returns: the page, plus the real backlog behind it. */
export type RuleReviewQueue = Schemas["RuleReviewQueue"];

/**
 * Body of `POST /api/v1/rules/{rule_id}/review`. `reviewed_by` is required for a decision:
 * verifying a rule changes what every future audit concludes about somebody's invoice.
 */
export type RuleReviewRequest = Schemas["RuleReviewRequest"];

/** The reviewed rule and the coverage it moved, so a progress bar updates from one response. */
export type RuleReviewResult = Schemas["RuleReviewResult"];

/* -- catalog and vocabulary ---------------------------------------------------------------- */

export type HealthResponse = Schemas["HealthResponse"];

/**
 * One solver's probe result, off `HealthResponse["solvers"]`.
 *
 * `status` is three-valued and the middle value is the useful one: `unavailable` means the solver is
 * not installed on that host, `failed` means it *is* installed and did not produce the right answer.
 * The old health endpoint could not tell those apart — it reported presence — and a container whose
 * Soufflé is present and broken is the failure this type exists to make renderable.
 */
export type SolverHealth = Schemas["SolverHealth"];

export type CatalogResponse = Schemas["CatalogResponse"];
export type ZifferResponse = Schemas["ZifferResponse"];
export type VocabularyResponse = Schemas["VocabularyResponse"];
export type EntityTypeOption = Schemas["EntityTypeOption"];
export type LabelledOption = Schemas["LabelledOption"];
export type BilingualOption = Schemas["BilingualOption"];
export type ComplexityRef = Schemas["ComplexityRef"];

/* -- API keys and usage --------------------------------------------------------------------- */

/**
 * A newly minted key. **The only shape in this package that carries a secret**, and it exists once:
 * the engine stores a SHA-256 hash, so no later response can produce the token again. A UI built
 * against this type has to show it immediately or lose it — which is the behaviour the storage
 * decision requires, made visible in the type rather than left to a comment.
 */
export type ApiKeyIssued = Schemas["ApiKeyIssued"];

/** A key as it can be read back: everything except the secret. Note the absence of `token`. */
export type ApiKeySummary = Schemas["ApiKeySummary"];
export type ApiKeyList = Schemas["ApiKeyList"];
export type ApiKeyRequest = Schemas["ApiKeyRequest"];
export type ApiKeyRevoked = Schemas["ApiKeyRevoked"];

/** What one practice consumed over one stated window. The basis of an invoice. */
export type UsageSummary = Schemas["UsageSummary"];
export type UsageByEndpoint = Schemas["UsageByEndpoint"];
export type UsageByKey = Schemas["UsageByKey"];

/* -- subscriptions, quota and priced periods ------------------------------------------------ */

/**
 * Two conventions run through every shape below, and both matter at a call site.
 *
 * **Every euro amount is an integer count of cents**, named `*_cents`. `9900` is 99,00 €. There is
 * no field anywhere carrying a formatted or decimal amount, because a JSON number that looks like
 * money invites `parseFloat`, and the sum of a few thousand overage lines is where that stops being
 * harmless. Format with `Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" })` on
 * `cents / 100` at the point of display, and nowhere else.
 *
 * **The billable unit is invoices, not requests.** `invoices_processed` is what a quota is spent
 * against and what an invoice is built from; one bulk upload of 300 deliveries is one request and
 * 300 invoices. `requests` sits beside it for context only.
 */
export type BillingUsage = Schemas["BillingUsage"];

/**
 * What a practice is entitled to. The numbers come from the practice's own row rather than from the
 * plan catalog — they were snapshotted when the plan was assigned, so a later change to the catalog
 * cannot alter what was agreed. `plan_code` says what they were taken from.
 */
export type SubscriptionSummary = Schemas["SubscriptionSummary"];

/** One plan in the catalog. `code` carries its revision: prices are superseded, never edited. */
export type PlanSummary = Schemas["PlanSummary"];
export type PlanCatalog = Schemas["PlanCatalog"];

/** One closed period, priced. Not a Rechnung in the legal sense — see `docs/BILLING.md`. */
export type BillingInvoice = Schemas["BillingInvoice"];
export type BillingInvoiceList = Schemas["BillingInvoiceList"];

/** A plan change. Name exactly one of `tier` or `plan_code`; both or neither is a 422. */
export type UpgradeRequest = Schemas["UpgradeRequest"];
export type UpgradeResult = Schemas["UpgradeResult"];

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
  padnextBatchDetail: "/api/v1/padnext/batch/{batch_id}",
  padnextBatchExport: "/api/v1/padnext/batch/{batch_id}/export",
  proposalExport: "/api/v1/proposals/{proposal_id}/export",
  catalog: "/api/v1/catalog",
  ruleCoverage: "/api/v1/rules/coverage",
  ruleReviewQueue: "/api/v1/rules/review-queue",
  vocabulary: "/api/v1/vocabulary",
  apiKeys: "/api/v1/settings/api-keys",
  apiKeyDetail: "/api/v1/settings/api-keys/{key_id}",
  usage: "/api/v1/settings/usage",
  billingUsage: "/api/v1/billing/usage",
  billingPlans: "/api/v1/billing/plans",
  billingUpgrade: "/api/v1/billing/upgrade",
  billingInvoices: "/api/v1/billing/invoices",
} as const satisfies Record<string, EnginePath>;
