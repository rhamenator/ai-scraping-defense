import logging
import os
import re
import shlex
import shutil
import subprocess  # nosec B404

logger = logging.getLogger(__name__)

_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_TLD_PATTERN = re.compile(r"^[a-z]{2,63}$", re.IGNORECASE)


def _is_enabled(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


def _valid_domain(domain: str) -> bool:
    candidate = domain.strip(".")
    if not candidate or len(candidate) > 253:
        return False
    labels = candidate.split(".")
    if len(labels) < 2 or not _TLD_PATTERN.match(labels[-1]):
        return False
    return all(_LABEL_PATTERN.match(label) for label in labels[:-1])


def _certbot_command(domain: str, staging: bool) -> list[str] | None:
    executable = os.getenv("TLS_CERTBOT_BIN") or shutil.which("certbot")
    email = os.getenv("TLS_EMAIL")
    if not executable:
        logger.warning("Managed TLS enabled but certbot is not installed.")
        return None
    if not email:
        logger.warning("Managed TLS requires TLS_EMAIL when TLS_PROVIDER=certbot.")
        return None
    webroot = os.getenv("TLS_WEBROOT")
    command = [
        executable,
        "certonly",
        "--non-interactive",
        "--agree-tos",
        "--email",
        email,
        "-d",
        domain,
    ]
    command.extend(["--webroot", "-w", webroot] if webroot else ["--standalone"])
    if staging:
        command.append("--staging")
    server = os.getenv("TLS_SERVER")
    if server:
        command.extend(["--server", server])
    key_type = os.getenv("TLS_KEY_TYPE")
    if key_type:
        command.extend(["--key-type", key_type])
    return command


def _acme_sh_command(domain: str, staging: bool) -> list[str] | None:
    executable = os.getenv("TLS_ACME_SH_BIN") or shutil.which("acme.sh")
    if not executable:
        logger.warning("Managed TLS enabled but acme.sh is not installed.")
        return None
    command = [executable, "--issue", "-d", domain]
    webroot = os.getenv("TLS_WEBROOT")
    command.extend(["-w", webroot] if webroot else ["--standalone"])
    if staging:
        command.append("--staging")
    server = os.getenv("TLS_SERVER")
    if server:
        command.extend(["--server", server])
    return command


_PROVIDER_COMMAND_BUILDERS = {
    "certbot": _certbot_command,
    "acme.sh": _acme_sh_command,
}


def _provider_command(domain: str) -> list[str] | None:
    provider = os.getenv("TLS_PROVIDER", "certbot").strip().lower()
    builder = _PROVIDER_COMMAND_BUILDERS.get(provider)
    if builder is None:
        logger.warning("Unsupported TLS provider %s.", provider)
        return None

    staging = _is_enabled("TLS_STAGING", "false")
    command = builder(domain, staging)
    if command is None:
        return None
    return command + shlex.split(os.getenv("TLS_EXTRA_ARGS", ""))


def ensure_certificate(domain: str) -> bool:
    """Request or renew a TLS certificate using an installed ACME client."""
    if not _is_enabled("ENABLE_MANAGED_TLS"):
        logger.debug("Managed TLS disabled.")
        return False

    normalized_domain = domain.strip().lower().rstrip(".")
    if not _valid_domain(normalized_domain):
        logger.warning(
            "Refusing to request TLS certificate for invalid domain %s", domain
        )
        return False

    command = _provider_command(normalized_domain)
    if not command:
        return False

    logger.info(
        "Ensuring TLS certificate for %s via %s.",
        normalized_domain,
        os.getenv("TLS_PROVIDER", "certbot").strip().lower(),
    )
    try:
        completed = subprocess.run(  # nosec B603
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip()
        logger.warning(
            "Managed TLS command failed for %s: %s", normalized_domain, stderr
        )
        return False
    except OSError as exc:
        logger.warning(
            "Managed TLS command could not be executed for %s: %s",
            normalized_domain,
            exc,
        )
        return False

    output = (completed.stdout or "").strip()
    if output:
        logger.debug("Managed TLS command output for %s: %s", normalized_domain, output)
    return True


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
