# Software Assurance Policy

## Status and intent

This repository uses a **DO-178C-inspired** software-assurance baseline for change control, requirements traceability, verification, configuration management, and problem reporting. This policy improves engineering rigor; it does **not** claim FAA approval, airborne suitability, RTCA DO-178C compliance, or certification of this software.

No Design Assurance Level (DAL) is assigned unless a project-specific certification plan and system safety assessment say otherwise. Objectives such as verification independence, structural coverage, MC/DC, qualified tools, certification liaison, and formal life-cycle data are applied only when the documented project context requires them.

Normative certification work must use an authorized copy of RTCA DO-178C and applicable supplements. Public references include [FAA AC 20-115D](https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentID/1032046) and the [RTCA DO-178 family overview](https://www.rtca.org/do-178/).

## Solo-maintainer review model

This repository is maintained by a solo developer. Independent human approval is not required for each development pull request. The maintainer may self-review and merge after the required automated quality, test, security, traceability, and change-control gates pass.

Self-review and automated verification are not independent verification, and repository records must not represent them as such. Independent human review is deferred to the completed-project or first-stable-release readiness gate described in [`RELEASE-READINESS-REVIEW.md`](RELEASE-READINESS-REVIEW.md). A project-specific risk assessment may bring human review forward for a particular change.

## Change-control objectives

Every non-trivial change must provide reviewable evidence for:

1. **Source** — link the requirement, issue, vulnerability, or maintenance objective that motivates the change.
2. **Impact** — identify affected behavior, interfaces, data, safety/security properties, and compatibility.
3. **Implementation** — keep the change bounded, understandable, and under version control.
4. **Verification** — add or update tests at the lowest effective level and record commands/results.
5. **Traceability** — map the source to changed artifacts and verification evidence in the pull request.
6. **Review** — perform explicit self-review during development; obtain independent human review at the release-readiness gate or earlier when a documented project risk requires it.

Derived requirements and assumptions must be called out explicitly. A change must not silently weaken an existing safety, security, privacy, or compatibility constraint.

## Verification baseline

- CI must build or validate the project and execute its automated test suite.
- New behavior and corrected defects require regression tests unless the pull request documents why automation is impractical and supplies alternate evidence.
- Static analysis, dependency review, and CodeQL (for supported languages) are enforcement gates.
- Tests must be deterministic, isolated from production systems, and free of embedded credentials.
- Coverage claims must name the tool, scope, and measurement. A passing test count alone is not a coverage claim.
- Safety-critical projects must maintain project-specific plans for requirements, design, verification, configuration management, quality assurance, certification liaison, coverage objectives, and tool qualification.

## Configuration management and release evidence

The default branch is the controlled baseline. Dependencies and automation actions should be locked or pinned where practical. Release evidence should include the source revision, build/test logs, dependency inventory, known-problem disposition, artifact checksums or signatures when artifacts are distributed, and the completed human-review record required by the release-readiness gate.

GitHub issues are the problem-reporting system. Security defects must be reported privately according to `SECURITY.md`. Closed problems must record a disposition such as fixed, duplicate, deferred with rationale, or not planned with rationale.

## Exceptions

An exception must be documented in the pull request with scope, rationale, risk, compensating evidence, owner, and an expiration or review date. Permanent silent exceptions are not allowed.
