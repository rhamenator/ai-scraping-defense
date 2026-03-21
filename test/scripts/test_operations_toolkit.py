import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

from scripts import operations_toolkit


class TestOperationsToolkit(unittest.TestCase):
    def test_run_command_dry_run_skips_subprocess(self):
        with patch("scripts.operations_toolkit.subprocess.run") as mock_run:
            result = operations_toolkit.run_command(
                ["kubectl", "get", "pods"], execute=False
            )

        mock_run.assert_not_called()
        self.assertEqual(result.command, ["kubectl", "get", "pods"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_run_command_executes_without_shell(self):
        completed = MagicMock(returncode=0, stdout="ok", stderr="")

        with patch(
            "scripts.operations_toolkit.subprocess.run", return_value=completed
        ) as mock_run:
            result = operations_toolkit.run_command(
                ["kubectl", "get", "pods"], execute=True
            )

        mock_run.assert_called_once_with(
            ["kubectl", "get", "pods"],
            cwd=None,
            check=False,
            capture_output=True,
            text=True,
            env=ANY,
        )
        self.assertEqual(result.command, ["kubectl", "get", "pods"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok")
        self.assertEqual(result.stderr, "")

    def test_run_command_raises_on_command_failure(self):
        completed = MagicMock(returncode=2, stdout="", stderr="boom")

        with patch("scripts.operations_toolkit.subprocess.run", return_value=completed):
            with self.assertRaises(operations_toolkit.CommandExecutionError) as exc:
                operations_toolkit.run_command(["kubectl", "get", "pods"], execute=True)

        self.assertEqual(exc.exception.result.returncode, 2)

    def test_run_command_sanitizes_stderr_before_logging_and_raising(self):
        completed = MagicMock(
            returncode=2,
            stdout="",
            stderr=(
                "failed for postgres://user:super-secret@db.example.com:5432/app "
                "token ghp_1234567890abcdefghijklmnopqrstuvwxyz"
            ),
        )

        with patch(
            "scripts.operations_toolkit.subprocess.run", return_value=completed
        ), patch.object(operations_toolkit.LOG, "error") as mock_error:
            with self.assertRaises(operations_toolkit.CommandExecutionError) as exc:
                operations_toolkit.run_command(["kubectl", "get", "pods"], execute=True)

        self.assertNotIn("super-secret", exc.exception.result.stderr)
        self.assertNotIn(
            "ghp_1234567890abcdefghijklmnopqrstuvwxyz", exc.exception.result.stderr
        )
        logged_messages = "\n".join(str(call) for call in mock_error.call_args_list)
        self.assertNotIn("super-secret", logged_messages)

    def test_run_command_wraps_missing_binary_errors(self):
        with patch(
            "scripts.operations_toolkit.subprocess.run",
            side_effect=FileNotFoundError("pg_dump not found"),
        ):
            with self.assertRaises(operations_toolkit.CommandExecutionError) as exc:
                operations_toolkit.run_command(["pg_dump", "--version"], execute=True)

        self.assertEqual(exc.exception.result.returncode, 127)
        self.assertIn("pg_dump not found", exc.exception.result.stderr)

    def test_command_execution_error_redacts_credentials_in_message(self):
        result = operations_toolkit.CommandResult(
            command=[
                "pg_dump",
                "--dbname",
                "postgres://user:super-secret@db.example.com:5432/app",
            ],
            returncode=2,
            stdout="",
            stderr="boom",
        )

        message = str(operations_toolkit.CommandExecutionError(result))

        self.assertNotIn("super-secret", message)
        self.assertIn("[REDACTED]@db.example.com:5432/app", message)

    def test_backup_returns_timestamped_path(self):
        """Test that backup() returns the timestamped directory path."""
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                destination=tmp,
                postgres_url="postgres://test",
                redis_url="redis://test",
                kube_context="test-context",
                execute=False,
            )

            with patch("scripts.operations_toolkit.run_command") as mock_run:
                mock_run.return_value = operations_toolkit.CommandResult(
                    command=[], returncode=0, stdout="", stderr=""
                )
                result_path = operations_toolkit.backup(args)

                # Verify the returned path is under the destination
                self.assertTrue(str(result_path).startswith(tmp))
                # Verify the path includes a timestamp subdirectory
                self.assertNotEqual(str(result_path), tmp)
                # Verify the path exists (was created by ensure_directory)
                self.assertTrue(result_path.exists())

    def test_backup_execute_writes_manifest_and_secures_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                destination=tmp,
                postgres_url="postgres://test",
                redis_url="redis://test",
                kube_context="test-context",
                execute=True,
            )

            def fake_run(command, *, execute, cwd=None, env=None):
                if command[0] == "pg_dump":
                    Path(command[-1]).write_text("pgdump", encoding="utf-8")
                elif command[0] == "redis-cli":
                    Path(command[-1]).write_bytes(b"redis")
                elif command[0] == "kubectl":
                    return operations_toolkit.CommandResult(
                        command=list(command),
                        returncode=0,
                        stdout=json.dumps({"items": []}),
                        stderr="",
                    )
                return operations_toolkit.CommandResult(
                    command=list(command), returncode=0, stdout="", stderr=""
                )

            with patch("scripts.operations_toolkit.run_command", side_effect=fake_run):
                result_path = operations_toolkit.backup(args)

            manifest = json.loads(
                (result_path / "backup_manifest.json").read_text(encoding="utf-8")
            )
            self.assertIn("artifacts", manifest)
            self.assertTrue(manifest["artifacts"]["postgres_dump"]["exists"])
            self.assertTrue(manifest["artifacts"]["redis_dump"]["exists"])
            self.assertTrue(manifest["artifacts"]["cluster_state"]["exists"])
            self.assertEqual(
                manifest["artifacts"]["postgres_dump"]["path"], "postgres.sql"
            )

            if os.name != "nt":
                self.assertEqual(
                    (result_path / "backup_manifest.json").stat().st_mode & 0o777,
                    0o600,
                )
                self.assertEqual(result_path.stat().st_mode & 0o777, 0o700)

    def test_backup_uses_env_vars_for_postgres_and_redis_passwords(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                destination=tmp,
                postgres_url="postgres://user:secret@db.example.com:5432/app",
                redis_url="redis://bot:cache-secret@cache.example.com:6379/0",
                kube_context="test-context",
                execute=False,
            )

            with patch("scripts.operations_toolkit.run_command") as mock_run:
                mock_run.return_value = operations_toolkit.CommandResult(
                    command=[], returncode=0, stdout="", stderr=""
                )
                operations_toolkit.backup(args)

        pg_call = mock_run.call_args_list[0]
        redis_call = mock_run.call_args_list[1]

        self.assertNotIn("secret", " ".join(pg_call.args[0]))
        self.assertEqual(pg_call.kwargs["env"]["PGPASSWORD"], "secret")
        self.assertIn("postgres://user@db.example.com:5432/app", pg_call.args[0])

        self.assertNotIn("cache-secret", " ".join(redis_call.args[0]))
        self.assertEqual(redis_call.kwargs["env"]["REDISCLI_AUTH"], "cache-secret")
        self.assertIn("--user", redis_call.args[0])
        self.assertIn("redis://bot@cache.example.com:6379/0", redis_call.args[0])

    def test_backup_preserves_empty_password_auth_env_vars(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                destination=tmp,
                postgres_url="postgres://user:@db.example.com:5432/app",
                redis_url="redis://bot:@cache.example.com:6379/0",
                kube_context="test-context",
                execute=False,
            )

            with patch("scripts.operations_toolkit.run_command") as mock_run:
                mock_run.return_value = operations_toolkit.CommandResult(
                    command=[], returncode=0, stdout="", stderr=""
                )
                operations_toolkit.backup(args)

        pg_call = mock_run.call_args_list[0]
        redis_call = mock_run.call_args_list[1]

        self.assertIn("PGPASSWORD", pg_call.kwargs["env"])
        self.assertEqual(pg_call.kwargs["env"]["PGPASSWORD"], "")
        self.assertIn("REDISCLI_AUTH", redis_call.kwargs["env"])
        self.assertEqual(redis_call.kwargs["env"]["REDISCLI_AUTH"], "")

    def test_backup_rejects_invalid_kubectl_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                destination=tmp,
                postgres_url="postgres://test",
                redis_url="redis://test",
                kube_context="test-context",
                execute=True,
            )

            responses = [
                operations_toolkit.CommandResult([], 0, "", ""),
                operations_toolkit.CommandResult([], 0, "", ""),
                operations_toolkit.CommandResult([], 0, "not-json", ""),
            ]

            with patch("scripts.operations_toolkit.run_command", side_effect=responses):
                with self.assertRaises(SystemExit) as exc:
                    operations_toolkit.backup(args)

        self.assertIn("invalid json", str(exc.exception).lower())

    def test_restore_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp)
            postgres_file = backup_dir / "postgres.sql"
            redis_file = backup_dir / "redis.rdb"
            state_file = backup_dir / "cluster_state.json"
            postgres_file.write_text("postgres", encoding="utf-8")
            redis_file.write_bytes(b"redis")
            state_file.write_text("{}", encoding="utf-8")
            manifest = operations_toolkit._build_backup_manifest(
                postgres_file=postgres_file,
                redis_file=redis_file,
                state_file=state_file,
                kube_context="test-context",
            )
            (backup_dir / "backup_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            postgres_file.write_text("tampered", encoding="utf-8")

            args = argparse.Namespace(
                source=str(backup_dir),
                postgres_url="postgres://test",
                redis_url="redis://test",
                redis_data_dir="/var/lib/redis",
                redis_host="localhost",
                execute=False,
            )

            with self.assertRaises(SystemExit):
                operations_toolkit.restore(args)

    def test_restore_rejects_manifest_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp)
            manifest = {
                "generated_at": "2026-03-17T00:00:00Z",
                "kube_context": "test-context",
                "artifacts": {
                    "postgres_dump": {
                        "path": "../outside.sql",
                        "exists": False,
                        "sha256": None,
                    }
                },
            }
            (backup_dir / "backup_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            args = argparse.Namespace(
                source=str(backup_dir),
                postgres_url="postgres://test",
                redis_url="redis://test",
                redis_data_dir="/var/lib/redis",
                redis_host="localhost",
                execute=False,
            )

            with self.assertRaises(SystemExit):
                operations_toolkit.restore(args)

    def test_restore_rejects_invalid_manifest_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp)
            (backup_dir / "backup_manifest.json").write_text(
                "{not-json", encoding="utf-8"
            )

            args = argparse.Namespace(
                source=str(backup_dir),
                postgres_url="postgres://test",
                redis_url="redis://test",
                redis_data_dir="/var/lib/redis",
                redis_host="localhost",
                execute=False,
            )

            with self.assertRaises(SystemExit):
                operations_toolkit.restore(args)

    def test_disaster_recovery_drill_uses_correct_backup_path(self):
        """Test that disaster_recovery_drill passes the correct timestamped path to restore."""
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                environment="staging",
                drill_backup_dir=tmp,
                postgres_url="postgres://test",
                redis_url="redis://test",
                kube_context="test-context",
                redis_data_dir="/var/lib/redis",
                redis_host="localhost",
                execute=False,
            )

            with patch("scripts.operations_toolkit.run_command") as mock_run:
                mock_run.return_value = operations_toolkit.CommandResult(
                    command=[], returncode=0, stdout="", stderr=""
                )

                with patch("scripts.operations_toolkit.restore") as mock_restore:
                    operations_toolkit.disaster_recovery_drill(args)

                    # Verify restore was called
                    self.assertEqual(mock_restore.call_count, 1)

                    # Get the arguments passed to restore
                    restore_args = mock_restore.call_args[0][0]

                    # Verify the source path is a timestamped subdirectory, not the parent
                    self.assertTrue(restore_args.source.startswith(tmp))
                    self.assertNotEqual(restore_args.source, tmp)

                    # Verify required redis parameters are present
                    self.assertEqual(restore_args.redis_data_dir, "/var/lib/redis")
                    self.assertEqual(restore_args.redis_host, "localhost")

                    # Verify other parameters are passed correctly
                    self.assertEqual(restore_args.postgres_url, "postgres://test")
                    self.assertEqual(restore_args.redis_url, "redis://test")
                    self.assertFalse(restore_args.execute)

    def test_disaster_recovery_drill_namespace_no_duplicates(self):
        """Test that the restore Namespace has no duplicate parameters."""
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                environment="staging",
                drill_backup_dir=tmp,
                postgres_url="postgres://test",
                redis_url="redis://test",
                kube_context="test-context",
                redis_data_dir="/var/lib/redis",
                redis_host="localhost",
                execute=False,
            )

            with patch("scripts.operations_toolkit.run_command") as mock_run:
                mock_run.return_value = operations_toolkit.CommandResult(
                    command=[], returncode=0, stdout="", stderr=""
                )

                with patch("scripts.operations_toolkit.restore") as mock_restore:
                    operations_toolkit.disaster_recovery_drill(args)

                    # Get the arguments passed to restore
                    restore_args = mock_restore.call_args[0][0]

                    # Get all attribute names from the Namespace
                    attrs = vars(restore_args)

                    # Verify each required attribute exists exactly once
                    required_attrs = [
                        "source",
                        "postgres_url",
                        "redis_url",
                        "redis_data_dir",
                        "redis_host",
                        "execute",
                    ]
                    for attr in required_attrs:
                        self.assertIn(
                            attr, attrs, f"Missing required attribute: {attr}"
                        )

    def test_deploy_rejects_missing_default_paths(self):
        args = argparse.Namespace(
            environment="staging",
            terraform_dir="infrastructure/terraform",
            ansible_inventory="ansible/inventory.yaml",
            ansible_playbook="ansible/site.yaml",
            kube_context="test-context",
            kustomize_dir="kubernetes/overlays/{environment}",
            execute=False,
        )

        with self.assertRaises(SystemExit) as exc:
            operations_toolkit.deploy(args)

        self.assertIn("missing path", str(exc.exception).lower())

    def test_deploy_rejects_invalid_kustomize_template(self):
        args = argparse.Namespace(
            environment="staging",
            terraform_dir="infrastructure/terraform",
            ansible_inventory="ansible/inventory.yaml",
            ansible_playbook="ansible/site.yaml",
            kube_context="test-context",
            kustomize_dir="kubernetes/{missing}",
            execute=False,
        )

        with self.assertRaises(SystemExit) as exc:
            operations_toolkit.deploy(args)

        self.assertIn(
            "invalid kustomize directory template", str(exc.exception).lower()
        )

    def test_restore_dry_run_logs_hypothetical_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp)
            (backup_dir / "postgres.sql").write_text("postgres", encoding="utf-8")
            (backup_dir / "redis.rdb").write_bytes(b"redis")

            args = argparse.Namespace(
                source=str(backup_dir),
                postgres_url="postgres://test",
                redis_url="redis://test",
                redis_data_dir="/var/lib/redis",
                redis_host="localhost",
                execute=False,
            )

            with patch("scripts.operations_toolkit.run_command") as mock_run:
                mock_run.return_value = operations_toolkit.CommandResult(
                    command=[], returncode=0, stdout="", stderr=""
                )
                with self.assertLogs(
                    "scripts.operations_toolkit", level="INFO"
                ) as logs:
                    operations_toolkit.restore(args)

        log_text = "\n".join(logs.output)
        self.assertIn("[dry-run] Would copy Redis dump", log_text)
        self.assertIn("[dry-run] Restore actions validated", log_text)
        self.assertNotIn("Redis dump copied.", log_text)

    def test_main_returns_non_zero_for_command_failures(self):
        args = argparse.Namespace(func=MagicMock())
        args.func.side_effect = operations_toolkit.CommandExecutionError(
            operations_toolkit.CommandResult(
                command=["terraform", "apply"],
                returncode=3,
                stdout="",
                stderr="failed",
            )
        )

        with patch("scripts.operations_toolkit.parse_args", return_value=args):
            self.assertEqual(operations_toolkit.main([]), 3)

    def test_main_normalizes_negative_command_return_codes(self):
        args = argparse.Namespace(func=MagicMock())
        args.func.side_effect = operations_toolkit.CommandExecutionError(
            operations_toolkit.CommandResult(
                command=["terraform", "apply"],
                returncode=-9,
                stdout="",
                stderr="failed",
            )
        )

        with patch("scripts.operations_toolkit.parse_args", return_value=args):
            self.assertEqual(operations_toolkit.main([]), 137)


if __name__ == "__main__":
    unittest.main()
