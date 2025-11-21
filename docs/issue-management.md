# Issue Management

## Reopen Unlinked Issues

The `scripts/reopen_unlinked_issues.py` script ensures that issues are not prematurely closed without an associated merged pull request.

### Purpose

This script helps maintain issue tracking integrity by:

1. Identifying closed issues that lack a merged PR
2. Automatically reopening such issues
3. Adding a comment explaining why the issue was reopened

### Usage

#### Command Line

```bash
# Dry run (recommended first)
python scripts/reopen_unlinked_issues.py --dry-run

# Actually reopen issues
python scripts/reopen_unlinked_issues.py

# With custom limit
python scripts/reopen_unlinked_issues.py --limit 1000

# With debug logging
python scripts/reopen_unlinked_issues.py --log-level DEBUG
```

#### GitHub Actions Workflow

The workflow runs weekly on Mondays at 9 AM UTC, or can be triggered manually:

1. Go to Actions → "Reopen Issues Without Merged PRs"
2. Click "Run workflow"
3. Choose options:
   - **dry_run**: Whether to actually make changes (default: true)
   - **limit**: Maximum number of issues/PRs to check (default: 500)

### How It Works

1. **Fetch Data**: Retrieves closed issues and all pull requests from GitHub
2. **Build Mappings**: Creates relationships between PRs and the issues they reference
3. **Identify Issues**: Finds closed issues without a merged PR
4. **Reopen Issues**: For each identified issue:
   - Reopens the issue
   - Adds a comment explaining the reason
5. **Rate Limiting**: Includes automatic delays to respect GitHub API limits

### Issue Reference Detection

The script recognizes several patterns for linking PRs to issues:

- `Fixes #123`
- `Closes #456`
- `Resolves #789`
- `Fix #123`, `Close #456`, `Resolve #789`
- `#123` (standalone references)

These patterns work in:
- PR titles
- PR descriptions
- GitHub's native `closingIssuesReferences` (when using keywords like "fixes")

### Requirements

- GitHub CLI (`gh`) installed and authenticated
- `GITHUB_TOKEN` environment variable with `repo` scope
- Python 3.8 or higher

### Configuration

The script uses these defaults:

- `DEFAULT_LIMIT`: 500 issues/PRs to check
- `RATE_LIMIT_SLEEP`: 0.5 seconds between API calls

### Testing

Run the unit tests:

```bash
python -m pytest test/scripts/test_reopen_unlinked_issues.py -v
```

### Scheduled Execution

The workflow is scheduled to run weekly on Mondays at 9 AM UTC. By default, scheduled runs use dry-run mode to prevent accidental changes. To enable actual reopening on schedule, modify the workflow file.

### Monitoring

Check the workflow logs for:
- Number of closed issues fetched
- Number of PRs analyzed
- Issues identified for reopening
- Successful reopen operations
- Any errors encountered

### Best Practices

1. Always run with `--dry-run` first to preview changes
2. Review the logs before running without dry-run
3. Set appropriate `--limit` based on repository size
4. Monitor for false positives (issues that should remain closed)
5. Use `--log-level DEBUG` to troubleshoot unexpected behavior

### Troubleshooting

**Issue: "GitHub CLI not found"**
- Install GitHub CLI: https://cli.github.com/
- Ensure it's in your PATH

**Issue: "Authentication failed"**
- Run `gh auth login` to authenticate
- Or set `GITHUB_TOKEN` environment variable

**Issue: "Too many API requests"**
- Increase `RATE_LIMIT_SLEEP` in the script
- Reduce `--limit` to process fewer items
- Wait for rate limit to reset (check with `gh api rate_limit`)

**Issue: "False positives"**
- Review the PR reference patterns
- Check if issues have PRs not detected by the script
- Manually close issues that shouldn't be reopened
