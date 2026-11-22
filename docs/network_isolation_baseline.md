# Network Isolation Baseline

This document defines the supported trust boundary model for local Compose and
Kubernetes deployments.

## Public Edge

- `nginx_proxy` in Compose
- `nginx-proxy` Kubernetes Service (`LoadBalancer`)
- Helm ingress resources and the legacy nginx `LoadBalancer` service

These are the only components intended to accept untrusted internet traffic by
default.

## Published ports bind to loopback by default

In `docker-compose.yaml` only `nginx_proxy` (80/443) publishes on every interface. All other published ports
(operator surfaces, development endpoints, data stores and model servers) bind to `127.0.0.1` through
`${PUBLISH_ADDRESS:-127.0.0.1}`. To reach them from another machine, put them behind a VPN, bastion or SSH tunnel; if you
must publish on a specific private interface, set `PUBLISH_ADDRESS` to that interface's address, never to `0.0.0.0` on an
internet-facing host. `test/deploy/test_compose_port_bindings.py` enforces this.

## Operator Access Only

These services may be published for trusted operators, but must not be exposed
to the public internet:

- `admin_ui`
- `cloud_dashboard`
- `prometheus`
- `grafana`
- `traefik`

Treat them as VPN, bastion, or private-subnet endpoints.

## Development-Only Published Endpoints

These ports exist for local development, demos, or CI integration and should
not be internet-exposed in production:

- `mailhog`
- `mock_external_api`
- `apache_proxy`
- `config_recommender`
- `cloud_proxy`
- `prompt_router`
- `postgres`
- `redis`
- `llama3`
- `mixtral`

## Internal-Only Services

These services must remain private behind ingress and service discovery:

- `ai_service`
- `escalation_engine`
- `tarpit_api`
- `captcha_service`
- `blocklist_sync`
- `fail2ban`
- `suricata`
- `watchtower`

## Enforcement

- `scripts/security/run_static_security_checks.py` validates:
  - which Compose services may publish ports
  - that internal-only services do not publish host ports
  - that Kubernetes Services remain `ClusterIP` unless explicitly marked public
  - that Kubernetes workloads do not use `hostPort`
  - that Helm defaults keep internal services on `ClusterIP`

- `test/test_security_baselines.py` mirrors the same exposure matrix.
