---
name: audit-closure-protocol
description: Run bounded, evidence-based audits with a frozen finding ledger, root-cause deduplication, controlled fixes, focused closure verification, and an exact final report. Use whenever the user asks to audit, re-audit, inspect for issues, review defects or risks, audit and fix, verify audit fixes, close findings, or assess security, authorization, data integrity, API/schema parity, lifecycle behavior, failure paths, test coverage, CI gates, or performance contracts in this repository.
---

# Audit Closure Protocol

Use explicit contracts and reproducible evidence to prevent scope drift, duplicate
findings, false-positive closure, and unbounded audit/fix loops.

## Determine the authorized mode

Honor the user's requested scope before doing work:

- Treat `audit`, `review`, `inspect`, and similar requests as read-only discovery
  unless the user also asks to fix, implement, close, or modify.
- For read-only work, complete discovery and publish the frozen finding ledger.
  Do not edit implementation files.
- For `audit and fix`, `fix audit findings`, or equivalent requests, run the full
  discovery, fix, and closure workflow below.
- For verification of previously defined findings, use the supplied finding IDs
  and acceptance criteria. Do not restart unrestricted discovery.
- Ask before continuing only when an ambiguity would materially change scope or
  authorization. Otherwise make conservative, documented assumptions.

## Establish the audit contract

Before broad implementation work:

1. State the exact audit target: commits, working-tree changes, plan, subsystem,
   endpoints, schemas, components, or performance workloads.
2. Identify the contracts and invariants that define correctness.
3. Read the repository instructions and the maintained sources of truth.
4. Inspect relevant plans, commits, and current working-tree changes without
   reverting or overwriting unrelated user work.
5. Define objective in-scope and out-of-scope boundaries.

Audit against contracts and invariants, not subjective perfection. Do not turn
style preferences or speculative risks into findings.

## Perform one discovery pass

Perform one comprehensive discovery pass across the relevant surfaces before
starting broad fixes. Inspect, as applicable:

- plans, documented contracts, commits, and working-tree changes;
- backend and frontend implementations;
- authorization, security, and trust boundaries;
- parser, client, API, and schema contract parity;
- persistence, migration, lifecycle, concurrency, and recovery behavior;
- fallback, cancellation, error, and partial-failure paths;
- declared performance workloads and fixture validity;
- existing regression tests, integration tests, type checks, and CI gates.

Prefer parallel read-only checks when independent. Do not repeatedly alternate
between broad discovery and broad fixes.

## Enforce the evidence threshold

Accept a finding only when supported by at least one of:

- a reproducible failing test;
- a reproducible command or API request;
- deterministic benchmark evidence;
- a concrete execution path that demonstrates a contract violation.

Record exact file paths, line references, inputs, commands, outputs, and relevant
state. Do not report speculative concerns as findings.

For high-risk security, authorization, data-integrity, and performance findings,
obtain both when practical:

1. a focused regression test; and
2. an independent integration or adversarial verification.

Do not treat tests introduced together with the implementation as sufficient
evidence by themselves.

## Create and freeze the finding ledger

Create the ledger before starting fixes. Give every finding a stable ID such as
`SH-01` and include all fields below:

| Field | Required content |
| --- | --- |
| ID | Stable identifier |
| Severity | Critical, high, medium, or low |
| Invariant | Violated contract or required behavior |
| Evidence | Reproduction, failing test, request, benchmark, or concrete path |
| Affected surface | Files, endpoints, schemas, components, or workloads |
| Root cause | Technical reason for the failure |
| Acceptance criteria | Objective conditions required to close it |
| Verification | Commands or tests that prove closure |

Deduplicate by root cause. Count multiple symptoms as one finding when they
violate the same invariant, originate at the same missing boundary, require the
same root-cause correction, and share acceptance criteria. Keep findings separate
only when they can fail independently or require independent fixes.

Announce the complete ledger, then freeze:

- the audit scope;
- the finding IDs;
- the finding count;
- the one-to-one mapping between each finding, fix, and verification.

Never claim a finding count different from the number of listed IDs. A valid
discovery pass may freeze at zero findings.

## Classify post-freeze discoveries

Classify every issue noticed after the freeze as exactly one category:

### SAME_ROOT_CAUSE

Attach the new evidence to the existing finding, extend its regression coverage
when necessary, and do not increase the finding count.

### CAUSED_BY_PATCH

Treat the regression as blocking closure, associate it with the fix that caused
it, correct it, and rerun only the affected verification boundaries. Do not
restart discovery or increase the frozen finding count.

### OUT_OF_SCOPE

Record the pre-existing or unrelated issue separately as backlog. Do not include
it in the frozen count or fix it without explicit authorization.

If classification is genuinely ambiguous or would materially alter the agreed
scope, stop and ask the user before continuing.

## Fix each authorized finding

For each frozen finding, in order:

1. Reproduce the recorded failure independently.
2. Add a failing regression test when practical.
3. Apply the smallest complete root-cause fix.
4. Run the focused regression test.
5. Run directly affected integration, contract, schema, type, and frontend tests.
6. Record the evidence against the same finding ID.

Avoid unrelated refactors. Never weaken tests, fixtures, budgets, validation, or
baseline expectations merely to make a result appear green.

## Verify closure without re-auditing

Treat the post-fix pass as closure verification, not a new unrestricted audit.
Verify only:

- every frozen finding's acceptance criteria;
- boundaries directly affected by the fixes;
- touched backend/frontend, parser/API, and schema contracts;
- touched authorization, security, and data-integrity invariants;
- touched persistence, lifecycle, migration, and failure behavior;
- declared performance workloads and corpus contracts;
- regressions caused by the patch.

Do not silently broaden scope, change the finding count, restart discovery from
zero, or promote unrelated baseline failures into findings. Start a new broad
re-audit only when the user explicitly requests it.

## Validate performance evidence

Accept a performance result only when all applicable conditions hold:

- the fixture reaches the declared minimum corpus size;
- required real files and metadata are actually indexed;
- every managed workload executes;
- every workload meets its minimum-match contract;
- no endpoint or workload is silently skipped;
- errors and missing payloads fail the benchmark;
- warm-up and measured iterations are reported separately when applicable;
- the benchmark exits non-zero when a contract or budget fails.

Never treat an empty workload as a successful performance result unless
emptiness is the explicit contract under test.

## Separate baseline failures

Call a failure baseline only when evidence proves all of the following:

- it is outside the frozen scope;
- the current patch does not touch its execution path;
- it reproduces without the current patch or was already documented;
- it does not invalidate any frozen finding's acceptance criteria.

Report baseline failures separately. Never describe them as fixed, passed, or
part of the closed finding count.

## Apply the loop breaker

If closure verification fails twice for the same root cause:

1. Stop speculative fixes.
2. Summarize the invariant, evidence, attempted fixes, and remaining failure.
3. Identify missing information or architectural uncertainty.
4. Ask the user before continuing.

Do not continue an unbounded audit/fix loop.

## Enforce exit criteria

Close only when all applicable conditions are true:

- every frozen finding satisfies its acceptance criteria;
- every finding-specific regression test passes;
- relevant integration, API, schema, type, and frontend tests pass;
- relevant security and authorization boundaries pass adversarial checks;
- performance gates pass on a valid corpus;
- no in-scope regression introduced by the patch remains;
- the final closure report contains exactly the frozen finding IDs;
- remaining failures are explicitly proven out of scope.

Automate stable acceptance criteria through regression tests, integration tests,
schema checks, type checks, benchmark corpus assertions, CI budget gates, and
diff or formatting checks. Documentation alone is not verification evidence.

## Publish one final report and stop

For a read-only audit, report the frozen scope, exact finding count, full ledger,
verification evidence gathered, and separately identified out-of-scope notes.

For an audit with authorized fixes, publish exactly one row per frozen finding:

| ID | Root-cause fix | Regression evidence | Status |
| --- | --- | --- | --- |
| SH-01 | Summary of implemented correction | Test or command | Closed |

Make the number of rows exactly equal the frozen finding count. If the count is
zero, explicitly state that there are no finding rows. State explicitly whether
closure verification is complete. List proven baseline failures separately.

After publishing the report, stop. Do not begin another audit/fix cycle unless
the user explicitly requests it.
