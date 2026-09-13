/**
 * A minimal but `isProposalShape`-valid `Proposal`, for specs that mock `GET /api/engine/proposals/{id}`
 * and drive `/review?id=...` the same way `positionen-table.spec.ts` mocks the PADnext audit endpoint.
 *
 * Kept in one place so the warnings-grouping and proof-lines specs build on the same shape rather
 * than drifting apart — only the `warnings` / `proposed_codes` each spec cares about differ.
 */

// Must match `/^prop_[0-9a-f]{4,}$/i` — deep-link ids are hex-only (see `lib/deep-link.ts`).
export const PROPOSAL_ID = "prop_e2eadeadbeef0000"

export function buildProposal(overrides: {
  warnings?: unknown[]
  proposed_codes?: unknown[]
}) {
  return {
    proposal_id: PROPOSAL_ID,
    status: "DRAFT",
    receipt_hash: "e2e-fixture-hash-0000000000000000",
    catalog_version: "2026-01-01",
    rules_version: "1.0.0",
    solver_version: "1.0.0",
    created_at: "2026-09-13T09:30:00Z",
    rules_hash: "e2e-fixture-rules-hash",
    rules_engine_version: "1.0.0",
    catalog_sha256: "e2e-fixture-catalog-sha",
    logic_version: "1.0.0",
    solve_time_ms: 12,
    total_time_ms: 20,
    solver_status: "optimal",
    solver_timed_out: false,
    enforced_rule_count: 10,
    advisory_rule_count: 2,
    analog_candidate_count: 0,
    suppressed_unverified_rule_count: 0,
    rule_coverage: null,
    solver_result: {
      audit_trail: {
        catalog_version: "2026-01-01",
        rules_version: "1.0.0",
        solver_status: "optimal",
        timestamp: "2026-09-13T09:30:00Z",
      },
      coding: {
        proposed_codes: overrides.proposed_codes ?? [],
        blocked_codes: [],
        warnings: overrides.warnings ?? [],
        missing_documentation: [],
      },
    },
  }
}
