"""Operations automation for backups, restores, deployments, and change management.

This utility consolidates the day-two operational workflows so they can be
scheduled (via cron, CI, or GitOps) and exercised during incident response
practice.  The commands are intentionally shell-friendly and leverage
subprocess calls to existing tools (`pg_dump`, `redis-cli`, `terraform`,
`ansible`, `kubectl`) without enforcing a particular platform.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

LOG = logging.getLogger(__name__)
DEFAULT_BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "./backups"))


@dataclass
class CommandResult:
    command: List[str]
    returncode: int
    stdout: str
    stderr: str


def run_command(command: Iterable[str], *, execute: bool, cwd: Path | None = None) -> CommandResult:
    """Run a command, optionally in dry-run mode, returning captured output."""

    args = list(command)
    LOG.debug("Prepared command: %s", shlex.join(args))
    if not execute:
        LOG.info("[dry-run] %s", shlex.join(args))
        return CommandResult(command=args, returncode=0, stdout="", stderr="")

    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        LOG.error("Command failed (%s): %s", proc.returncode, shlex.join(args))
        LOG.error(proc.stderr.strip())
    else:
        LOG.info("Command succeeded: %s", shlex.join(args))
    return CommandResult(args, proc.returncode, proc.stdout, proc.stderr)


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def backup(args: argparse.Namespace) -> None:
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    destination = Path(args.destination or DEFAULT_BACKUP_DIR) / timestamp
    ensure_directory(destination)

    LOG.info("Creating backup in %s", destination)
    postgres_file = destination / "postgres.sql"
    redis_file = destination / "redis.rdb"
    state_file = destination / "cluster_state.json"

    run_command(
        [
            "pg_dump",
            "--dbname",
            args.postgres_url,
            "--file",
            str(postgres_file),
        ],
        execute=args.execute,
    )
    run_command(
        [
            "redis-cli",
            "-u",
            args.redis_url,
            "--rdb",
            str(redis_file),
        ],
        execute=args.execute,
    )
    run_command(
        [
            "kubectl",
            "--context",
            args.kube_context,
            "get",
            "all",
            "--all-namespaces",
            "-o",
            "json",
        ],
        execute=args.execute,
    )
    if args.execute:
        (state_file).write_text(
            json.dumps(
                {
                    "generated_at": datetime.utcnow().isoformat(),
                    "postgres_dump": str(postgres_file),
                    "redis_dump": str(redis_file),
                    "kube_context": args.kube_context,
                },
                indent=2,
            )
        )
    LOG.info("Backup complete")


def restore(args: argparse.Namespace) -> None:
    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"Backup directory {source} does not exist")

    LOG.info("Restoring from %s", source)
    run_command(
        ["psql", args.postgres_url, "-f", str(source / "postgres.sql")],
        execute=args.execute,
    )
    redis_dump = source / "redis.rdb"
    if redis_dump.exists():
        run_command(
            [
                "cp",
                str(redis_dump),
                str(Path(args.redis_data_dir) / "dump.rdb"),
            ],
            execute=args.execute,
        )
        LOG.warning(
            "Redis dump copied. Restart the redis service on %s to load the snapshot.",
            args.redis_host,
        )
    else:
        LOG.warning("No redis.rdb file found in %s", source)
    LOG.info("Restore jobs queued")


def disaster_recovery_drill(args: argparse.Namespace) -> None:
    LOG.info("Starting disaster recovery drill against %s", args.environment)
    backup_args = argparse.Namespace(
        destination=args.drill_backup_dir,
        postgres_url=args.postgres_url,
        redis_url=args.redis_url,
        kube_context=args.kube_context,
        execute=args.execute,
    )
    backup(backup_args)
    restore(
        argparse.Namespace(
            source=args.drill_backup_dir,
            postgres_url=args.postgres_url,
            redis_url=args.redis_url,
            execute=args.execute,
        )
    )
    LOG.info("Drill completed")


def deploy(args: argparse.Namespace) -> None:
    LOG.info("Deploying environment %s", args.environment)
    run_command(
        ["terraform", "-chdir", args.terraform_dir, "apply", "-auto-approve"],
        execute=args.execute,
    )
    run_command(
        [
            "ansible-playbook",
            "-i",
            args.ansible_inventory,
            args.ansible_playbook,
        ],
        execute=args.execute,
    )
    run_command(
        ["kubectl", "--context", args.kube_context, "apply", "-k", args.kustomize_dir],
        execute=args.execute,
    )
    LOG.info("Deployment pipeline finished")


def gitops_sync(args: argparse.Namespace) -> None:
    LOG.info("Reconciling GitOps state for %s", args.environment)
    run_command(
        [
            "flux",
            "reconcile",
            "ks",
            args.kustomization,
            "--with-source",
        ],
        execute=args.execute,
    )
    run_command(
        [
            "flux",
            "reconcile",
            "helmrelease",
            args.helm_release,
        ],
        execute=args.execute,
    )
    LOG.info("GitOps reconciliation triggered")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run commands instead of logging them")
    sub = parser.add_subparsers(dest="command", required=True)

    backup_parser = sub.add_parser("backup", help="Create a full backup")
    backup_parser.add_argument("--destination", help="Directory for backup artifacts")
    backup_parser.add_argument("--postgres-url", default=os.getenv("POSTGRES_URL", "postgres://postgres@localhost:5432/postgres"))
    backup_parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    backup_parser.add_argument("--kube-context", default=os.getenv("KUBE_CONTEXT", "kind-ai-defense"))
    backup_parser.set_defaults(func=backup)

    restore_parser = sub.add_parser("restore", help="Restore from a backup directory")
    restore_parser.add_argument("source", help="Backup directory to restore")
    restore_parser.add_argument("--postgres-url", default=os.getenv("POSTGRES_URL", "postgres://postgres@localhost:5432/postgres"))
    restore_parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    restore_parser.add_argument("--redis-data-dir", default="/var/lib/redis")
    restore_parser.add_argument("--redis-host", default="localhost")
    restore_parser.set_defaults(func=restore)

    drill_parser = sub.add_parser("drill", help="Execute an end-to-end DR drill")
    drill_parser.add_argument("--environment", default="staging")
    drill_parser.add_argument("--drill-backup-dir", default="./drills/latest")
    drill_parser.add_argument("--postgres-url", default=os.getenv("POSTGRES_URL", "postgres://postgres@localhost:5432/postgres"))
    drill_parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    drill_parser.add_argument("--kube-context", default=os.getenv("KUBE_CONTEXT", "kind-ai-defense"))
    drill_parser.set_defaults(func=disaster_recovery_drill)

    deploy_parser = sub.add_parser("deploy", help="Run Terraform/Ansible/Kubernetes deployment")
    deploy_parser.add_argument("--environment", default="staging")
    deploy_parser.add_argument("--terraform-dir", default="infrastructure/terraform")
    deploy_parser.add_argument("--ansible-inventory", default="ansible/inventory.yaml")
    deploy_parser.add_argument("--ansible-playbook", default="ansible/site.yaml")
    deploy_parser.add_argument("--kube-context", default=os.getenv("KUBE_CONTEXT", "kind-ai-defense"))
    deploy_parser.add_argument("--kustomize-dir", default="kubernetes/overlays/${ENVIRONMENT}")
    deploy_parser.set_defaults(func=deploy)

    gitops_parser = sub.add_parser("gitops", help="Trigger GitOps reconciliation")
    gitops_parser.add_argument("--environment", default="staging")
    gitops_parser.add_argument("--kustomization", default="ai-defense")
    gitops_parser.add_argument("--helm-release", default="grafana")
    gitops_parser.set_defaults(func=gitops_sync)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
