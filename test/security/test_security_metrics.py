"""Tests for security metrics collection and KPI tracking."""

import unittest
from datetime import datetime

from src.security.security_metrics import (
    SecurityKPIs,
    SecurityMetricsCollector,
    SecurityScorecard,
    get_security_metrics_collector,
)


class TestSecurityMetricsCollector(unittest.TestCase):
    """Test the SecurityMetricsCollector class."""

    def setUp(self):
        """Create a fresh collector for each test."""
        self.collector = SecurityMetricsCollector()

    def test_record_attack_blocked(self):
        """Test recording blocked attacks."""
        self.collector.record_attack_blocked("sql_injection", "high", score=0.95)
        self.collector.record_attack_blocked("xss", "medium", score=0.75)
        # No assertion on metrics values, just ensure no exceptions

    def test_record_threat_detected(self):
        """Test recording detected threats."""
        self.collector.record_threat_detected("bot", "escalation_engine", score=0.87)
        self.collector.record_threat_detected("scraper", "behavioral", score=0.65)

    def test_record_auth_failure(self):
        """Test recording authentication failures."""
        self.collector.record_auth_failure("jwt", "invalid_token")
        self.collector.record_auth_failure("basic", "wrong_password")

    def test_record_authz_denial(self):
        """Test recording authorization denials."""
        self.collector.record_authz_denial("/admin", "read")
        self.collector.record_authz_denial("/api/users", "delete")

    def test_record_rate_limit_violation(self):
        """Test recording rate limit violations."""
        self.collector.record_rate_limit_violation("/api/query", "ip_based")
        self.collector.record_rate_limit_violation("/webhook", "global")

    def test_record_captcha_result(self):
        """Test recording CAPTCHA results."""
        self.collector.record_captcha_result("recaptcha", True)
        self.collector.record_captcha_result("hcaptcha", False, "timeout")

    def test_record_honeypot_hit(self):
        """Test recording honeypot hits."""
        self.collector.record_honeypot_hit("fake_admin", "malicious")
        self.collector.record_honeypot_hit("hidden_form", "unknown")

    def test_record_audit_event(self):
        """Test recording audit events."""
        self.collector.record_audit_event("access_control", "info")
        self.collector.record_audit_event("policy_change", "warning")

    def test_record_compliance_violation(self):
        """Test recording compliance violations."""
        self.collector.record_compliance_violation("GDPR", "medium")
        self.collector.record_compliance_violation("SOC2", "high")

    def test_record_suspicious_pattern(self):
        """Test recording suspicious patterns."""
        self.collector.record_suspicious_pattern("rapid_requests")
        self.collector.record_suspicious_pattern("unusual_user_agent")

    def test_record_ip_block(self):
        """Test recording IP blocks."""
        self.collector.record_ip_block("malicious_activity", "24h")
        self.collector.record_ip_block("rate_limit_exceeded", "1h")

    def test_record_waf_rule_trigger(self):
        """Test recording WAF rule triggers."""
        self.collector.record_waf_rule_trigger("SQL_001", "high")
        self.collector.record_waf_rule_trigger("XSS_042", "medium")

    def test_record_intrusion_attempt(self):
        """Test recording intrusion attempts."""
        self.collector.record_intrusion_attempt("path_traversal", "high")
        self.collector.record_intrusion_attempt("command_injection", "critical")

    def test_record_exfiltration_attempt(self):
        """Test recording data exfiltration attempts."""
        self.collector.record_exfiltration_attempt("unusual_data_transfer")
        self.collector.record_exfiltration_attempt("suspicious_export")

    def test_record_anomaly(self):
        """Test recording anomalies."""
        self.collector.record_anomaly("sequence", "high", score=0.88)
        self.collector.record_anomaly("behavioral", "medium", score=0.62)

    def test_record_detection_result(self):
        """Test recording detection results."""
        self.collector.record_detection_result("bot_detection", True)
        self.collector.record_detection_result("bot_detection", False)

    def test_record_incident_escalation(self):
        """Test recording incident escalations."""
        self.collector.record_incident_escalation("critical", "level_3")
        self.collector.record_incident_escalation("high", "level_2")

    def test_record_policy_update(self):
        """Test recording policy updates."""
        self.collector.record_policy_update("waf_rules")
        self.collector.record_policy_update("rate_limits")

    def test_record_detection_time(self):
        """Test recording detection times."""
        self.collector.record_detection_time("pattern_match", 0.5)
        self.collector.record_detection_time("ml_model", 1.2)
        # Verify internal state
        self.assertEqual(len(self.collector._detection_times), 2)
        self.assertAlmostEqual(self.collector._detection_times[0], 0.5)

    def test_record_response_time(self):
        """Test recording response times."""
        self.collector.record_response_time("block_ip", 2.3)
        self.collector.record_response_time("send_alert", 1.5)
        # Verify internal state
        self.assertEqual(len(self.collector._response_times), 2)
        self.assertAlmostEqual(self.collector._response_times[0], 2.3)

    def test_record_mitigation_time(self):
        """Test recording mitigation times."""
        self.collector.record_mitigation_time("rate_limit", 5.0)
        self.collector.record_mitigation_time("captcha", 3.2)
        # Verify internal state
        self.assertEqual(len(self.collector._remediation_times), 2)
        self.assertAlmostEqual(self.collector._remediation_times[0], 5.0)

    def test_record_risk_score(self):
        """Test recording risk scores."""
        self.collector.record_risk_score("ip_reputation", 0.75)
        self.collector.record_risk_score("behavioral", 0.45)

    def test_update_threat_level(self):
        """Test updating threat level."""
        self.collector.update_threat_level(3)
        # Test boundary conditions
        self.collector.update_threat_level(-1)  # Should clamp to 0
        self.collector.update_threat_level(10)  # Should clamp to 5

    def test_update_active_threats(self):
        """Test updating active threats count."""
        self.collector.update_active_threats("bot", 15)
        self.collector.update_active_threats("scraper", 7)

    def test_update_blocked_ips(self):
        """Test updating blocked IPs count."""
        self.collector.update_blocked_ips("malicious", 42)
        self.collector.update_blocked_ips("rate_limit", 18)

    def test_update_active_sessions(self):
        """Test updating active sessions count."""
        self.collector.update_active_sessions("jwt", 125)
        self.collector.update_active_sessions("oauth", 87)

    def test_update_quarantined_requests(self):
        """Test updating quarantined requests count."""
        self.collector.update_quarantined_requests(5)

    def test_update_policy_version(self):
        """Test updating policy versions."""
        self.collector.update_policy_version("waf_rules", 42)
        self.collector.update_policy_version("rate_limits", 17)

    def test_update_compliance_score(self):
        """Test updating compliance scores."""
        self.collector.update_compliance_score("GDPR", 92.5)
        self.collector.update_compliance_score("SOC2", 87.3)
        # Test boundary clamping
        self.collector.update_compliance_score("PCI-DSS", 150.0)  # Should clamp to 100
        self.collector.update_compliance_score("HIPAA", -10.0)  # Should clamp to 0

    def test_update_vulnerability_count(self):
        """Test updating vulnerability counts."""
        self.collector.update_vulnerability_count("critical", 2)
        self.collector.update_vulnerability_count("high", 5)
        self.collector.update_vulnerability_count("medium", 12)

    def test_update_detection_coverage(self):
        """Test updating detection coverage."""
        self.collector.update_detection_coverage("sql_injection", 98.5)
        self.collector.update_detection_coverage("xss", 95.0)

    def test_update_response_readiness(self):
        """Test updating response readiness score."""
        self.collector.update_response_readiness(87.5)

    def test_update_mean_times(self):
        """Test updating mean time metrics."""
        # Record some events first
        self.collector.record_detection_time("test", 1.0)
        self.collector.record_detection_time("test", 2.0)
        self.collector.record_response_time("test", 3.0)
        self.collector.record_response_time("test", 5.0)
        self.collector.record_mitigation_time("test", 4.0)
        self.collector.record_mitigation_time("test", 6.0)

        # Update gauges
        self.collector.update_mean_times("test_incident")

    def test_update_detection_rates(self):
        """Test updating detection rates."""
        self.collector.update_detection_rates("bot_detection", 95, 5)
        # With 95 TP and 5 FP: TPR = 95%, FPR = 5%

    def test_update_pending_alerts(self):
        """Test updating pending alerts count."""
        self.collector.update_pending_alerts("critical", 3)
        self.collector.update_pending_alerts("high", 12)
        self.collector.update_pending_alerts("medium", 25)

    def test_calculate_kpis_basic(self):
        """Test basic KPI calculation."""
        kpis = self.collector.calculate_kpis(
            threats_detected=100,
            attacks_blocked=95,
            true_positives=90,
            false_positives=5,
        )

        self.assertEqual(kpis.total_threats_detected, 100)
        self.assertEqual(kpis.total_attacks_blocked, 95)
        self.assertAlmostEqual(kpis.true_positive_rate, 94.74, places=1)
        self.assertAlmostEqual(kpis.false_positive_rate, 5.26, places=1)
        self.assertAlmostEqual(kpis.detection_accuracy, 94.74, places=1)

    def test_calculate_kpis_with_times(self):
        """Test KPI calculation with recorded times."""
        # Record some timing events
        self.collector.record_detection_time("test", 30.0)
        self.collector.record_detection_time("test", 60.0)
        self.collector.record_response_time("test", 120.0)
        self.collector.record_response_time("test", 180.0)
        self.collector.record_mitigation_time("test", 300.0)
        self.collector.record_mitigation_time("test", 600.0)

        kpis = self.collector.calculate_kpis()

        self.assertAlmostEqual(kpis.mean_time_to_detect, 45.0)
        self.assertAlmostEqual(kpis.mean_time_to_respond, 150.0)
        self.assertAlmostEqual(kpis.mean_time_to_remediate, 450.0)

    def test_calculate_kpis_full(self):
        """Test KPI calculation with all parameters."""
        kpis = self.collector.calculate_kpis(
            threats_detected=150,
            attacks_blocked=142,
            true_positives=135,
            false_positives=7,
            current_threat_level=2,
            active_threats=8,
            blocked_ips=47,
            compliance_score=92.5,
            vulnerability_count=3,
            auth_failures=12,
            total_auth_attempts=1000,
            authz_denials=5,
            total_authz_checks=500,
            active_sessions=125,
            pending_alerts=4,
            escalated_incidents=2,
        )

        self.assertEqual(kpis.total_threats_detected, 150)
        self.assertEqual(kpis.total_attacks_blocked, 142)
        self.assertEqual(kpis.current_threat_level, 2)
        self.assertEqual(kpis.active_threats, 8)
        self.assertEqual(kpis.blocked_ips, 47)
        self.assertAlmostEqual(kpis.compliance_score, 92.5)
        self.assertEqual(kpis.vulnerability_count, 3)
        self.assertAlmostEqual(kpis.auth_failure_rate, 1.2)
        self.assertAlmostEqual(kpis.authz_denial_rate, 1.0)
        self.assertEqual(kpis.active_sessions, 125)
        self.assertEqual(kpis.pending_alerts, 4)
        self.assertEqual(kpis.escalated_incidents, 2)
        self.assertIsInstance(kpis.calculated_at, datetime)

    def test_generate_scorecard_basic(self):
        """Test basic scorecard generation."""
        scorecard = self.collector.generate_scorecard()

        self.assertIsInstance(scorecard, SecurityScorecard)
        self.assertGreaterEqual(scorecard.overall_score, 0.0)
        self.assertLessEqual(scorecard.overall_score, 100.0)
        self.assertGreaterEqual(scorecard.detection_score, 0.0)
        self.assertGreaterEqual(scorecard.response_score, 0.0)
        self.assertGreaterEqual(scorecard.prevention_score, 0.0)
        self.assertGreaterEqual(scorecard.compliance_score, 0.0)
        self.assertGreaterEqual(scorecard.readiness_score, 0.0)
        self.assertIsInstance(scorecard.strengths, list)
        self.assertIsInstance(scorecard.weaknesses, list)
        self.assertIsInstance(scorecard.recommendations, list)
        self.assertIsInstance(scorecard.generated_at, datetime)

    def test_generate_scorecard_with_good_kpis(self):
        """Test scorecard generation with good KPIs."""
        kpis = SecurityKPIs(
            total_threats_detected=100,
            total_attacks_blocked=98,
            false_positive_rate=2.0,
            true_positive_rate=98.0,
            detection_accuracy=98.0,
            mean_time_to_detect=30.0,
            mean_time_to_respond=120.0,
            mean_time_to_remediate=300.0,
            current_threat_level=1,
            compliance_score=95.0,
            vulnerability_count=0,
            pending_alerts=2,
        )

        scorecard = self.collector.generate_scorecard(kpis)

        # Good metrics should result in high scores
        self.assertGreater(scorecard.overall_score, 80.0)
        self.assertGreater(scorecard.detection_score, 80.0)
        self.assertGreater(scorecard.prevention_score, 80.0)
        self.assertGreater(len(scorecard.strengths), 0)

    def test_generate_scorecard_with_poor_kpis(self):
        """Test scorecard generation with poor KPIs."""
        kpis = SecurityKPIs(
            total_threats_detected=100,
            total_attacks_blocked=50,
            false_positive_rate=30.0,
            true_positive_rate=70.0,
            detection_accuracy=70.0,
            mean_time_to_detect=300.0,
            mean_time_to_respond=1200.0,
            mean_time_to_remediate=3600.0,
            current_threat_level=4,
            compliance_score=65.0,
            vulnerability_count=15,
            pending_alerts=50,
        )

        scorecard = self.collector.generate_scorecard(kpis)

        # Poor metrics should result in lower scores
        self.assertLess(scorecard.overall_score, 80.0)
        self.assertGreater(len(scorecard.weaknesses), 0)
        self.assertGreater(len(scorecard.recommendations), 0)

    def test_time_history_limit(self):
        """Test that time history is limited to max_history."""
        # Record more than max_history events
        for i in range(1500):
            self.collector.record_detection_time("test", float(i))

        # Should keep only the last 1000
        self.assertEqual(len(self.collector._detection_times), 1000)
        # Last value should be 1499
        self.assertAlmostEqual(self.collector._detection_times[-1], 1499.0)

    def test_get_security_metrics_collector_singleton(self):
        """Test that get_security_metrics_collector returns a singleton."""
        collector1 = get_security_metrics_collector()
        collector2 = get_security_metrics_collector()

        self.assertIs(collector1, collector2)


class TestSecurityKPIs(unittest.TestCase):
    """Test the SecurityKPIs dataclass."""

    def test_kpis_creation(self):
        """Test creating a KPIs instance."""
        kpis = SecurityKPIs(
            total_threats_detected=100,
            total_attacks_blocked=95,
            false_positive_rate=5.0,
            true_positive_rate=95.0,
        )

        self.assertEqual(kpis.total_threats_detected, 100)
        self.assertEqual(kpis.total_attacks_blocked, 95)
        self.assertAlmostEqual(kpis.false_positive_rate, 5.0)
        self.assertAlmostEqual(kpis.true_positive_rate, 95.0)

    def test_kpis_defaults(self):
        """Test KPIs with default values."""
        kpis = SecurityKPIs()

        self.assertEqual(kpis.total_threats_detected, 0)
        self.assertEqual(kpis.total_attacks_blocked, 0)
        self.assertAlmostEqual(kpis.false_positive_rate, 0.0)
        self.assertIsInstance(kpis.calculated_at, datetime)


class TestSecurityScorecard(unittest.TestCase):
    """Test the SecurityScorecard dataclass."""

    def test_scorecard_creation(self):
        """Test creating a scorecard instance."""
        scorecard = SecurityScorecard(
            overall_score=87.5,
            detection_score=90.0,
            response_score=85.0,
            prevention_score=88.0,
            compliance_score=92.0,
            readiness_score=82.0,
            strengths=["High detection accuracy", "Fast response"],
            weaknesses=["Alert backlog"],
            recommendations=["Clear pending alerts"],
        )

        self.assertAlmostEqual(scorecard.overall_score, 87.5)
        self.assertAlmostEqual(scorecard.detection_score, 90.0)
        self.assertEqual(len(scorecard.strengths), 2)
        self.assertEqual(len(scorecard.weaknesses), 1)
        self.assertEqual(len(scorecard.recommendations), 1)

    def test_scorecard_defaults(self):
        """Test scorecard with default values."""
        scorecard = SecurityScorecard()

        self.assertAlmostEqual(scorecard.overall_score, 0.0)
        self.assertEqual(len(scorecard.strengths), 0)
        self.assertEqual(len(scorecard.weaknesses), 0)
        self.assertEqual(len(scorecard.recommendations), 0)
        self.assertIsNone(scorecard.kpis)
        self.assertIsInstance(scorecard.generated_at, datetime)


if __name__ == "__main__":
    unittest.main()
