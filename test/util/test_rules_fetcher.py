import io
import os
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

import requests

from src.util import rules_fetcher


class MockResponse:
    def __init__(self, text: bytes | str, status_code: int = 200):
        self.status_code = status_code
        if isinstance(text, (bytes, bytearray)):
            self.content = text
            try:
                self.text = text.decode()
            except Exception:
                self.text = ""
        else:
            self.text = text
            self.content = text.encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError()


class TestRulesFetcher(unittest.TestCase):
    def setUp(self):
        self.patcher_get = patch("src.util.rules_fetcher.fetcher.requests.get")
        self.mock_get = self.patcher_get.start()
        self.addCleanup(self.patcher_get.stop)
        self.patcher_subprocess = patch("src.util.rules_fetcher.fetcher.subprocess.run")
        self.mock_subprocess = self.patcher_subprocess.start()
        self.addCleanup(self.patcher_subprocess.stop)

    def test_fetch_rules_success(self):
        self.mock_get.return_value = MockResponse("SecRule ...", 200)
        content = rules_fetcher.fetch_rules("https://example.com/rules")
        self.assertEqual(content, "SecRule ...")
        self.mock_get.assert_called_once()

    def test_fetch_rules_error(self):
        self.mock_get.side_effect = requests.exceptions.RequestException()
        content = rules_fetcher.fetch_rules("https://example.com/rules")
        self.assertEqual(content, "")

    def test_fetch_rules_rejects_non_https(self):
        content = rules_fetcher.fetch_rules("http://example.com/rules")
        self.assertEqual(content, "")
        self.mock_get.assert_not_called()

    def test_fetch_rules_domain_not_allowed(self):
        allowed = ["example.com"]
        content = rules_fetcher.fetch_rules(
            "https://notallowed.com/rules", allowed_domains=allowed
        )
        self.assertEqual(content, "")
        self.mock_get.assert_not_called()

    def test_fetch_rules_domain_allowed(self):
        allowed = ["example.com"]
        self.mock_get.return_value = MockResponse("SecRule ...", 200)
        content = rules_fetcher.fetch_rules(
            "https://example.com/rules", allowed_domains=allowed
        )
        self.assertEqual(content, "SecRule ...")
        self.mock_get.assert_called_once()

    @unittest.skipIf(
        not rules_fetcher.KUBE_AVAILABLE, "Kubernetes library not installed"
    )
    def test_update_configmap_patches_existing(self):
        mock_api = MagicMock()
        rules_fetcher.update_configmap(mock_api, "content")
        mock_api.patch_namespaced_config_map.assert_called_once()

    def test_main_flow_local(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("src.util.rules_fetcher.fetcher.reload_waf_rules") as mock_reload,
            patch(
                "src.util.rules_fetcher.fetcher.RULES_URL", "https://example.com/rules"
            ),
            patch("src.util.rules_fetcher.fetcher.ALLOWED_RULES_DOMAINS", []),
            patch("src.util.rules_fetcher.fetcher.CRS_DOWNLOAD_URL", ""),
        ):
            self.mock_get.return_value = MockResponse("SecRule ...", 200)
            result = rules_fetcher._run_as_script()
            self.assertTrue(result)
            mock_reload.assert_called_once()

    def test_main_flow_no_rules_returns_false(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("src.util.rules_fetcher.fetcher.reload_waf_rules") as mock_reload,
            patch(
                "src.util.rules_fetcher.fetcher.RULES_URL", "https://example.com/rules"
            ),
            patch("src.util.rules_fetcher.fetcher.ALLOWED_RULES_DOMAINS", []),
            patch("src.util.rules_fetcher.fetcher.CRS_DOWNLOAD_URL", ""),
        ):
            self.mock_get.return_value = MockResponse("", 200)
            result = rules_fetcher._run_as_script()
            self.assertFalse(result)
            mock_reload.assert_not_called()

    def test_reload_failure_returns_false(self):
        with (
            patch(
                "src.util.rules_fetcher.fetcher.CRS_DOWNLOAD_URL", "https://crs.example"
            ),
            patch(
                "src.util.rules_fetcher.fetcher.download_and_extract_crs",
                return_value=True,
            ),
        ):
            self.mock_subprocess.side_effect = subprocess.CalledProcessError(
                1, ["nginx"]
            )
            result = rules_fetcher._run_as_script()
            self.assertFalse(result)

    def test_download_and_extract_crs(self):
        # Create tiny tar.gz archive with CRS structure
        tar_bytes = io.BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w:gz") as tf:
            info = tarfile.TarInfo("crs-setup.conf.example")
            data = b"# CRS setup"
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

            info = tarfile.TarInfo("rules/example.conf")
            data = b"SecRule"
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        tar_bytes.seek(0)
        self.mock_get.return_value = MockResponse(tar_bytes.getvalue(), 200)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = rules_fetcher.download_and_extract_crs(
                "http://example.com/crs.tar.gz", tmpdir
            )
            self.assertTrue(result)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "crs-setup.conf")))
            self.assertTrue(
                os.path.exists(os.path.join(tmpdir, "rules", "example.conf"))
            )

    def test_download_and_extract_crs_prevents_tar_path_traversal(self):
        tar_bytes = io.BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w:gz") as tf:
            info = tarfile.TarInfo("../evil.conf")
            data = b"bad"
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

            info = tarfile.TarInfo("crs-setup.conf.example")
            data = b"# CRS setup"
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

            info = tarfile.TarInfo("rules/example.conf")
            data = b"SecRule"
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        tar_bytes.seek(0)
        self.mock_get.return_value = MockResponse(tar_bytes.getvalue(), 200)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = rules_fetcher.download_and_extract_crs(
                "http://example.com/crs.tar.gz", tmpdir
            )
            self.assertFalse(result)
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "crs-setup.conf")))

    def test_download_and_extract_crs_prevents_zip_path_traversal(self):
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, mode="w") as zf:
            zf.writestr("../evil.conf", "bad")
            zf.writestr("crs-setup.conf.example", "# CRS setup")
            zf.writestr("rules/example.conf", "SecRule")

        zip_bytes.seek(0)
        self.mock_get.return_value = MockResponse(zip_bytes.getvalue(), 200)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = rules_fetcher.download_and_extract_crs(
                "http://example.com/crs.zip", tmpdir
            )
            self.assertFalse(result)
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "crs-setup.conf")))

    def test_download_and_extract_crs_skips_symlink_members(self):
        tar_bytes = io.BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w:gz") as tf:
            info = tarfile.TarInfo("crs-setup.conf.example")
            data = b"# CRS setup"
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

            info = tarfile.TarInfo("rules/example.conf")
            data = b"SecRule"
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

            info = tarfile.TarInfo("rules/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "../evil"
            tf.addfile(info)

        tar_bytes.seek(0)
        self.mock_get.return_value = MockResponse(tar_bytes.getvalue(), 200)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = rules_fetcher.download_and_extract_crs(
                "http://example.com/crs.tar.gz", tmpdir
            )
            self.assertTrue(result)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "crs-setup.conf")))
            self.assertTrue(
                os.path.exists(os.path.join(tmpdir, "rules", "example.conf"))
            )
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "rules", "link")))


if __name__ == "__main__":
    unittest.main()
