import logging
import os
import re
import shlex
import shutil
import subprocess

logger = logging.getLogger(__name__)

DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[a-z0-9-]{1,63}\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)


def _is_enabled(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


def _valid_domain(domain: str) -> bool:
    return bool(DOMAIN_PATTERN.fullmatch(domain.strip(".")))


def _provider_command(domain: str) -> list[str] | None:
    provider = os.getenv("TLS_PROVIDER", "certbot").strip().lower()
    staging = _is_enabled("TLS_STAGING", "false")
    extra_args = shlex.split(os.getenv("TLS_EXTRA_ARGS", ""))

    if provider == "certbot":
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
        if webroot:
            command.extend(["--webroot", "-w", webroot])
        else:
            command.append("--standalone")
        if staging:
            command.append("--staging")
        server = os.getenv("TLS_SERVER")
        if server:
            command.extend(["--server", server])
        key_type = os.getenv("TLS_KEY_TYPE")
        if key_type:
            command.extend(["--key-type", key_type])
        return command + extra_args

    if provider == "acme.sh":
        executable = os.getenv("TLS_ACME_SH_BIN") or shutil.which("acme.sh")
        if not executable:
            logger.warning("Managed TLS enabled but acme.sh is not installed.")
            return None
        command = [executable, "--issue", "-d", domain]
        webroot = os.getenv("TLS_WEBROOT")
        if webroot:
            command.extend(["-w", webroot])
        else:
            command.append("--standalone")
        if staging:
            command.append("--staging")
        server = os.getenv("TLS_SERVER")
        if server:
            command.extend(["--server", server])
        return command + extra_args

    logger.warning("Unsupported TLS provider %s.", provider)
    return None


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
