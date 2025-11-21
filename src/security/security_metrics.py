"""Security-specific metrics collection and KPI tracking.

This module provides security-focused metrics collection, KPI calculation,
and security scorecard functionality for monitoring the security posture
of the AI Scraping Defense system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.shared.metrics import (
    SECURITY_ACTIVE_SESSIONS,
    SECURITY_ACTIVE_THREATS,
    SECURITY_ALERTS_PENDING,
    SECURITY_ANOMALIES_DETECTED,
    SECURITY_ANOMALY_SCORE_DISTRIBUTION,
    SECURITY_ATTACK_SCORE_DISTRIBUTION,
    SECURITY_ATTACKS_BLOCKED,
    SECURITY_AUTH_FAILURES,
    SECURITY_AUTHZ_DENIALS,
    SECURITY_BLOCKED_IPS,
    SECURITY_CAPTCHA_FAILURES,
    SECURITY_CAPTCHA_SUCCESSES,
    SECURITY_COMPLIANCE_SCORE,
    SECURITY_COMPLIANCE_VIOLATIONS,
    SECURITY_DATA_EXFILTRATION_ATTEMPTS,
    SECURITY_DETECTION_COVERAGE,
    SECURITY_DETECTION_LATENCY,
    SECURITY_FALSE_POSITIVE_RATE,
    SECURITY_FALSE_POSITIVES,
    SECURITY_HONEYPOT_HITS,
    SECURITY_INCIDENT_ESCALATIONS,
    SECURITY_INTRUSION_ATTEMPTS,
    SECURITY_IP_BLOCKS,
    SECURITY_MEAN_TIME_TO_DETECT,
    SECURITY_MEAN_TIME_TO_REMEDIATE,
    SECURITY_MEAN_TIME_TO_RESPOND,
    SECURITY_MITIGATION_TIME,
    SECURITY_POLICY_UPDATES,
    SECURITY_POLICY_VERSION,
    SECURITY_QUARANTINED_REQUESTS,
    SECURITY_RATE_LIMIT_VIOLATIONS,
    SECURITY_RESPONSE_READINESS,
    SECURITY_RESPONSE_TIME,
    SECURITY_RISK_SCORE_DISTRIBUTION,
    SECURITY_SUSPICIOUS_PATTERNS,
    SECURITY_THREAT_LEVEL,
    SECURITY_THREAT_SCORE_DISTRIBUTION,
    SECURITY_THREATS_DETECTED,
    SECURITY_TRUE_POSITIVE_RATE,
    SECURITY_TRUE_POSITIVES,
    SECURITY_VULNERABILITY_COUNT,
    SECURITY_WAF_RULES_TRIGGERED,
    increment_counter_metric,
    observe_histogram_metric,
    set_gauge_metric,
)

logger = logging.getLogger(__name__)


@dataclass
class SecurityKPIs:
    """Container for security Key Performance Indicators."""

    # Detection effectiveness
    total_threats_detected: int = 0
    total_attacks_blocked: int = 0
    false_positive_rate: float = 0.0
    true_positive_rate: float = 0.0
    detection_accuracy: float = 0.0

    # Response metrics
    mean_time_to_detect: float = 0.0
    mean_time_to_respond: float = 0.0
    mean_time_to_remediate: float = 0.0
    
    # Security posture
    current_threat_level: int = 0
    active_threats: int = 0
    blocked_ips: int = 0
    compliance_score: float = 0.0
    vulnerability_count: int = 0
    
    # Authentication & Authorization
    auth_failure_rate: float = 0.0
    authz_denial_rate: float = 0.0
    active_sessions: int = 0
    
    # Incident management
    pending_alerts: int = 0
    escalated_incidents: int = 0
    
    # Timestamp
    calculated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SecurityScorecard:
    """Comprehensive security scorecard with multiple dimensions."""

    overall_score: float = 0.0
    detection_score: float = 0.0
    response_score: float = 0.0
    prevention_score: float = 0.0
    compliance_score: float = 0.0
    readiness_score: float = 0.0
    
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    kpis: Optional[SecurityKPIs] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)


class SecurityMetricsCollector:
    """Collector for security metrics and KPI calculations."""

    def __init__(self):
        self._detection_times: List[float] = []
        self._response_times: List[float] = []
        self._remediation_times: List[float] = []
        self._max_history = 1000  # Keep last 1000 events for rolling averages

    def record_attack_blocked(
        self,
        attack_type: str,
        severity: str,
        score: Optional[float] = None,
    ) -> None:
        """Record a blocked attack event."""
        increment_counter_metric(
            SECURITY_ATTACKS_BLOCKED,
            labels={"attack_type": attack_type, "severity": severity},
        )
        if score is not None:
            observe_histogram_metric(
                SECURITY_ATTACK_SCORE_DISTRIBUTION,
                score,
                labels={"attack_type": attack_type},
            )
        logger.info(
            f"Attack blocked: type={attack_type}, severity={severity}, score={score}"
        )

    def record_threat_detected(
        self,
        threat_type: str,
        source: str,
        score: Optional[float] = None,
    ) -> None:
        """Record a detected security threat."""
        increment_counter_metric(
            SECURITY_THREATS_DETECTED,
            labels={"threat_type": threat_type, "source": source},
        )
        if score is not None:
            observe_histogram_metric(
                SECURITY_THREAT_SCORE_DISTRIBUTION,
                score,
                labels={"score_type": threat_type},
            )

    def record_auth_failure(
        self,
        auth_method: str,
        failure_reason: str,
    ) -> None:
        """Record an authentication failure."""
        increment_counter_metric(
            SECURITY_AUTH_FAILURES,
            labels={"auth_method": auth_method, "failure_reason": failure_reason},
        )

    def record_authz_denial(
        self,
        resource: str,
        action: str,
    ) -> None:
        """Record an authorization denial."""
        increment_counter_metric(
            SECURITY_AUTHZ_DENIALS,
            labels={"resource": resource, "action": action},
        )

    def record_rate_limit_violation(
        self,
        endpoint: str,
        limit_type: str,
    ) -> None:
        """Record a rate limit violation."""
        increment_counter_metric(
            SECURITY_RATE_LIMIT_VIOLATIONS,
            labels={"endpoint": endpoint, "limit_type": limit_type},
        )

    def record_captcha_result(
        self,
        captcha_type: str,
        success: bool,
        failure_reason: Optional[str] = None,
    ) -> None:
        """Record CAPTCHA verification result."""
        if success:
            increment_counter_metric(
                SECURITY_CAPTCHA_SUCCESSES,
                labels={"captcha_type": captcha_type},
            )
        else:
            increment_counter_metric(
                SECURITY_CAPTCHA_FAILURES,
                labels={
                    "captcha_type": captcha_type,
                    "failure_reason": failure_reason or "unknown",
                },
            )

    def record_honeypot_hit(
        self,
        honeypot_type: str,
        ip_reputation: str = "unknown",
    ) -> None:
        """Record a honeypot trap activation."""
        increment_counter_metric(
            SECURITY_HONEYPOT_HITS,
            labels={"honeypot_type": honeypot_type, "ip_reputation": ip_reputation},
        )

    def record_audit_event(
        self,
        event_category: str,
        severity: str,
    ) -> None:
        """Record a security audit event."""
        increment_counter_metric(
            SECURITY_AUDIT_EVENTS,
            labels={"event_category": event_category, "severity": severity},
        )

    def record_compliance_violation(
        self,
        policy_type: str,
        severity: str,
    ) -> None:
        """Record a compliance policy violation."""
        increment_counter_metric(
            SECURITY_COMPLIANCE_VIOLATIONS,
            labels={"policy_type": policy_type, "severity": severity},
        )

    def record_suspicious_pattern(
        self,
        pattern_type: str,
    ) -> None:
        """Record detection of suspicious activity pattern."""
        increment_counter_metric(
            SECURITY_SUSPICIOUS_PATTERNS,
            labels={"pattern_type": pattern_type},
        )

    def record_ip_block(
        self,
        block_reason: str,
        duration: str = "permanent",
    ) -> None:
        """Record an IP being blocked."""
        increment_counter_metric(
            SECURITY_IP_BLOCKS,
            labels={"block_reason": block_reason, "duration": duration},
        )

    def record_waf_rule_trigger(
        self,
        rule_id: str,
        severity: str,
    ) -> None:
        """Record a WAF rule being triggered."""
        increment_counter_metric(
            SECURITY_WAF_RULES_TRIGGERED,
            labels={"rule_id": rule_id, "severity": severity},
        )

    def record_intrusion_attempt(
        self,
        attack_vector: str,
        severity: str,
    ) -> None:
        """Record an intrusion attempt."""
        increment_counter_metric(
            SECURITY_INTRUSION_ATTEMPTS,
            labels={"attack_vector": attack_vector, "severity": severity},
        )

    def record_exfiltration_attempt(
        self,
        detection_method: str,
    ) -> None:
        """Record a data exfiltration attempt."""
        increment_counter_metric(
            SECURITY_DATA_EXFILTRATION_ATTEMPTS,
            labels={"detection_method": detection_method},
        )

    def record_anomaly(
        self,
        anomaly_type: str,
        confidence: str,
        score: Optional[float] = None,
    ) -> None:
        """Record a security anomaly detection."""
        increment_counter_metric(
            SECURITY_ANOMALIES_DETECTED,
            labels={"anomaly_type": anomaly_type, "confidence": confidence},
        )
        if score is not None:
            observe_histogram_metric(
                SECURITY_ANOMALY_SCORE_DISTRIBUTION,
                score,
                labels={"detector_type": anomaly_type},
            )

    def record_detection_result(
        self,
        detection_type: str,
        is_true_positive: bool,
    ) -> None:
        """Record whether a detection was a true or false positive."""
        if is_true_positive:
            increment_counter_metric(
                SECURITY_TRUE_POSITIVES,
                labels={"detection_type": detection_type},
            )
        else:
            increment_counter_metric(
                SECURITY_FALSE_POSITIVES,
                labels={"detection_type": detection_type},
            )

    def record_incident_escalation(
        self,
        severity: str,
        escalation_level: str,
    ) -> None:
        """Record a security incident escalation."""
        increment_counter_metric(
            SECURITY_INCIDENT_ESCALATIONS,
            labels={"severity": severity, "escalation_level": escalation_level},
        )

    def record_policy_update(
        self,
        policy_type: str,
    ) -> None:
        """Record a security policy update."""
        increment_counter_metric(
            SECURITY_POLICY_UPDATES,
            labels={"policy_type": policy_type},
        )

    def record_detection_time(
        self,
        event_type: str,
        latency_seconds: float,
    ) -> None:
        """Record time taken to detect a security event."""
        observe_histogram_metric(
            SECURITY_DETECTION_LATENCY,
            latency_seconds,
            labels={"detection_method": event_type},
        )
        self._detection_times.append(latency_seconds)
        if len(self._detection_times) > self._max_history:
            self._detection_times.pop(0)

    def record_response_time(
        self,
        event_type: str,
        duration_seconds: float,
    ) -> None:
        """Record time taken to respond to a security event."""
        observe_histogram_metric(
            SECURITY_RESPONSE_TIME,
            duration_seconds,
            labels={"event_type": event_type},
        )
        self._response_times.append(duration_seconds)
        if len(self._response_times) > self._max_history:
            self._response_times.pop(0)

    def record_mitigation_time(
        self,
        threat_type: str,
        duration_seconds: float,
    ) -> None:
        """Record time taken to mitigate a security threat."""
        observe_histogram_metric(
            SECURITY_MITIGATION_TIME,
            duration_seconds,
            labels={"threat_type": threat_type},
        )
        self._remediation_times.append(duration_seconds)
        if len(self._remediation_times) > self._max_history:
            self._remediation_times.pop(0)

    def record_risk_score(
        self,
        risk_category: str,
        score: float,
    ) -> None:
        """Record a risk score assessment."""
        observe_histogram_metric(
            SECURITY_RISK_SCORE_DISTRIBUTION,
            score,
            labels={"risk_category": risk_category},
        )

    def update_threat_level(
        self,
        level: int,
    ) -> None:
        """Update the current security threat level (0-5)."""
        set_gauge_metric(SECURITY_THREAT_LEVEL, min(max(level, 0), 5))

    def update_active_threats(
        self,
        threat_type: str,
        count: int,
    ) -> None:
        """Update count of active threats of a specific type."""
        set_gauge_metric(
            SECURITY_ACTIVE_THREATS,
            count,
            labels={"threat_type": threat_type},
        )

    def update_blocked_ips(
        self,
        block_reason: str,
        count: int,
    ) -> None:
        """Update count of blocked IPs."""
        set_gauge_metric(
            SECURITY_BLOCKED_IPS,
            count,
            labels={"block_reason": block_reason},
        )

    def update_active_sessions(
        self,
        auth_method: str,
        count: int,
    ) -> None:
        """Update count of active authenticated sessions."""
        set_gauge_metric(
            SECURITY_ACTIVE_SESSIONS,
            count,
            labels={"auth_method": auth_method},
        )

    def update_quarantined_requests(
        self,
        count: int,
    ) -> None:
        """Update count of quarantined requests under review."""
        set_gauge_metric(SECURITY_QUARANTINED_REQUESTS, count)

    def update_policy_version(
        self,
        policy_type: str,
        version: int,
    ) -> None:
        """Update the version of a security policy."""
        set_gauge_metric(
            SECURITY_POLICY_VERSION,
            version,
            labels={"policy_type": policy_type},
        )

    def update_compliance_score(
        self,
        compliance_standard: str,
        score: float,
    ) -> None:
        """Update compliance score (0-100)."""
        set_gauge_metric(
            SECURITY_COMPLIANCE_SCORE,
            min(max(score, 0), 100),
            labels={"compliance_standard": compliance_standard},
        )

    def update_vulnerability_count(
        self,
        severity: str,
        count: int,
    ) -> None:
        """Update count of known vulnerabilities."""
        set_gauge_metric(
            SECURITY_VULNERABILITY_COUNT,
            count,
            labels={"severity": severity},
        )

    def update_detection_coverage(
        self,
        coverage_category: str,
        percentage: float,
    ) -> None:
        """Update detection coverage percentage (0-100)."""
        set_gauge_metric(
            SECURITY_DETECTION_COVERAGE,
            min(max(percentage, 0), 100),
            labels={"coverage_category": coverage_category},
        )

    def update_response_readiness(
        self,
        score: float,
    ) -> None:
        """Update incident response readiness score (0-100)."""
        set_gauge_metric(SECURITY_RESPONSE_READINESS, min(max(score, 0), 100))

    def update_mean_times(
        self,
        incident_type: str = "all",
    ) -> None:
        """Update mean time metrics based on recorded events."""
        if self._detection_times:
            mttd = sum(self._detection_times) / len(self._detection_times)
            set_gauge_metric(
                SECURITY_MEAN_TIME_TO_DETECT,
                mttd,
                labels={"incident_type": incident_type},
            )

        if self._response_times:
            mttr = sum(self._response_times) / len(self._response_times)
            set_gauge_metric(
                SECURITY_MEAN_TIME_TO_RESPOND,
                mttr,
                labels={"incident_type": incident_type},
            )

        if self._remediation_times:
            mttr_remediate = sum(self._remediation_times) / len(self._remediation_times)
            set_gauge_metric(
                SECURITY_MEAN_TIME_TO_REMEDIATE,
                mttr_remediate,
                labels={"incident_type": incident_type},
            )

    def update_detection_rates(
        self,
        detection_type: str,
        true_positives: int,
        false_positives: int,
    ) -> None:
        """Update true positive and false positive rates."""
        total = true_positives + false_positives
        if total > 0:
            tpr = (true_positives / total) * 100
            fpr = (false_positives / total) * 100
            
            set_gauge_metric(
                SECURITY_TRUE_POSITIVE_RATE,
                tpr,
                labels={"detection_type": detection_type},
            )
            set_gauge_metric(
                SECURITY_FALSE_POSITIVE_RATE,
                fpr,
                labels={"detection_type": detection_type},
            )

    def update_pending_alerts(
        self,
        severity: str,
        count: int,
    ) -> None:
        """Update count of pending security alerts."""
        set_gauge_metric(
            SECURITY_ALERTS_PENDING,
            count,
            labels={"severity": severity},
        )

    def calculate_kpis(
        self,
        threats_detected: int = 0,
        attacks_blocked: int = 0,
        true_positives: int = 0,
        false_positives: int = 0,
        current_threat_level: int = 0,
        active_threats: int = 0,
        blocked_ips: int = 0,
        compliance_score: float = 0.0,
        vulnerability_count: int = 0,
        auth_failures: int = 0,
        total_auth_attempts: int = 1,
        authz_denials: int = 0,
        total_authz_checks: int = 1,
        active_sessions: int = 0,
        pending_alerts: int = 0,
        escalated_incidents: int = 0,
    ) -> SecurityKPIs:
        """Calculate current security KPIs from provided metrics."""
        total_detections = true_positives + false_positives
        
        return SecurityKPIs(
            total_threats_detected=threats_detected,
            total_attacks_blocked=attacks_blocked,
            false_positive_rate=(
                (false_positives / total_detections * 100) if total_detections > 0 else 0.0
            ),
            true_positive_rate=(
                (true_positives / total_detections * 100) if total_detections > 0 else 0.0
            ),
            detection_accuracy=(
                (true_positives / total_detections * 100) if total_detections > 0 else 0.0
            ),
            mean_time_to_detect=(
                sum(self._detection_times) / len(self._detection_times)
                if self._detection_times else 0.0
            ),
            mean_time_to_respond=(
                sum(self._response_times) / len(self._response_times)
                if self._response_times else 0.0
            ),
            mean_time_to_remediate=(
                sum(self._remediation_times) / len(self._remediation_times)
                if self._remediation_times else 0.0
            ),
            current_threat_level=current_threat_level,
            active_threats=active_threats,
            blocked_ips=blocked_ips,
            compliance_score=compliance_score,
            vulnerability_count=vulnerability_count,
            auth_failure_rate=(auth_failures / total_auth_attempts * 100),
            authz_denial_rate=(authz_denials / total_authz_checks * 100),
            active_sessions=active_sessions,
            pending_alerts=pending_alerts,
            escalated_incidents=escalated_incidents,
        )

    def generate_scorecard(
        self,
        kpis: Optional[SecurityKPIs] = None,
    ) -> SecurityScorecard:
        """Generate a comprehensive security scorecard."""
        if kpis is None:
            kpis = self.calculate_kpis()

        # Calculate component scores
        detection_score = min(
            100,
            (kpis.true_positive_rate * 0.7) + 
            ((100 - kpis.false_positive_rate) * 0.3)
        )
        
        response_score = 100.0
        if kpis.mean_time_to_detect > 0:
            # Penalize slow detection (target: < 60 seconds)
            response_score -= min(40, kpis.mean_time_to_detect / 60 * 40)
        if kpis.mean_time_to_respond > 0:
            # Penalize slow response (target: < 300 seconds)
            response_score -= min(40, kpis.mean_time_to_respond / 300 * 40)
        if kpis.mean_time_to_remediate > 0:
            # Penalize slow remediation (target: < 600 seconds)
            response_score -= min(20, kpis.mean_time_to_remediate / 600 * 20)

        prevention_score = min(
            100,
            (kpis.total_attacks_blocked / max(1, kpis.total_threats_detected) * 100) * 0.6 +
            ((100 - kpis.current_threat_level * 20) * 0.4)
        )

        compliance_score = kpis.compliance_score

        readiness_score = 100.0
        if kpis.vulnerability_count > 0:
            readiness_score -= min(50, kpis.vulnerability_count * 5)
        if kpis.pending_alerts > 10:
            readiness_score -= min(30, (kpis.pending_alerts - 10) * 2)

        overall_score = (
            detection_score * 0.25 +
            response_score * 0.25 +
            prevention_score * 0.20 +
            compliance_score * 0.15 +
            readiness_score * 0.15
        )

        # Generate insights
        strengths = []
        weaknesses = []
        recommendations = []

        if detection_score > 80:
            strengths.append("High detection accuracy")
        elif detection_score < 60:
            weaknesses.append("Low detection accuracy")
            recommendations.append("Review and tune detection rules to reduce false positives")

        if response_score > 80:
            strengths.append("Fast incident response")
        elif response_score < 60:
            weaknesses.append("Slow incident response times")
            recommendations.append("Automate response workflows and improve alerting")

        if prevention_score > 80:
            strengths.append("Effective attack prevention")
        elif prevention_score < 60:
            weaknesses.append("Insufficient attack prevention")
            recommendations.append("Strengthen preventive controls and update WAF rules")

        if compliance_score > 80:
            strengths.append("Good compliance posture")
        elif compliance_score < 60:
            weaknesses.append("Compliance gaps identified")
            recommendations.append("Address compliance violations and update policies")

        if readiness_score < 70:
            weaknesses.append("System readiness concerns")
            recommendations.append("Remediate vulnerabilities and clear alert backlog")

        return SecurityScorecard(
            overall_score=overall_score,
            detection_score=detection_score,
            response_score=response_score,
            prevention_score=prevention_score,
            compliance_score=compliance_score,
            readiness_score=readiness_score,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
            kpis=kpis,
        )


# Global singleton instance
_security_metrics_collector: Optional[SecurityMetricsCollector] = None


def get_security_metrics_collector() -> SecurityMetricsCollector:
    """Get or create the global security metrics collector instance."""
    global _security_metrics_collector
    if _security_metrics_collector is None:
        _security_metrics_collector = SecurityMetricsCollector()
    return _security_metrics_collector


__all__ = [
    "SecurityKPIs",
    "SecurityScorecard",
    "SecurityMetricsCollector",
    "get_security_metrics_collector",
]
