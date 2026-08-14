# Release-Readiness Human Review

## Purpose

Independent human review is a release-readiness activity for this solo-maintained repository, not a required approval on every development pull request.

Complete this review before either:

- the first stable release;
- declaring the project complete for its intended scope; or
- representing the software as independently reviewed for downstream or production use.

Until then, development records may cite self-review and automated verification but must state that independent human review is pending.

## Review packet

Provide the reviewer with:

1. the intended scope, requirements, assumptions, and documented exclusions;
2. the architecture, trust boundaries, interfaces, and important design decisions;
3. traceability from requirements or objectives to implementation and verification;
4. automated and manual test evidence, coverage claims, and known test limitations;
5. security analysis, dependency state, static-analysis results, and unresolved alerts;
6. known defects, deferred work, compatibility constraints, and residual risks;
7. reproducible build and release instructions plus artifact provenance; and
8. the exact source revision and release candidate being reviewed.

## Review record

Archive the following in a release issue, release notes, or another durable repository record:

- reviewer name and relevant qualifications;
- review date, scope, source revision, and release candidate;
- findings and their severity;
- resolution or explicit risk acceptance for each finding;
- limitations of the review; and
- the final recommendation: approved, approved with limitations, or not approved.

Do not claim independent review while blocking high-severity findings remain unresolved or without an explicit, documented risk disposition.
