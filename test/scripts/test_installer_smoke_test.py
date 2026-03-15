import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from scripts import installer_smoke_test


def _completed(stdout="", stderr="", returncode=0):
    return installer_smoke_test.subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestInstallerSmokeTest(unittest.TestCase):
    def test_run_smoke_test_for_nginx_contract(self):
        outputs = {
            (
                "inspect",
                "-f",
                "{{.State.Status}}",
                "postgres_markov_db",
            ): _completed(stdout="running\n"),
            (
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
                "postgres_markov_db",
            ): _completed(stdout="healthy\n"),
            ("inspect", "-f", "{{.State.Status}}", "redis_store"): _completed(
                stdout="running\n"
            ),
            (
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
                "redis_store",
            ): _completed(stdout="healthy\n"),
            ("inspect", "-f", "{{.State.Status}}", "admin_ui"): _completed(
                stdout="running\n"
            ),
            (
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
                "admin_ui",
            ): _completed(stdout="healthy\n"),
            ("inspect", "-f", "{{.State.Status}}", "escalation_engine"): _completed(
                stdout="running\n"
            ),
            (
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
                "escalation_engine",
            ): _completed(stdout="healthy\n"),
            ("inspect", "-f", "{{.State.Status}}", "tarpit_api"): _completed(
                stdout="running\n"
            ),
            (
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
                "tarpit_api",
            ): _completed(stdout="healthy\n"),
            ("inspect", "-f", "{{.State.Status}}", "nginx_proxy"): _completed(
                stdout="running\n"
            ),
            (
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
                "nginx_proxy",
            ): _completed(stdout="healthy\n"),
            (
                "inspect",
                "-f",
                '{{(index (index .NetworkSettings.Ports "80/tcp") 0).HostPort}}',
                "nginx_proxy",
            ): _completed(stdout="8088\n"),
            (
                "inspect",
                "-f",
                '{{(index (index .NetworkSettings.Ports "443/tcp") 0).HostPort}}',
                "nginx_proxy",
            ): _completed(stdout="8443\n"),
            (
                "exec",
                "admin_ui",
                "curl",
                "-fsS",
                "http://127.0.0.1:5002/observability/health",
            ): _completed(stdout="ok"),
            (
                "exec",
                "tarpit_api",
                "curl",
                "-fsS",
                "http://127.0.0.1:8001/health",
            ): _completed(stdout="ok"),
            (
                "exec",
                "escalation_engine",
                "curl",
                "-fsS",
                "http://127.0.0.1:8003/health",
            ): _completed(stdout='{"status":"healthy"}'),
        }

        def fake_run(*command):
            key = tuple(command[1:])
            return outputs[key]

        with (
            patch("scripts.installer_smoke_test.run_docker", side_effect=fake_run),
            patch("scripts.installer_smoke_test.assert_http") as mock_http,
            io.StringIO() as buf,
            redirect_stdout(buf),
        ):
            installer_smoke_test.run_smoke_test(
                installer_smoke_test.SmokeConfig(platform="linux", proxy="nginx")
            )
            output = buf.getvalue()

        self.assertIn("=== Stack Smoke Test (linux / nginx) ===", output)
        self.assertIn("[OK] nginx_proxy HTTPS is reachable on port 8443", output)
        self.assertIn("Smoke test passed.", output)
        self.assertEqual(mock_http.call_count, 2)

    def test_main_reports_failures_with_contract_prefix(self):
        with (
            patch(
                "scripts.installer_smoke_test.run_smoke_test",
                side_effect=installer_smoke_test.SmokeFailure(
                    "redis_store is not running"
                ),
            ),
            io.StringIO() as stderr,
            redirect_stderr(stderr),
        ):
            result = installer_smoke_test.main(
                ["--platform", "linux", "--proxy", "nginx"]
            )
            error_output = stderr.getvalue()

        self.assertEqual(result, 1)
        self.assertIn("[FAIL] redis_store is not running", error_output)
