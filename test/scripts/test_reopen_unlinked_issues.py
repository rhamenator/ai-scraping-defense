import unittest
from unittest.mock import MagicMock, patch

from scripts import reopen_unlinked_issues


class TestReopenUnlinkedIssues(unittest.TestCase):
    def test_extract_issue_numbers_from_text(self):
        """Test extracting issue numbers from various text patterns."""
        text = "Fixes #123 and closes #456. Also see #789."
        result = reopen_unlinked_issues.extract_issue_numbers_from_text(text)
        self.assertEqual(result, {123, 456, 789})

    def test_extract_issue_numbers_case_insensitive(self):
        """Test that extraction is case insensitive."""
        text = "FIXES #100, Closes #200, resolves #300"
        result = reopen_unlinked_issues.extract_issue_numbers_from_text(text)
        self.assertEqual(result, {100, 200, 300})

    def test_extract_issue_numbers_empty(self):
        """Test empty text returns empty set."""
        result = reopen_unlinked_issues.extract_issue_numbers_from_text("")
        self.assertEqual(result, set())

    def test_extract_issue_numbers_none(self):
        """Test None text returns empty set."""
        result = reopen_unlinked_issues.extract_issue_numbers_from_text(None)
        self.assertEqual(result, set())

    def test_build_pr_to_issues_map(self):
        """Test building PR to issues mapping."""
        prs = [
            {
                "number": 1,
                "title": "Fix bug",
                "body": "Fixes #10 and #20",
                "closingIssuesReferences": {"nodes": []},
            },
            {
                "number": 2,
                "title": "Close #30",
                "body": "Resolves #40",
                "closingIssuesReferences": {"nodes": [{"number": 50}]},
            },
        ]
        result = reopen_unlinked_issues.build_pr_to_issues_map(prs)
        self.assertIn(1, result)
        self.assertEqual(result[1], {10, 20})
        self.assertIn(2, result)
        self.assertEqual(result[2], {30, 40, 50})

    def test_build_issue_to_prs_map(self):
        """Test building issue to PRs mapping."""
        pr_to_issues = {1: {10, 20}, 2: {20, 30}}
        prs = [
            {
                "number": 1,
                "title": "PR 1",
                "merged": True,
                "mergedAt": "2023-01-01T00:00:00Z",
            },
            {
                "number": 2,
                "title": "PR 2",
                "merged": False,
                "mergedAt": None,
            },
        ]
        result = reopen_unlinked_issues.build_issue_to_prs_map(pr_to_issues, prs)
        self.assertIn(10, result)
        self.assertEqual(len(result[10]), 1)
        self.assertEqual(result[10][0]["number"], 1)
        self.assertTrue(result[10][0]["merged"])

        self.assertIn(20, result)
        self.assertEqual(len(result[20]), 2)

        self.assertIn(30, result)
        self.assertEqual(len(result[30]), 1)
        self.assertEqual(result[30][0]["number"], 2)
        self.assertFalse(result[30][0]["merged"])

    def test_has_merged_pr_true(self):
        """Test checking if issue has merged PR."""
        issue_to_prs = {10: [{"number": 1, "merged": True, "title": "PR 1"}]}
        result = reopen_unlinked_issues.has_merged_pr(10, issue_to_prs)
        self.assertTrue(result)

    def test_has_merged_pr_false(self):
        """Test checking if issue has no merged PR."""
        issue_to_prs = {10: [{"number": 1, "merged": False, "title": "PR 1"}]}
        result = reopen_unlinked_issues.has_merged_pr(10, issue_to_prs)
        self.assertFalse(result)

    def test_has_merged_pr_no_prs(self):
        """Test checking if issue has no PRs."""
        issue_to_prs = {}
        result = reopen_unlinked_issues.has_merged_pr(10, issue_to_prs)
        self.assertFalse(result)

    def test_has_merged_pr_mixed(self):
        """Test checking if issue has at least one merged PR among many."""
        issue_to_prs = {
            10: [
                {"number": 1, "merged": False, "title": "PR 1"},
                {"number": 2, "merged": True, "title": "PR 2"},
                {"number": 3, "merged": False, "title": "PR 3"},
            ]
        }
        result = reopen_unlinked_issues.has_merged_pr(10, issue_to_prs)
        self.assertTrue(result)

    @patch("scripts.reopen_unlinked_issues.run_gh_command")
    def test_reopen_issue_dry_run(self, mock_gh_command):
        """Test reopening issue in dry-run mode."""
        result = reopen_unlinked_issues.reopen_issue(123, "Test reason", dry_run=True)
        self.assertTrue(result)
        mock_gh_command.assert_not_called()

    @patch("scripts.reopen_unlinked_issues.run_gh_command")
    def test_reopen_issue_success(self, mock_gh_command):
        """Test successfully reopening issue."""
        mock_gh_command.return_value = MagicMock()
        result = reopen_unlinked_issues.reopen_issue(123, "Test reason", dry_run=False)
        self.assertTrue(result)
        self.assertEqual(mock_gh_command.call_count, 2)


if __name__ == "__main__":
    unittest.main()
