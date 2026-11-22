"""Download, verify, stage and activate the OWASP Core Rule Set (#1907).

The archive is checked against a pinned digest when one is configured, extracted with hard limits on members, bytes and
expansion into a staging directory next to the live rules, validated, and only then swapped in. The previous rules are
kept so that a failed reload can be rolled back.
"""

import logging
import os
import posixpath
import shutil
import stat
import tarfile
import tempfile
import zipfile
from typing import IO, Iterator, Optional

from . import config
from .download import (
    RulesDownloadError,
    check_source,
    download_bounded,
    validate_rules_text,
    verify_digest,
)

logger = logging.getLogger(__name__)

_RULE_SUFFIXES = (".conf", ".data", ".example")
_COPY_CHUNK = 64 * 1024


def _looks_like_zip(content: bytes) -> bool:
    return content.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))


def _looks_like_gzip(content: bytes) -> bool:
    return content.startswith(b"\x1f\x8b")


class _Budget:
    """Counts what has been extracted and refuses to go past the configured limits."""

    def __init__(self, compressed_size: int):
        self.members = 0
        self.declared = 0
        self.written = 0
        self.max_total = min(
            config.CRS_MAX_EXTRACTED_BYTES,
            max(compressed_size, 1) * config.CRS_MAX_EXPANSION_RATIO,
        )

    def member(self, declared_size: int) -> None:
        self.members += 1
        if self.members > config.CRS_MAX_MEMBERS:
            raise RulesDownloadError(f"archive has more than {config.CRS_MAX_MEMBERS} members")
        if declared_size > config.CRS_MAX_FILE_BYTES:
            raise RulesDownloadError(f"archive member is {declared_size} bytes, over the per-file limit")
        self.declared += max(declared_size, 0)
        if self.declared > self.max_total:
            raise RulesDownloadError("archive would expand beyond the allowed size or ratio")

    def copy(self, source: IO[bytes], destination: IO[bytes]) -> None:
        in_file = 0
        while True:
            chunk = source.read(_COPY_CHUNK)
            if not chunk:
                return
            in_file += len(chunk)
            self.written += len(chunk)
            if in_file > config.CRS_MAX_FILE_BYTES or self.written > self.max_total:
                raise RulesDownloadError("archive expanded beyond the allowed size or ratio")
            destination.write(chunk)


def _member_parts(name: str) -> list[str]:
    """The path components of an archive member, refusing absolute paths, ``..`` and backslashes."""
    if name.startswith(("/", "\\")) or "\\" in name:
        raise RulesDownloadError(f"unsafe archive member name: {name!r}")
    parts = [p for p in posixpath.normpath(name).split("/") if p not in ("", ".")]
    if ".." in parts:
        raise RulesDownloadError(f"archive member outside the extraction directory: {name!r}")
    return parts


def _staged_path(rel: list[str]) -> Optional[str]:
    """Where a path (relative to the archive's top-level directory) is kept, or None to skip it."""
    if rel in (["crs-setup.conf"], ["crs-setup.conf.example"]):
        return rel[0]
    if len(rel) >= 2 and rel[0] == "rules" and rel[-1].endswith(_RULE_SUFFIXES):
        return posixpath.join(*rel)
    return None


def _wanted(name: str) -> Optional[str]:
    """Where a member goes inside the staging directory, or None to skip it.

    Only ``crs-setup.conf[.example]`` and the files directly or below ``rules/`` of the archive's single top-level
    directory are kept.
    """
    parts = _member_parts(name)
    for rel in ((parts, parts[1:]) if len(parts) > 1 else (parts,)):
        target = _staged_path(rel)
        if target is not None:
            return target
    return None


def _write(staging: str, relative: str, budget: _Budget, source: IO[bytes]) -> None:
    target = os.path.join(staging, *relative.split("/"))
    if os.path.commonpath([os.path.realpath(staging), os.path.realpath(target)]) != os.path.realpath(staging):
        raise RulesDownloadError(f"archive member outside the extraction directory: {relative!r}")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        budget.copy(source, handle)


def _extract_tar(path: str, staging: str, budget: _Budget) -> None:
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:  # lazily, so an oversized member is refused before it is skipped over
            budget.member(member.size if member.isfile() else 0)
            if member.issym() or member.islnk():
                logger.warning("Skipping symlink in archive: %s", member.name)
                continue
            if not member.isfile():
                continue
            relative = _wanted(member.name)
            if relative is None:
                continue
            source = archive.extractfile(member)
            if source is not None:
                _write(staging, relative, budget, source)


def _extract_zip(path: str, staging: str, budget: _Budget) -> None:
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            budget.member(info.file_size)
            if stat.S_ISLNK(info.external_attr >> 16):
                logger.warning("Skipping symlink in archive: %s", info.filename)
                continue
            if info.is_dir():
                continue
            relative = _wanted(info.filename)
            if relative is None:
                continue
            with archive.open(info) as source:
                _write(staging, relative, budget, source)


def _rule_files(rules_dir: str) -> Iterator[str]:
    for root, _dirs, files in os.walk(rules_dir):
        for name in files:
            if name.endswith(".conf"):
                yield os.path.join(root, name)


def _find_setup(staging: str) -> Optional[str]:
    for name in ("crs-setup.conf", "crs-setup.conf.example"):
        if os.path.isfile(os.path.join(staging, name)):
            return name
    return None


def _check_rule_file(path: str, staging: str) -> None:
    """A CRS file may hold no rules itself, so only the forbidden constructs fail here."""
    relative = os.path.relpath(path, staging)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            problems = validate_rules_text(handle.read())
    except UnicodeDecodeError as exc:
        raise RulesDownloadError(f"{relative} is not valid UTF-8") from exc
    forbidden = [p for p in problems if "not allowed" in p]
    if forbidden:
        raise RulesDownloadError(f"{relative}: {forbidden[0]}")


def _validate_staged(staging: str) -> str:
    """Check the staged tree and return the name of its setup file."""
    setup = _find_setup(staging)
    rules_dir = os.path.join(staging, "rules")
    if setup is None or not os.path.isdir(rules_dir):
        raise RulesDownloadError("CRS archive missing expected files")
    files = list(_rule_files(rules_dir))
    if not files:
        raise RulesDownloadError("CRS archive contains no rule files")
    for path in files:
        _check_rule_file(path, staging)
    return setup


def _activate(staging: str, setup: str, dest_dir: str) -> None:
    """Swap the staged rules in with renames, keeping the previous generation for rollback."""
    live_rules = os.path.join(dest_dir, "rules")
    previous_rules = os.path.join(dest_dir, "rules.previous")
    live_setup = os.path.join(dest_dir, "crs-setup.conf")
    previous_setup = os.path.join(dest_dir, "crs-setup.conf.previous")
    if os.path.isdir(previous_rules):
        shutil.rmtree(previous_rules)
    if os.path.isdir(live_rules):
        os.rename(live_rules, previous_rules)
    try:
        os.rename(os.path.join(staging, "rules"), live_rules)
        if os.path.isfile(live_setup):
            shutil.copy2(live_setup, previous_setup)
        shutil.copy2(os.path.join(staging, setup), live_setup + ".new")
        os.replace(live_setup + ".new", live_setup)
    except OSError:
        rollback_crs(dest_dir)
        raise


def rollback_crs(dest_dir: str) -> bool:
    """Restore the rules that were live before the last installation. Returns False when there is nothing to restore."""
    live_rules = os.path.join(dest_dir, "rules")
    previous_rules = os.path.join(dest_dir, "rules.previous")
    live_setup = os.path.join(dest_dir, "crs-setup.conf")
    previous_setup = os.path.join(dest_dir, "crs-setup.conf.previous")
    if not os.path.isdir(previous_rules):
        return False
    if os.path.isdir(live_rules):
        shutil.rmtree(live_rules)
    os.rename(previous_rules, live_rules)
    if os.path.isfile(previous_setup):
        os.replace(previous_setup, live_setup)
    logger.warning("Rolled back to the previous OWASP CRS rules in %s", dest_dir)
    return True


def _fetch_archive(url: str, domains: Optional[list[str]], digest: str) -> tuple[bytes, bool]:
    """Download and verify the archive; returns its bytes and whether it is a ZIP (otherwise a gzip tarball)."""
    check_source(url, domains)
    content = download_bounded(url, timeout=30, max_bytes=config.CRS_MAX_DOWNLOAD_BYTES)
    verify_digest(content, digest, require=config.RULES_REQUIRE_DIGEST, what="OWASP CRS archive")
    is_zip = url.endswith(".zip")
    if is_zip and not _looks_like_zip(content):
        raise RulesDownloadError(f"CRS archive does not look like a ZIP file: {url}")
    if not is_zip and not _looks_like_gzip(content):
        raise RulesDownloadError(f"CRS archive does not look like a gzip file: {url}")
    return content, is_zip


def _extract_archive(content: bytes, is_zip: bool, staging: str) -> None:
    """Extract the wanted members of ``content`` into ``staging`` within the configured budgets."""
    archive_path = os.path.join(staging, ".archive")
    with open(archive_path, "wb") as handle:
        handle.write(content)
    budget = _Budget(len(content))
    try:
        (_extract_zip if is_zip else _extract_tar)(archive_path, staging, budget)
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError) as exc:
        raise RulesDownloadError(f"failed to extract CRS archive: {exc}") from exc
    os.remove(archive_path)


def download_and_extract_crs(
    url: str,
    dest_dir: str,
    allowed_domains: Optional[list[str]] = None,
    expected_sha256: Optional[str] = None,
) -> bool:
    """Download, verify, validate and install the OWASP Core Rule Set. Returns False and installs nothing on any problem."""
    if not url:
        logger.error("No CRS archive URL provided.")
        return False
    domains = allowed_domains if allowed_domains is not None else config.ALLOWED_RULES_DOMAINS
    digest = config.CRS_SHA256 if expected_sha256 is None else expected_sha256
    staging = ""
    try:
        content, is_zip = _fetch_archive(url, domains, digest)
        os.makedirs(dest_dir, exist_ok=True)
        # Same filesystem as the live rules, so the final swap is a rename.
        staging = tempfile.mkdtemp(prefix=".crs-staging-", dir=dest_dir)
        _extract_archive(content, is_zip, staging)
        _activate(staging, _validate_staged(staging), dest_dir)
    except (RulesDownloadError, OSError) as exc:
        logger.error("OWASP CRS not installed: %s", exc)
        return False
    finally:
        if staging and os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)

    logger.info("OWASP CRS successfully installed to %s", dest_dir)
    return True
