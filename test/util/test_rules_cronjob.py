"""The CRS CronJob, its RBAC and the fetcher's reload modes must agree with each other (#1907)."""

import os
import re
import unittest
from unittest.mock import MagicMock, patch

import yaml

from src.util.rules_fetcher import config, fetcher, kubernetes

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load(*parts):
    with open(os.path.join(ROOT, *parts)) as handle:
        return [doc for doc in yaml.safe_load_all(handle) if doc]


class ManifestsAgree(unittest.TestCase):
    def setUp(self):
        self.cron = load("kubernetes", "waf-rules-fetcher-cronjob.yaml")[0]
        pod = self.cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        self.pod = pod
        self.container = pod["containers"][0]
        self.env = {e["name"]: e.get("value") for e in self.container["env"]}

    def test_the_job_is_pinned_to_a_direct_url_and_a_digest_and_requires_it(self):
        self.assertTrue(self.env["CRS_DOWNLOAD_URL"].startswith("https://codeload.github.com/"))
        self.assertRegex(self.env["CRS_SHA256"], r"^[0-9a-f]{64}$")
        self.assertEqual(self.env["RULES_REQUIRE_DIGEST"], "true")
        self.assertEqual(self.env["RULES_ALLOWED_DOMAINS"], "codeload.github.com")

    def test_the_rules_are_written_to_the_shared_volume_and_the_job_restarts_nginx_through_kubernetes(self):
        mounts = {m["name"]: m["mountPath"] for m in self.container["volumeMounts"]}
        self.assertEqual(self.env["MODSECURITY_DIR"], mounts["waf-rules"])
        claims = {v["name"]: v.get("persistentVolumeClaim", {}).get("claimName") for v in self.pod["volumes"]}
        pvc = load("kubernetes", "optional-waf-crs", "waf-rules-pvc.yaml")[0]
        self.assertEqual(claims["waf-rules"], pvc["metadata"]["name"])
        self.assertEqual(self.env["WAF_RELOAD_MODE"], "kubernetes")

    def test_the_job_may_restart_exactly_the_deployment_it_names(self):
        role = next(d for d in load("kubernetes", "waf-rules-fetcher-rbac.yaml") if d["kind"] == "Role")
        rule = next(r for r in role["rules"] if "deployments" in r["resources"])
        self.assertEqual(rule["resourceNames"], [self.env["WAF_RESTART_DEPLOYMENT"]])
        self.assertEqual(sorted(rule["verbs"]), ["get", "patch"])
        deployment = load("kubernetes", "nginx-deployment.yaml")[1]
        self.assertEqual(deployment["metadata"]["name"], self.env["WAF_RESTART_DEPLOYMENT"])

    def test_the_job_stays_suspended_and_keeps_its_hardening(self):
        self.assertTrue(self.cron["spec"]["suspend"])
        self.assertTrue(self.container["securityContext"]["readOnlyRootFilesystem"])
        self.assertFalse(self.container["securityContext"]["allowPrivilegeEscalation"])

    def test_the_nginx_patch_mounts_the_same_claim_read_only_where_the_readme_says(self):
        patch_doc = load("kubernetes", "optional-waf-crs", "nginx-waf-volume.patch.yaml")[0]
        pod = patch_doc["spec"]["template"]["spec"]
        self.assertTrue(pod["volumes"][0]["persistentVolumeClaim"]["readOnly"])
        self.assertTrue(pod["containers"][0]["volumeMounts"][0]["readOnly"])
        with open(os.path.join(ROOT, "kubernetes", "optional-waf-crs", "README.md")) as handle:
            readme = handle.read()
        self.assertIn(pod["containers"][0]["volumeMounts"][0]["mountPath"], readme)
        self.assertIsNotNone(re.search(r"CRS_SHA256", readme))


class ReloadModes(unittest.TestCase):
    def apply(self, mode, **kw):
        with patch.object(config, "WAF_RELOAD_MODE", mode), patch.object(fetcher, "MODSEC_DIR", "/nowhere"), \
                patch.object(fetcher, "rollback_crs", return_value=True) as rollback, \
                patch.object(fetcher.subprocess, "run", **kw) as run:
            return fetcher._apply_crs(), rollback, run

    def test_none_installs_and_does_not_signal_anything(self):
        ok, rollback, run = self.apply("none")
        self.assertTrue(ok)
        run.assert_not_called()
        rollback.assert_not_called()

    def test_local_reloads_nginx_and_rolls_back_when_that_fails(self):
        ok, rollback, run = self.apply("local")
        self.assertTrue(ok)
        run.assert_called_once()
        ok, rollback, run = self.apply("local", side_effect=FileNotFoundError("nginx"))
        self.assertFalse(ok)
        rollback.assert_called_once_with("/nowhere")

    def test_kubernetes_mode_restarts_the_named_deployment_and_never_runs_nginx_locally(self):
        api = MagicMock()
        with patch.object(config, "WAF_RELOAD_MODE", "kubernetes"), patch.object(config, "WAF_RESTART_DEPLOYMENT", "web"), \
                patch.object(config, "CONFIGMAP_NAMESPACE", "ns"), patch.object(fetcher, "get_apps_api", return_value=api), \
                patch.object(fetcher.subprocess, "run") as run:
            self.assertTrue(fetcher._apply_crs())
        run.assert_not_called()
        kwargs = api.patch_namespaced_deployment.call_args.kwargs
        self.assertEqual((kwargs["name"], kwargs["namespace"]), ("web", "ns"))
        annotations = kwargs["body"]["spec"]["template"]["metadata"]["annotations"]
        self.assertIn("kubectl.kubernetes.io/restartedAt", annotations)

    def test_kubernetes_mode_rolls_the_rules_back_when_the_restart_cannot_be_requested(self):
        for api in (None, MagicMock(**{"patch_namespaced_deployment.side_effect": RuntimeError("forbidden")})):
            with patch.object(config, "WAF_RELOAD_MODE", "kubernetes"), patch.object(fetcher, "get_apps_api", return_value=api), \
                    patch.object(fetcher, "MODSEC_DIR", "/nowhere"), patch.object(fetcher, "rollback_crs", return_value=True) as rollback:
                self.assertFalse(fetcher._apply_crs())
            rollback.assert_called_once()

    def test_an_unknown_mode_fails_and_rolls_back_instead_of_guessing(self):
        ok, rollback, run = self.apply("restart-everything")
        self.assertFalse(ok)
        rollback.assert_called_once()
        run.assert_not_called()

    def test_a_missing_kubernetes_client_is_reported_clearly_and_the_rules_are_rolled_back(self):
        with patch.object(kubernetes, "KUBE_AVAILABLE", False):
            with self.assertLogs("src.util.rules_fetcher.kubernetes", "ERROR") as logs:
                self.assertIsNone(kubernetes.get_apps_api())
        self.assertIn("Kubernetes client library is not installed", "".join(logs.output))
        with patch.object(config, "WAF_RELOAD_MODE", "kubernetes"), patch.object(fetcher, "get_apps_api", return_value=None), \
                patch.object(fetcher, "MODSEC_DIR", "/nowhere"), patch.object(fetcher, "rollback_crs", return_value=True) as rollback:
            self.assertFalse(fetcher._apply_crs())
        rollback.assert_called_once()

    def test_the_readme_recovery_restores_the_setup_file_too_and_names_the_image_prerequisite(self):
        with open(os.path.join(ROOT, "kubernetes", "optional-waf-crs", "README.md")) as handle:
            readme = handle.read()
        self.assertIn("crs-setup.conf.previous", readme)
        self.assertIn('pip install --no-cache-dir "kubernetes', readme)

    def test_rollout_restart_reports_failure_without_raising(self):
        api = MagicMock()
        api.patch_namespaced_deployment.side_effect = RuntimeError("forbidden")
        self.assertFalse(kubernetes.rollout_restart(api, "d", "n"))
        self.assertTrue(kubernetes.rollout_restart(MagicMock(), "d", "n"))


if __name__ == "__main__":
    unittest.main()
