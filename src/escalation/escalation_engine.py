"""
Escalation Engine for AI Scraping Defense

This module implements a sophisticated threat detection and response system
that monitors incoming requests and escalates defensive measures based on
detected scraping patterns and behavioral anomalies.
"""

import time
import logging
import hashlib
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
import json
import re
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


@dataclass
class ThreatMetrics:
    """Metrics for threat detection and scoring."""
    request_count: int = 0
    error_rate: float = 0.0
    pattern_violations: int = 0
    timing_anomalies: int = 0
    content_hash_diversity: float = 0.0
    user_agent_changes: int = 0
    last_request_time: float = 0.0
    first_request_time: float = 0.0
    blocked_attempts: int = 0
    challenge_failures: int = 0
    suspicious_patterns: Set[str] = field(default_factory=set)
    request_timestamps: deque = field(default_factory=lambda: deque(maxlen=100))
    accessed_paths: Set[str] = field(default_factory=set)
    referer_domains: Set[str] = field(default_factory=set)
    

@dataclass
class EscalationLevel:
    """Defines an escalation level with its thresholds and responses."""
    level: int
    name: str
    threat_score_threshold: float
    response_actions: List[str]
    rate_limit_factor: float = 1.0
    challenge_difficulty: str = "none"
    block_duration: int = 0  # seconds
    

class EscalationEngine:
    """
    Manages threat detection and escalation of defensive measures.
    
    The engine monitors request patterns, maintains threat scores for
    IP addresses and identifiers, and escalates responses based on
    detected scraping behavior.
    """
    
    # Escalation levels configuration
    ESCALATION_LEVELS = [
        EscalationLevel(
            level=0,
            name="normal",
            threat_score_threshold=0.0,
            response_actions=["allow"],
            rate_limit_factor=1.0,
            challenge_difficulty="none"
        ),
        EscalationLevel(
            level=1,
            name="suspicious",
            threat_score_threshold=30.0,
            response_actions=["log", "monitor"],
            rate_limit_factor=0.8,
            challenge_difficulty="none"
        ),
        EscalationLevel(
            level=2,
            name="elevated",
            threat_score_threshold=50.0,
            response_actions=["log", "challenge_easy"],
            rate_limit_factor=0.5,
            challenge_difficulty="easy"
        ),
        EscalationLevel(
            level=3,
            name="high",
            threat_score_threshold=70.0,
            response_actions=["log", "challenge_medium", "rate_limit"],
            rate_limit_factor=0.3,
            challenge_difficulty="medium",
            block_duration=300  # 5 minutes
        ),
        EscalationLevel(
            level=4,
            name="critical",
            threat_score_threshold=90.0,
            response_actions=["log", "challenge_hard", "strict_rate_limit"],
            rate_limit_factor=0.1,
            challenge_difficulty="hard",
            block_duration=900  # 15 minutes
        ),
        EscalationLevel(
            level=5,
            name="blocked",
            threat_score_threshold=100.0,
            response_actions=["block", "alert"],
            rate_limit_factor=0.0,
            challenge_difficulty="impossible",
            block_duration=3600  # 1 hour
        ),
    ]
    
    # Threat scoring weights
    SCORE_WEIGHTS = {
        'high_request_rate': 15.0,
        'timing_pattern': 10.0,
        'error_rate': 8.0,
        'user_agent_rotation': 12.0,
        'path_enumeration': 10.0,
        'challenge_failure': 20.0,
        'blocked_attempt': 25.0,
        'suspicious_pattern': 5.0,
        'low_content_diversity': 8.0,
        'missing_referer': 3.0,
        'suspicious_referer': 7.0,
    }
    
    # Pattern detection thresholds
    THRESHOLDS = {
        'requests_per_minute': 60,
        'requests_per_hour': 500,
        'error_rate_threshold': 0.3,
        'timing_variance_threshold': 0.1,
        'unique_paths_threshold': 50,
        'min_request_interval': 0.1,  # seconds
        'max_user_agent_changes': 3,
    }
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the Escalation Engine.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.threat_metrics: Dict[str, ThreatMetrics] = defaultdict(ThreatMetrics)
        self.threat_scores: Dict[str, float] = defaultdict(float)
        self.escalation_states: Dict[str, EscalationLevel] = {}
        self.blocked_until: Dict[str, float] = {}
        self.request_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # Pattern detection
        self.known_scraper_patterns = self._load_scraper_patterns()
        self.whitelist: Set[str] = set(self.config.get('whitelist', []))
        self.blacklist: Set[str] = set(self.config.get('blacklist', []))
        
        logger.info("Escalation Engine initialized with %d levels", 
                   len(self.ESCALATION_LEVELS))
    
    def _load_scraper_patterns(self) -> List[re.Pattern]:
        """Load known scraper patterns for detection."""
        patterns = [
            r'bot|crawler|spider|scraper',
            r'curl|wget|python-requests',
            r'headless|phantom|selenium',
            r'scrapy|beautifulsoup',
            r'automated|script',
        ]
        return [re.compile(p, re.IGNORECASE) for p in patterns]
    
    def analyze_request(self, request_data: Dict) -> Dict:
        """
        Analyze an incoming request and determine threat level.
        
        Args:
            request_data: Dictionary containing request information
                - ip: Client IP address
                - user_agent: User agent string
                - path: Request path
                - timestamp: Request timestamp
                - referer: Referer header
                - status_code: Response status code (if available)
                
        Returns:
            Dictionary containing analysis results and recommended actions
        """
        ip = request_data.get('ip', 'unknown')
        
        # Check whitelist/blacklist
        if ip in self.whitelist:
            return self._create_response(ip, 0, "whitelisted")
        if ip in self.blacklist:
            return self._create_response(ip, 5, "blacklisted")
        
        # Check if currently blocked
        if self._is_blocked(ip):
            return self._create_response(ip, 5, "currently_blocked")
        
        # Update metrics
        self._update_metrics(ip, request_data)
        
        # Calculate threat score
        threat_score = self._calculate_threat_score(ip, request_data)
        self.threat_scores[ip] = threat_score
        
        # Determine escalation level
        escalation_level = self._determine_escalation_level(threat_score)
        self.escalation_states[ip] = escalation_level
        
        # Check if we should block
        if escalation_level.block_duration > 0:
            self.blocked_until[ip] = time.time() + escalation_level.block_duration
        
        logger.info("Request from %s analyzed: threat_score=%.2f, level=%s",
                   ip, threat_score, escalation_level.name)
        
        return self._create_response(ip, escalation_level.level, "analyzed")
    
    def _update_metrics(self, ip: str, request_data: Dict):
        """Update threat metrics for the given IP."""
        metrics = self.threat_metrics[ip]
        current_time = time.time()
        
        # Update basic counters
        metrics.request_count += 1
        metrics.last_request_time = current_time
        if metrics.first_request_time == 0.0:
            metrics.first_request_time = current_time
        
        # Track timestamps
        metrics.request_timestamps.append(current_time)
        
        # Track paths
        path = request_data.get('path', '')
        if path:
            metrics.accessed_paths.add(path)
        
        # Track referer domains
        referer = request_data.get('referer', '')
        if referer:
            try:
                domain = urlparse(referer).netloc
                if domain:
                    metrics.referer_domains.add(domain)
            except Exception as e:
                logger.warning('Error parsing referer: %s', e)
        
        # Track error rate
        status_code = request_data.get('status_code', 200)
        if status_code >= 400:
            # Simple moving average for error rate
            metrics.error_rate = (metrics.error_rate * 0.9) + 0.1
        else:
            metrics.error_rate = metrics.error_rate * 0.95
        
        # Check for timing patterns
        if len(metrics.request_timestamps) >= 10:
            intervals = [
                metrics.request_timestamps[i] - metrics.request_timestamps[i-1]
                for i in range(1, len(metrics.request_timestamps))
            ]
            avg_interval = sum(intervals) / len(intervals)
            variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
            
            if variance < self.THRESHOLDS['timing_variance_threshold']:
                metrics.timing_anomalies += 1
        
        # Check for suspicious patterns
        user_agent = request_data.get('user_agent', '')
        for pattern in self.known_scraper_patterns:
            if pattern.search(user_agent):
                metrics.suspicious_patterns.add(pattern.pattern)
    
    def _calculate_threat_score(self, ip: str, request_data: Dict) -> float:
        """Calculate the threat score for an IP address."""
        metrics = self.threat_metrics[ip]
        score = 0.0
        current_time = time.time()
        
        # High request rate
        if len(metrics.request_timestamps) >= 2:
            time_window = current_time - metrics.request_timestamps[0]
            if time_window > 0:
                rate_per_minute = len(metrics.request_timestamps) / (time_window / 60)
                if rate_per_minute > self.THRESHOLDS['requests_per_minute']:
                    score += self.SCORE_WEIGHTS['high_request_rate']
        
        # Timing patterns (too regular = bot)
        if metrics.timing_anomalies > 3:
            score += self.SCORE_WEIGHTS['timing_pattern']
        
        # High error rate
        if metrics.error_rate > self.THRESHOLDS['error_rate_threshold']:
            score += self.SCORE_WEIGHTS['error_rate']
        
        # Path enumeration
        if len(metrics.accessed_paths) > self.THRESHOLDS['unique_paths_threshold']:
            score += self.SCORE_WEIGHTS['path_enumeration']
        
        # User agent rotation
        if metrics.user_agent_changes > self.THRESHOLDS['max_user_agent_changes']:
            score += self.SCORE_WEIGHTS['user_agent_rotation']
        
        # Challenge failures
        if metrics.challenge_failures > 0:
            score += self.SCORE_WEIGHTS['challenge_failure'] * metrics.challenge_failures
        
        # Blocked attempts
        if metrics.blocked_attempts > 0:
            score += self.SCORE_WEIGHTS['blocked_attempt'] * min(metrics.blocked_attempts, 3)
        
        # Suspicious patterns
        score += len(metrics.suspicious_patterns) * self.SCORE_WEIGHTS['suspicious_pattern']
        
        # Missing or suspicious referer
        referer = request_data.get('referer', '')
        if not referer and metrics.request_count > 5:
            score += self.SCORE_WEIGHTS['missing_referer']
        
        # Cap the score at 100
        return min(score, 100.0)
    
    def _determine_escalation_level(self, threat_score: float) -> EscalationLevel:
        """Determine the appropriate escalation level based on threat score."""
        for level in reversed(self.ESCALATION_LEVELS):
            if threat_score >= level.threat_score_threshold:
                return level
        return self.ESCALATION_LEVELS[0]
    
    def _is_blocked(self, ip: str) -> bool:
        """Check if an IP is currently blocked."""
        if ip in self.blocked_until:
            if time.time() < self.blocked_until[ip]:
                self.threat_metrics[ip].blocked_attempts += 1
                return True
            else:
                # Block expired
                del self.blocked_until[ip]
        return False
    
    def _create_response(self, ip: str, level: int, reason: str) -> Dict:
        """Create a response dictionary with escalation information."""
        escalation_level = None
        for lvl in self.ESCALATION_LEVELS:
            if lvl.level == level:
                escalation_level = lvl
                break
        
        if escalation_level is None:
            escalation_level = self.ESCALATION_LEVELS[0]
        
        metrics = self.threat_metrics[ip]
        
        return {
            'ip': ip,
            'threat_score': self.threat_scores.get(ip, 0.0),
            'escalation_level': level,
            'escalation_name': escalation_level.name,
            'actions': escalation_level.response_actions,
            'rate_limit_factor': escalation_level.rate_limit_factor,
            'challenge_difficulty': escalation_level.challenge_difficulty,
            'blocked': level >= 5,
            'blocked_until': self.blocked_until.get(ip, 0),
            'reason': reason,
            'metrics': {
                'request_count': metrics.request_count,
                'error_rate': metrics.error_rate,
                'timing_anomalies': metrics.timing_anomalies,
                'accessed_paths': len(metrics.accessed_paths),
                'suspicious_patterns': len(metrics.suspicious_patterns),
            }
        }
    
    def record_challenge_result(self, ip: str, success: bool):
        """Record the result of a challenge."""
        metrics = self.threat_metrics[ip]
        if not success:
            metrics.challenge_failures += 1
            # Increase threat score on challenge failure
            current_score = self.threat_scores.get(ip, 0.0)
            self.threat_scores[ip] = min(current_score + 15.0, 100.0)
            logger.warning("Challenge failed for %s, threat score increased to %.2f",
                         ip, self.threat_scores[ip])
    
    def get_current_state(self, ip: str) -> Dict:
        """Get the current escalation state for an IP."""
        if ip in self.escalation_states:
            level = self.escalation_states[ip]
            return self._create_response(ip, level.level, "current_state")
        return self._create_response(ip, 0, "no_state")
    
    def reset_ip(self, ip: str):
        """Reset all metrics and state for an IP address."""
        if ip in self.threat_metrics:
            del self.threat_metrics[ip]
        if ip in self.threat_scores:
            del self.threat_scores[ip]
        if ip in self.escalation_states:
            del self.escalation_states[ip]
        if ip in self.blocked_until:
            del self.blocked_until[ip]
        logger.info("Reset state for IP: %s", ip)
    
    def add_to_whitelist(self, ip: str):
        """Add an IP to the whitelist."""
        self.whitelist.add(ip)
        self.reset_ip(ip)
        logger.info("Added %s to whitelist", ip)
    
    def add_to_blacklist(self, ip: str):
        """Add an IP to the blacklist."""
        self.blacklist.add(ip)
        logger.info("Added %s to blacklist", ip)
    
    def remove_from_whitelist(self, ip: str):
        """Remove an IP from the whitelist."""
        self.whitelist.discard(ip)
        logger.info("Removed %s from whitelist", ip)
    
    def remove_from_blacklist(self, ip: str):
        """Remove an IP from the blacklist."""
        self.blacklist.discard(ip)
        logger.info("Removed %s from blacklist", ip)
    
    def get_statistics(self) -> Dict:
        """Get overall statistics about the escalation engine."""
        total_ips = len(self.threat_metrics)
        
        level_counts = defaultdict(int)
        for ip, state in self.escalation_states.items():
            level_counts[state.name] += 1
        
        total_requests = sum(m.request_count for m in self.threat_metrics.values())
        total_blocked = len(self.blocked_until)
        
        return {
            'total_tracked_ips': total_ips,
            'total_requests': total_requests,
            'currently_blocked': total_blocked,
            'whitelisted': len(self.whitelist),
            'blacklisted': len(self.blacklist),
            'escalation_levels': dict(level_counts),
            'average_threat_score': (
                sum(self.threat_scores.values()) / len(self.threat_scores)
                if self.threat_scores else 0.0
            ),
        }
    
    def cleanup_old_data(self, max_age_hours: int = 24):
        """Clean up old tracking data to prevent memory bloat."""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        ips_to_remove = []
        for ip, metrics in self.threat_metrics.items():
            if current_time - metrics.last_request_time > max_age_seconds:
                ips_to_remove.append(ip)
        
        for ip in ips_to_remove:
            self.reset_ip(ip)
        
        logger.info("Cleaned up %d old IP records", len(ips_to_remove))
        return len(ips_to_remove)
