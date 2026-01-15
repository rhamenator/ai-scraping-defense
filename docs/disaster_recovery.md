# Backup, Restore, and Disaster Recovery

Business continuity for the defense stack relies on consistent data protection,
regular validation drills, and automated orchestration.  The following
playbooks cover the full lifecycle.

## Backup Strategy

| Asset             | Tooling                          | Frequency | Retention |
|-------------------|----------------------------------|-----------|-----------|
| PostgreSQL        | `pg_dump` (logical)              | Hourly    | 7 days    |
| Redis             | `redis-cli --rdb`                | Hourly    | 7 days    |
| Object Storage    | `rclone sync`                    | Daily     | 30 days   |
| Kubernetes State  | `kubectl get all --all-namespaces` | Daily   | 30 days   |

Backups are executed via `scripts/operations_toolkit.py backup` and stored in
`BACKUP_DIR` (default `./backups`).  Artifacts are encrypted by the platform's
storage layer and replicated to off-site storage.

## Restore Procedure

1. Identify the desired timestamp in the backup directory hierarchy.
2. Run `scripts/operations_toolkit.py restore --source ./backups/<timestamp> --execute`.
   * The script restores PostgreSQL using `psql`.
   * The Redis RDB is copied to the configured data directory. Restart Redis to
     load the snapshot.
3. Apply any Kubernetes manifests captured in `cluster_state.json` if needed.
4. Validate the environment using `/health` for each microservice.

## Disaster Recovery Drills

Quarterly drills simulate a full-region failure:

1. Run `scripts/operations_toolkit.py drill --environment staging --execute` to
   perform a backup and restore cycle inside staging.
2. Promote the staging environment to production using the GitOps workflow (see
   [Operations Automation](operations_playbooks.md)).
3. Capture metrics on recovery time objective (RTO) and recovery point
   objective (RPO).  The target RTO is 30 minutes and RPO is 15 minutes.
4. Document gaps and feed improvements into the backlog.

## Business Continuity

* **Hot standby** – Maintain a warm standby cluster in an alternate region with
  infrastructure declared via Terraform and configuration managed with
  Ansible.  GitOps keeps configuration drift-free.
* **Failover trigger** – Incident commander authorises failover when SLOs are
  breached for more than 5 minutes and the root cause is infrastructure-related.
* **Communication plan** – Notify internal stakeholders via Slack `#incident`
  channel and external customers via status page updates.

## Automation Hooks

* Add the backup command to a cron job or Kubernetes `CronJob` for continuous
  protection.
* Integrate the `drill` command into CI to run on a rolling basis (e.g., once a
  week) and surface failures.
* Use the JSON metadata files in each backup directory for audit trails and to
  prove compliance with regulatory requirements.

## Resilience Validation

* **Failure Injection Testing**: Regularly inject failures into the system to validate its resilience. This can be done using tools like Chaos Mesh or LitmusChaos. Metrics should be gathered to determine MTTR and MTBF.
* **Automated Rollback**: Implement automated rollback procedures to quickly revert to a stable state in case of a failure. Test these procedures regularly to ensure they work as expected.
* **Health Checks**: Implement comprehensive health checks for all services to quickly detect and respond to failures. Use these health checks to automatically restart failing services or trigger failover to a backup.
