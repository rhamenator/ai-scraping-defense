# Alert Management System Flow

This document provides a visual representation of how the alert management system works.

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    User Initiates Script                    │
│  (run_alert_management.sh or manage_alerts_issues_prs.py)  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Prerequisites Check                        │
│  ✓ Python 3.7+    ✓ pip    ✓ Libraries    ✓ GitHub Token  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Configuration                            │
│  • Owner/Repo      • Dry-run/Live      • API Session       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Fetch Security Alerts                          │
│  ┌─────────────────┬──────────────────┬─────────────────┐  │
│  │  Code Scanning  │ Secret Scanning  │   Dependabot    │  │
│  └─────────────────┴──────────────────┴─────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│            Diagnose Error-State Alerts                      │
│  • Identify errors  • Map to remediation  • Log details    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│           Identify Duplicate Alerts                         │
│  • Normalize keys   • Calculate similarity  • Group items   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│            Consolidate Alerts                               │
│  • Keep primary     • Close duplicates    • Add notes       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Fetch Issues & PRs                             │
│  ┌─────────────────┬──────────────────────────────────┐    │
│  │  Open Issues    │     Open Pull Requests          │    │
│  └─────────────────┴──────────────────────────────────┘    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│       Identify Duplicate Issues/PRs                         │
│  • Normalize titles • Check similarity  • Group by content  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         Consolidate Issues/PRs                              │
│  • Keep oldest      • Close duplicates   • Add references   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Generate Report                                │
│  • Statistics       • Actions log       • Save to file      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Complete                                 │
│  Report: alert_management_report_YYYYMMDD_HHMMSS.txt       │
└─────────────────────────────────────────────────────────────┘
```

## Duplicate Detection Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  Item (Alert/Issue/PR)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Extract Essential Properties                   │
│  • Tool name        • Rule ID         • Severity            │
│  • Description      • Title           • Body content        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Normalize Data                             │
│  • Remove prefixes ([SECURITY], fix:, etc.)                 │
│  • Convert to lowercase                                     │
│  • Create normalized key                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Group by Normalized Key                        │
│  Key = "tool:rule:severity:description[:100]"               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│      Calculate Content Similarity (if needed)               │
│  SequenceMatcher.ratio() > 0.8 (80% threshold)              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Create Duplicate Groups                        │
│  Only groups with 2+ items                                  │
└─────────────────────────────────────────────────────────────┘
```

## Consolidation Process

```
┌─────────────────────────────────────────────────────────────┐
│           Duplicate Group (N items)                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│          Sort by Number (Ascending)                         │
│  Oldest item (lowest number) becomes primary                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│       Collect All Affected Files/Locations                  │
│  Aggregate from all items in the group                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              For Each Duplicate Item:                       │
│  1. Create closure comment with:                            │
│     - Reference to primary item                             │
│     - List of all affected files                            │
│  2. Close item with appropriate state:                      │
│     - Alerts: dismissed/resolved                            │
│     - Issues: closed (not_planned)                          │
│     - PRs: closed                                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│               Update Statistics                             │
│  • alerts_closed    • issues_closed    • prs_closed         │
│  • alerts_consolidated                                      │
└─────────────────────────────────────────────────────────────┘
```

## Error Diagnosis Flow

```
┌─────────────────────────────────────────────────────────────┐
│                   Alert with State                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│        Check for Error Keywords                             │
│  In: state, state_reason fields                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
                  Error Found?
                       │
        ┌──────────────┴──────────────┐
        │ No                     Yes   │
        ▼                              ▼
    Continue              ┌─────────────────────────────────┐
                          │  Map Error to Remediation       │
                          │  • stale                        │
                          │  • timeout                      │
                          │  • analysis_error               │
                          │  • insufficient_permissions     │
                          │  • configuration_error          │
                          └──────────────┬──────────────────┘
                                         │
                                         ▼
                          ┌─────────────────────────────────┐
                          │  Log Diagnosis & Remediation    │
                          │  errors_diagnosed++             │
                          └─────────────────────────────────┘
```

## Decision Tree: When Items Are Duplicates

```
                        Start
                          │
                          ▼
           ┌──────────────────────────────┐
           │  Same essential properties?  │
           │  (tool:rule:severity:desc)   │
           └──────────┬───────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │ No                   Yes  │
        ▼                           ▼
    Different        ┌──────────────────────────┐
    Items            │  Same title (normalized)?│
                     └──────────┬───────────────┘
                                │
                  ┌─────────────┴─────────────┐
                  │ No                   Yes  │
                  ▼                           ▼
              Different      ┌────────────────────────┐
              Items          │ Content similarity >80%?│
                             └──────────┬─────────────┘
                                        │
                          ┌─────────────┴──────────────┐
                          │ No                    Yes  │
                          ▼                            ▼
                      Different              ┌─────────────────┐
                      Items                  │   DUPLICATES!   │
                                             │  Consolidate    │
                                             └─────────────────┘
```

## Modes of Operation

### Dry-Run Mode
```
User Action → Check Prerequisites → Fetch Data → Analyze →
Generate Report → Display "DRY RUN" → No Changes Made
```

### Live Mode
```
User Action → Check Prerequisites → Fetch Data → Analyze →
Close Duplicates → Update Items → Generate Report →
Display "LIVE" → Changes Applied
```

## API Interaction Flow

```
┌────────────────────────────────────────────────────────────┐
│                     Script                                 │
└──────────────────────┬─────────────────────────────────────┘
                       │ HTTPS Request
                       │ Authorization: token GITHUB_TOKEN
                       ▼
┌────────────────────────────────────────────────────────────┐
│                  GitHub API                                │
│  • GET  /repos/{owner}/{repo}/code-scanning/alerts        │
│  • GET  /repos/{owner}/{repo}/secret-scanning/alerts      │
│  • GET  /repos/{owner}/{repo}/dependabot/alerts           │
│  • GET  /repos/{owner}/{repo}/issues                      │
│  • GET  /repos/{owner}/{repo}/pulls                       │
│  • PATCH /repos/{owner}/{repo}/code-scanning/alerts/{n}   │
│  • PATCH /repos/{owner}/{repo}/secret-scanning/alerts/{n} │
│  • PATCH /repos/{owner}/{repo}/dependabot/alerts/{n}      │
└──────────────────────┬─────────────────────────────────────┘
                       │ JSON Response
                       ▼
┌────────────────────────────────────────────────────────────┐
│                    Script                                  │
│  • Parse data      • Process items     • Take actions     │
└────────────────────────────────────────────────────────────┘
```

## Error Handling Flow

```
                    API Request
                         │
                         ▼
                  Success (200-299)?
                         │
        ┌────────────────┴────────────────┐
        │ Yes                        No   │
        ▼                                 ▼
    Process Data            ┌─────────────────────────┐
                            │  Check Error Code       │
                            └──────────┬──────────────┘
                                       │
                      ┌────────────────┼────────────────┐
                      │                │                │
                      ▼                ▼                ▼
                   403 Forbidden    404 Not Found   Other
                      │                │                │
                      ▼                ▼                ▼
            Log: Insufficient    Log: Feature     Log: Error
            permissions          not enabled      details
                      │                │                │
                      └────────────────┴────────────────┘
                                       │
                                       ▼
                              Continue Processing
                            (Don't fail entirely)
```

## Report Structure

```
┌────────────────────────────────────────────────────────────┐
│                        REPORT                              │
├────────────────────────────────────────────────────────────┤
│  Header                                                    │
│  • Repository: owner/repo                                  │
│  • Timestamp: ISO 8601                                     │
│  • Mode: DRY RUN / LIVE                                    │
├────────────────────────────────────────────────────────────┤
│  Statistics                                                │
│  • Alerts Fetched: N                                       │
│  • Alerts Reopened: N                                      │
│  • Alerts Consolidated: N                                  │
│  • Alerts Closed: N                                        │
│  • Issues Created: N                                       │
│  • Issues Closed: N                                        │
│  • Issues Consolidated: N                                  │
│  • PRs Closed: N                                           │
│  • PRs Consolidated: N                                     │
│  • Errors Diagnosed: N                                     │
├────────────────────────────────────────────────────────────┤
│  Actions Log (Timestamped)                                 │
│  [2025-11-22T20:51:28] START: ...                         │
│  [2025-11-22T20:51:29] FETCH: ...                         │
│  [2025-11-22T20:51:30] ANALYSIS: ...                      │
│  [2025-11-22T20:51:31] CONSOLIDATE: ...                   │
│  [2025-11-22T20:51:32] DETAIL: ...                        │
│  ...                                                       │
└────────────────────────────────────────────────────────────┘
```

## Integration Points

### GitHub Actions
```
Workflow Trigger (schedule/manual)
         │
         ▼
Checkout Repository
         │
         ▼
Setup Python & Install Dependencies
         │
         ▼
Run Script (with GITHUB_TOKEN)
         │
         ▼
Upload Report as Artifact
```

### Command Line
```
User → Shell Script → Prerequisites Check → Python Script → Report
```

### Direct Python
```
User → Python Script → Report
```

## Key Design Principles

1. **Idempotent**: Running multiple times produces consistent results
2. **Safe**: Dry-run mode prevents accidental changes
3. **Transparent**: Every action is logged with details
4. **Robust**: Handles errors gracefully, doesn't fail entirely
5. **Flexible**: Customizable thresholds and filters
6. **Comprehensive**: Addresses all alert types and item types
7. **User-friendly**: Clear messages and helpful errors

## Performance Characteristics

- **API Calls**: Paginated (100 items per page) to minimize requests
- **Memory**: Processes items in groups, not all at once
- **Speed**: Depends on API response time and number of items
- **Rate Limits**: Respects GitHub API rate limits (5000/hour with token)

## Security Considerations

- **Token Security**: Token never logged or displayed
- **Read-Only Operations**: Only writes when explicitly needed
- **Audit Trail**: All actions logged for review
- **No Data Loss**: Items closed, not deleted (can be reopened)
- **Permission Model**: Requires appropriate scopes, fails gracefully if missing
