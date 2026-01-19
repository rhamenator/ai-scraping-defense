import logging
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile

import requests

logger = logging.getLogger(__name__)


def download_and_extract_crs(url: str, dest_dir: str) -> bool:
    """Download and extract the OWASP Core Rule Set archive."""
    if not url:
        logger.error("No CRS archive URL provided.")
        return False

    try:
        response = requests.get(url, timeout=30, allow_redirects=False)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to download CRS archive from %s: %s", url, exc)
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = os.path.join(tmpdir, "crs_archive")
        with open(archive_path, "wb") as f:
            f.write(response.content)

        try:
            real_tmpdir = os.path.realpath(tmpdir)
            if url.endswith(".zip"):
                with zipfile.ZipFile(archive_path) as zf:
                    for member in zf.infolist():
                        if stat.S_ISLNK(member.external_attr >> 16):
                            logger.warning(
                                "Skipping symlink in archive: %s", member.filename
                            )
                            continue
                        target_path = os.path.realpath(
                            os.path.join(tmpdir, member.filename)
                        )
                        if (
                            os.path.commonpath([real_tmpdir, target_path])
                            != real_tmpdir
                        ):
                            logger.error(
                                "Archive member outside extraction directory: %s",
                                member.filename,
                            )
                            return False
                        zf.extract(member, tmpdir)
            else:
                with tarfile.open(archive_path, "r:gz") as tf:
                    for member in tf.getmembers():
                        if member.issym() or member.islnk():
                            logger.warning(
                                "Skipping symlink in archive: %s", member.name
                            )
                            continue
                        target_path = os.path.realpath(
                            os.path.join(tmpdir, member.name)
                        )
                        if (
                            os.path.commonpath([real_tmpdir, target_path])
                            != real_tmpdir
                        ):
                            logger.error(
                                "Archive member outside extraction directory: %s",
                                member.name,
                            )
                            return False
                        tf.extract(member, tmpdir, filter="data")
        except (tarfile.TarError, zipfile.BadZipFile) as exc:
            logger.error("Failed to extract CRS archive: %s", exc)
            return False

        src_root = None
        for root, dirs, files in os.walk(tmpdir):
            if (
                "crs-setup.conf" in files or "crs-setup.conf.example" in files
            ) and "rules" in dirs:
                src_root = root
                break

        if not src_root:
            logger.error("CRS archive missing expected files.")
            return False

        setup_file = os.path.join(src_root, "crs-setup.conf")
        if not os.path.exists(setup_file):
            setup_file = setup_file + ".example"

        os.makedirs(dest_dir, exist_ok=True)
        if os.path.islink(setup_file):
            logger.warning("Skipping symlink setup file: %s", setup_file)
        else:
            shutil.copy(setup_file, os.path.join(dest_dir, "crs-setup.conf"))

        dest_rules = os.path.join(dest_dir, "rules")
        if os.path.exists(dest_rules):
            shutil.rmtree(dest_rules)

        def _ignore_symlinks(path: str, names: list[str]) -> list[str]:
            return [name for name in names if os.path.islink(os.path.join(path, name))]

        shutil.copytree(
            os.path.join(src_root, "rules"), dest_rules, ignore=_ignore_symlinks
        )

    logger.info("OWASP CRS successfully installed to %s", dest_dir)
    return True
