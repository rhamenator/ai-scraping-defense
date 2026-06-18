import os
import unittest
from unittest.mock import patch

from src.security.attack_score import compute_attack_score
from src.security.risk_scoring import RiskPolicy, RiskScorer


class TestRiskScorer(unittest.TestCase):
    def test_score_combines_weighted_signals(self):
        scorer = RiskScorer(
            RiskPolicy(
                vpn_weight=0.2,
                high_frequency_weight=0.1,
                empty_user_agent_weight=0.1,
                malicious_ip_weight=0.2,
                anomaly_weight=0.2,
                geo_velocity_weight=0.1,
                impossible_travel_weight=0.05,
                auth_failure_weight=0.05,
                anomaly_threshold=0.5,
                auth_failure_threshold=2.0,
            )
        )

        score = scorer.score(
            {
                "is_vpn": 1,
                "high_freq": 1,
                "is_malicious_ip": 1,
                "anomaly_score": 0.9,
                "auth_failures": 2,
            }
        )

        self.assertGreater(score, 0.7)

    def test_env_policy_overrides_invalid_values(self):
        with patch.dict(
            os.environ,
            {
                "RISK_SCORE_WEIGHT_VPN": "0.4",
                "RISK_SCORE_AUTH_FAILURE_THRESHOLD": "bad",
            },
            clear=False,
        ):
            policy = RiskPolicy.from_env()
        self.assertEqual(policy.vpn_weight, 0.4)
        self.assertEqual(
            policy.auth_failure_threshold, RiskPolicy.auth_failure_threshold
        )


class TestAttackScore(unittest.TestCase):
    def test_high_risk_payload_scores_high(self):
        score = compute_attack_score(
            "UNION SELECT password FROM users; <script>alert(1)</script>"
        )
        self.assertGreaterEqual(score, 0.5)

    def test_empty_payload_scores_zero(self):
        self.assertEqual(compute_attack_score(""), 0.0)


if __name__ == "__main__":
    unittest.main()
