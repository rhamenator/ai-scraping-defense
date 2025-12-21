"""
Escalation engine for AI scraping defense.

This module contains the core logic for detecting and responding to AI scraping attempts.
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class EscalationEngine:
    """
    Engine for escalating responses to detected AI scraping attempts.
    
    This class analyzes request patterns and determines appropriate responses
    based on various signals including user agent, request frequency, and behavior.
    """
    
    # Known AI scraper user agents
    AI_USER_AGENTS = {
        'GPTBot',
        'ChatGPT-User',
        'Google-Extended',
        'anthropic-ai',
        'Claude-Web',
        'ClaudeBot',
        'cohere-ai',
        'Omgilibot',
        'Diffbot',
        'Bytespider',
        'PerplexityBot',
        'YouBot',
    }
    
    # Suspicious patterns in user agents
    SUSPICIOUS_PATTERNS = [
        r'bot',
        r'crawler',
        r'spider',
        r'scraper',
        r'python-requests',
        r'curl',
        r'wget',
        r'http\.client',
        r'scrapy',
        r'beautifulsoup',
    ]
    
    # Disallowed paths that should not be accessed by scrapers
    DISALLOWED_PATHS = {
        '/admin',
        '/api/internal',
        '/private',
        '/user/settings',
    }
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the escalation engine.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.request_history: Dict[str, List[datetime]] = {}
        self.blocked_ips: Set[str] = set()
        self.warning_ips: Set[str] = set()
        
    def analyze_request(self, request_data: Dict) -> Dict:
        """
        Analyze a request and determine the appropriate response level.
        
        Args:
            request_data: Dictionary containing request information including:
                - user_agent: User agent string
                - ip_address: Client IP address
                - path: Request path
                - referer: Referer header
                - timestamp: Request timestamp
                
        Returns:
            Dictionary containing:
                - threat_level: 0-100 threat score
                - action: Recommended action (allow, warn, block)
                - reasons: List of detection reasons
        """
        threat_level = 0
        reasons = []
        
        user_agent = request_data.get('user_agent', '')
        ip_address = request_data.get('ip_address', '')
        path = request_data.get('path', '')
        
        # Check if IP is already blocked
        if ip_address in self.blocked_ips:
            return {
                'threat_level': 100,
                'action': 'block',
                'reasons': ['IP previously blocked']
            }
        
        # Check for known AI scrapers
        if self._is_ai_scraper(user_agent):
            threat_level += 40
            reasons.append('Known AI scraper user agent detected')
        
        # Check for suspicious patterns
        if self._has_suspicious_patterns(user_agent):
            threat_level += 30
            reasons.append('Suspicious user agent pattern detected')
        
        # Check request frequency
        frequency_score = self._check_request_frequency(ip_address, request_data.get('timestamp'))
        if frequency_score > 0:
            threat_level += frequency_score
            reasons.append(f'High request frequency detected (score: {frequency_score})')
        
        # Check for disallowed path access
        if self._is_disallowed_path(path):
            threat_level += 30
            reasons.append('Access to disallowed path')
        
        # Check referer header
        referer_score = self._analyze_referer(request_data.get('referer', ''), request_data.get('host', ''))
        if referer_score > 0:
            threat_level += referer_score
            reasons.append('Suspicious or missing referer header')
        
        # Determine action based on threat level
        if threat_level >= 70:
            action = 'block'
            self.blocked_ips.add(ip_address)
        elif threat_level >= 40:
            action = 'warn'
            self.warning_ips.add(ip_address)
        else:
            action = 'allow'
        
        return {
            'threat_level': min(threat_level, 100),
            'action': action,
            'reasons': reasons
        }
    
    def _is_ai_scraper(self, user_agent: str) -> bool:
        """
        Check if user agent matches known AI scrapers.
        
        Args:
            user_agent: User agent string
            
        Returns:
            True if matches known AI scraper
        """
        if not user_agent:
            return False
        
        user_agent_lower = user_agent.lower()
        return any(bot.lower() in user_agent_lower for bot in self.AI_USER_AGENTS)
    
    def _has_suspicious_patterns(self, user_agent: str) -> bool:
        """
        Check if user agent contains suspicious patterns.
        
        Args:
            user_agent: User agent string
            
        Returns:
            True if suspicious patterns found
        """
        if not user_agent:
            return True  # Empty user agent is suspicious
        
        user_agent_lower = user_agent.lower()
        return any(re.search(pattern, user_agent_lower) for pattern in self.SUSPICIOUS_PATTERNS)
    
    def _check_request_frequency(self, ip_address: str, timestamp: Optional[datetime] = None) -> int:
        """
        Check request frequency for an IP address.
        
        Args:
            ip_address: Client IP address
            timestamp: Request timestamp (defaults to now)
            
        Returns:
            Threat score based on frequency (0-30)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Initialize history for new IPs
        if ip_address not in self.request_history:
            self.request_history[ip_address] = []
        
        # Add current request
        self.request_history[ip_address].append(timestamp)
        
        # Clean old requests (older than 1 minute)
        cutoff = timestamp.timestamp() - 60
        self.request_history[ip_address] = [
            ts for ts in self.request_history[ip_address]
            if ts.timestamp() > cutoff
        ]
        
        # Calculate score based on request count
        request_count = len(self.request_history[ip_address])
        
        if request_count > 100:
            return 30
        elif request_count > 50:
            return 20
        elif request_count > 20:
            return 10
        
        return 0
    
    def _is_disallowed_path(self, path: str) -> bool:
        """
        Check if path is in the disallowed list.
        
        Args:
            path: Request path
            
        Returns:
            True if path is disallowed
        """
        if not path:
            return False
        
        # Check exact matches
        if path in self.DISALLOWED_PATHS:
            return True
        
        # Check prefix matches
        try:
            return any(path.startswith(disallowed) for disallowed in self.DISALLOWED_PATHS)
        except Exception as e:
            logger.debug('Error checking disallowed path: %s', e)
            return False
    
    def _analyze_referer(self, referer: str, host: str) -> int:
        """
        Analyze referer header for suspicious patterns.
        
        Args:
            referer: Referer header value
            host: Request host
            
        Returns:
            Threat score (0-20)
        """
        # Missing referer is somewhat suspicious
        if not referer:
            return 10
        
        # Check if referer is from same domain
        try:
            referer_domain = urlparse(referer).netloc
            if referer_domain and referer_domain != host:
                return 15
        except Exception as e:
            logger.debug('Error parsing referer URL: %s', e)
            return 10
        
        return 0
    
    def get_escalation_response(self, action: str, threat_level: int) -> Dict:
        """
        Get the appropriate HTTP response for an escalation action.
        
        Args:
            action: Action to take (allow, warn, block)
            threat_level: Threat level score
            
        Returns:
            Dictionary containing response details
        """
        if action == 'block':
            return {
                'status_code': 403,
                'message': 'Access denied',
                'headers': {
                    'X-Threat-Level': str(threat_level),
                    'X-Action': 'blocked'
                }
            }
        elif action == 'warn':
            return {
                'status_code': 200,
                'message': 'Warning: Suspicious activity detected',
                'headers': {
                    'X-Threat-Level': str(threat_level),
                    'X-Action': 'warned',
                    'X-Warning': 'Your activity appears suspicious. Continued abuse will result in blocking.'
                }
            }
        else:
            return {
                'status_code': 200,
                'message': 'OK',
                'headers': {
                    'X-Threat-Level': str(threat_level),
                    'X-Action': 'allowed'
                }
            }
    
    def reset_ip_status(self, ip_address: str):
        """
        Reset the status for an IP address.
        
        Args:
            ip_address: IP address to reset
        """
        self.blocked_ips.discard(ip_address)
        self.warning_ips.discard(ip_address)
        if ip_address in self.request_history:
            del self.request_history[ip_address]
    
    def get_statistics(self) -> Dict:
        """
        Get current statistics about the escalation engine.
        
        Returns:
            Dictionary containing statistics
        """
        return {
            'blocked_ips': len(self.blocked_ips),
            'warning_ips': len(self.warning_ips),
            'tracked_ips': len(self.request_history),
            'total_requests_tracked': sum(len(requests) for requests in self.request_history.values())
        }


def extract_features(request_data: Dict) -> Dict:
    """
    Extract features from request data for analysis.
    
    Args:
        request_data: Raw request data
        
    Returns:
        Dictionary of extracted features
    """
    features = {}
    
    # Extract user agent features
    user_agent = request_data.get('user_agent', '')
    features['user_agent_length'] = len(user_agent)
    features['has_user_agent'] = bool(user_agent)
    
    # Extract path features
    path = request_data.get('path', '')
    features['path_length'] = len(path)
    features['path_depth'] = path.count('/')
    
    # Extract timestamp features
    try:
        timestamp = request_data.get('timestamp')
        if timestamp:
            features['hour_of_day'] = timestamp.hour
            features['day_of_week'] = timestamp.weekday()
    except Exception as e:
        logger.debug('Error extracting timestamp features: %s', e)
    
    return features
