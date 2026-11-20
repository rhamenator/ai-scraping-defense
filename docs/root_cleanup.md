# Root cleanup inventory

Issue #1930 reviewed the contents and repository references for each candidate
before moving or deleting it. This cleanup does not change licensing terms.

| Original root file | Decision and checked use |
|---|---|
| `ALERT_MANAGEMENT_SUMMARY.md` | Preserve under `docs/archive/root-notes/`; historical implementation notes refer to the quick start. |
| `QUICK_START_ALERT_MANAGEMENT.md` | Preserve in the same archive; update the README and active alert guide links. |
| `START_HERE_ALERT_MANAGEMENT.md` | Preserve in the same archive; fix its links to active docs and scripts. |
| `CODE_SCANNING_ISSUES.md` | Preserve the 38-finding historical report in the archive. The generator now writes to ignored `reports/security/`. |
| `SECURITY_SUMMARY.md` | Preserve dated resolution notes alongside the report they describe. |
| `WORKFLOW_FIXES_SUMMARY.md` | Preserve the dated 2025 workflow investigation as historical context. |
| `WORKFLOW_INVESTIGATION_SUMMARY.md` | Preserve the companion 2025 investigation in the same archive. |
| `ISSUES_TO_CREATE.md` | Preserve historical issue proposals in the archive; not an authoritative current backlog. |
| `CHAT_RELEVANT_PLAYBOOK.md` | Preserve operational/session context in the archive beside its handoff. |
| `WINDOWS_HANDOFF.md` | Preserve the historical handoff; canonical deployment guidance remains in the active docs. |
| `problem_file_map.json` | Move unchanged to `docs/triage/`. Active generation, loading, metadata synchronization, issue/PR and milestone scripts use it; update all default paths and its existing regression test. |
| `issue_milestone_assignments.json` | Move unchanged to `docs/triage/`; update the categorizer and assignment-applier defaults. |
| `compliance_problems.json` | Preserve unchanged in `docs/triage/`: the generator discovers it dynamically through its JSON filename filter. Update the scan directory and joined input path; test that catalogue loading still works. |
| `problems.txt` | Remove stale editor diagnostics containing workstation paths; no executable consumer found. |
| `models.json` | Remove unused old model-list API snapshot; no runtime/script consumer found. |
| `# setup.sh.txt` | Remove unreferenced six-line setup scratch file; active setup instructions and scripts already cover dependency installation. |
| `license_summary.md` | Move to `docs/`; update links and MkDocs navigation. Only the relative LICENSE link changes; terms remain unchanged. |
| `AI_Scraping_Defense_System_Presentation.pptx` | Preserve unchanged under `docs/presentations/`; inspected the eleven slides and linked it as historical material. |
| `ai-scraping-defense.sln` | Keep: `.github/workflows/codeql.yml` restores/builds the embedded IIS module through this solution. |
| `rust-toolchain.toml` | Keep: embedded Rust crates and their CI still use the pinned toolchain. |
| `__init__.py` | Remove empty root marker; packaging explicitly includes `src*` and tests use those packages. Targeted tests confirm discovery still works. |

[The documentation index](index.md#historical-notes-and-maintenance-data) links
the preserved notes and data. Generated editor/API snapshots are root-anchored in
`.gitignore`; new code-scanning reports use the existing ignored `reports/` tree.
The problem-map database remains a local ignored database, independent of where
the tracked JSON input lives. Run maintenance scripts from the repository root,
as before.
