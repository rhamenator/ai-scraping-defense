"""GraphQL security controls for query complexity, rate limiting, and introspection protection.

This module provides comprehensive security controls for GraphQL endpoints:
- Query complexity analysis to prevent expensive queries
- Query depth limiting to prevent deeply nested queries
- Field limiting to prevent overly broad queries
- Rate limiting specific to GraphQL operations
- Introspection protection for production environments
- Custom validation rules for GraphQL queries
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


class GraphQLSecurityError(Exception):
    """Base exception for GraphQL security violations."""

    pass


class QueryComplexityError(GraphQLSecurityError):
    """Raised when query complexity exceeds the allowed threshold."""

    pass


class QueryDepthError(GraphQLSecurityError):
    """Raised when query depth exceeds the allowed threshold."""

    pass


class IntrospectionDisabledError(GraphQLSecurityError):
    """Raised when introspection is attempted in a protected environment."""

    pass


class GraphQLRateLimitError(GraphQLSecurityError):
    """Raised when GraphQL rate limit is exceeded."""

    pass


class EnvironmentMode(str, Enum):
    """Environment modes for introspection control."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class GraphQLSecurityConfig:
    """Configuration for GraphQL security controls."""

    max_query_complexity: int = 1000
    max_query_depth: int = 10
    max_field_count: int = 100
    enable_introspection: bool = True
    environment: EnvironmentMode = EnvironmentMode.DEVELOPMENT
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds
    # Cost multipliers for different field types
    list_multiplier: int = 10
    connection_multiplier: int = 10
    mutation_multiplier: int = 5

    @classmethod
    def from_env(cls) -> "GraphQLSecurityConfig":
        """Create configuration from environment variables."""
        env_mode = os.getenv("ENVIRONMENT", "development").lower()
        if env_mode in ["prod", "production"]:
            environment = EnvironmentMode.PRODUCTION
            enable_introspection = False
        elif env_mode in ["stage", "staging"]:
            environment = EnvironmentMode.STAGING
            enable_introspection = (
                os.getenv("GRAPHQL_INTROSPECTION", "false").lower() == "true"
            )
        else:
            environment = EnvironmentMode.DEVELOPMENT
            enable_introspection = True

        return cls(
            max_query_complexity=int(os.getenv("GRAPHQL_MAX_COMPLEXITY", "1000")),
            max_query_depth=int(os.getenv("GRAPHQL_MAX_DEPTH", "10")),
            max_field_count=int(os.getenv("GRAPHQL_MAX_FIELDS", "100")),
            enable_introspection=enable_introspection,
            environment=environment,
            rate_limit_requests=int(os.getenv("GRAPHQL_RATE_LIMIT", "100")),
            rate_limit_window=int(os.getenv("GRAPHQL_RATE_WINDOW", "60")),
            list_multiplier=int(os.getenv("GRAPHQL_LIST_MULTIPLIER", "10")),
            connection_multiplier=int(os.getenv("GRAPHQL_CONNECTION_MULTIPLIER", "10")),
            mutation_multiplier=int(os.getenv("GRAPHQL_MUTATION_MULTIPLIER", "5")),
        )


class QueryComplexityAnalyzer:
    """Analyzes GraphQL query complexity to prevent resource exhaustion."""

    def __init__(self, config: GraphQLSecurityConfig):
        self.config = config

    def calculate_complexity(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> int:
        """Calculate the complexity score of a GraphQL query.

        This is a simplified implementation that counts:
        - Each field selection
        - Multiplies by depth
        - Applies cost multipliers for lists, connections, and mutations
        """
        complexity = 0
        depth = 0
        max_depth = 0
        field_count = 0

        # Simple parsing - count braces for depth and fields
        in_string = False
        escape_next = False

        for i, char in enumerate(query):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
                max_depth = max(max_depth, depth)
            elif char == "}":
                depth = max(0, depth - 1)
            elif char.isalnum() and i > 0 and not query[i - 1].isalnum():
                # Rough field count
                field_count += 1

        # Base complexity from fields and depth
        complexity = field_count * (max_depth + 1)

        # Check for expensive patterns
        query_lower = query.lower()

        # Mutations are more expensive
        if "mutation" in query_lower:
            complexity *= self.config.mutation_multiplier

        # Lists and connections are expensive
        if "connection" in query_lower or "edges" in query_lower:
            complexity *= self.config.connection_multiplier
        elif any(
            pattern in query_lower
            for pattern in ["list", "[]", "first:", "last:", "limit:"]
        ):
            complexity *= self.config.list_multiplier // 2

        return complexity

    def calculate_depth(self, query: str) -> int:
        """Calculate the maximum depth of a GraphQL query."""
        depth = 0
        max_depth = 0
        in_string = False
        escape_next = False

        for char in query:
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
                max_depth = max(max_depth, depth)
            elif char == "}":
                depth = max(0, depth - 1)

        return max_depth

    def count_fields(self, query: str) -> int:
        """Count the number of fields in a GraphQL query."""
        # Simple field counting
        field_count = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(query):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            # Count alphanumeric sequences that follow non-alphanumeric chars
            if char.isalnum() and i > 0 and not query[i - 1].isalnum():
                # Skip common keywords
                if i + 5 < len(query):
                    word_start = (
                        query[i: i + 10].split()[0] if query[i:].strip() else ""
                    )
                    if word_start.lower() not in [
                        "query",
                        "mutation",
                        "fragment",
                        "on",
                        "true",
                        "false",
                        "null",
                    ]:
                        field_count += 1

        return field_count

    def validate_query(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> None:
        """Validate a GraphQL query against security constraints.

        Raises:
            QueryComplexityError: If complexity exceeds threshold
            QueryDepthError: If depth exceeds threshold
            ValueError: If field count exceeds threshold
        """
        complexity = self.calculate_complexity(query, variables)
        if complexity > self.config.max_query_complexity:
            raise QueryComplexityError(
                f"Query complexity {complexity} exceeds maximum allowed "
                f"{self.config.max_query_complexity}"
            )

        depth = self.calculate_depth(query)
        if depth > self.config.max_query_depth:
            raise QueryDepthError(
                f"Query depth {depth} exceeds maximum allowed {self.config.max_query_depth}"
            )

        field_count = self.count_fields(query)
        if field_count > self.config.max_field_count:
            raise ValueError(
                f"Query field count {field_count} exceeds maximum allowed "
                f"{self.config.max_field_count}"
            )

        logger.debug(
            "Query validation passed: complexity=%d, depth=%d, fields=%d",
            complexity,
            depth,
            field_count,
        )


class IntrospectionProtector:
    """Protects GraphQL introspection queries in production environments."""

    INTROSPECTION_KEYWORDS = {
        "__schema",
        "__type",
        "__typename",
        "__field",
        "__inputvalue",
        "__enumvalue",
        "__directive",
    }

    def __init__(self, config: GraphQLSecurityConfig):
        self.config = config

    def is_introspection_query(self, query: str) -> bool:
        """Check if a query contains introspection keywords."""
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in self.INTROSPECTION_KEYWORDS)

    def validate_introspection(self, query: str) -> None:
        """Validate that introspection is allowed for the current environment.

        Raises:
            IntrospectionDisabledError: If introspection is disabled and query uses it
        """
        if not self.config.enable_introspection and self.is_introspection_query(query):
            raise IntrospectionDisabledError(
                f"GraphQL introspection is disabled in {self.config.environment.value} environment"
            )


class GraphQLRateLimiter:
    """Rate limiter specifically for GraphQL operations."""

    def __init__(self, config: GraphQLSecurityConfig):
        self.config = config
        self._request_counts: Dict[str, Tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    def _get_client_identifier(self, request: Request) -> str:
        """Get a unique identifier for the client."""
        # Try to get user ID from auth claims
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"

        # Fall back to IP address
        if request.client:
            return f"ip:{request.client.host}"

        return "unknown"

    def _calculate_window_reset(self, now: float) -> int:
        """Calculate when the current rate limit window resets."""
        window = self.config.rate_limit_window
        return int((now // window) * window + window)

    async def _cleanup_expired(self, now: float) -> None:
        """Remove expired rate limit entries."""
        expired = [
            client_id
            for client_id, (_, reset_time) in self._request_counts.items()
            if now > reset_time
        ]
        for client_id in expired:
            del self._request_counts[client_id]

    async def check_rate_limit(self, request: Request) -> Dict[str, str]:
        """Check if the request is within rate limits.

        Returns:
            Dict with rate limit headers

        Raises:
            GraphQLRateLimitError: If rate limit is exceeded
        """
        client_id = self._get_client_identifier(request)
        now = time.time()
        window_reset = self._calculate_window_reset(now)

        async with self._lock:
            await self._cleanup_expired(now)

            count, reset_time = self._request_counts.get(client_id, (0, window_reset))

            # Reset counter if we're in a new window
            if now > reset_time:
                count, reset_time = 0, window_reset

            # Check limit
            if count >= self.config.rate_limit_requests:
                retry_after = int(reset_time - now)
                raise GraphQLRateLimitError(
                    f"GraphQL rate limit exceeded. Retry after {retry_after} seconds"
                )

            # Increment counter
            self._request_counts[client_id] = (count + 1, reset_time)
            remaining = self.config.rate_limit_requests - (count + 1)

        # Return rate limit headers
        return {
            "X-RateLimit-Limit": str(self.config.rate_limit_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(int(reset_time)),
        }


class GraphQLSecurityMiddleware:
    """Comprehensive GraphQL security middleware."""

    def __init__(self, config: Optional[GraphQLSecurityConfig] = None):
        self.config = config or GraphQLSecurityConfig.from_env()
        self.complexity_analyzer = QueryComplexityAnalyzer(self.config)
        self.introspection_protector = IntrospectionProtector(self.config)
        self.rate_limiter = GraphQLRateLimiter(self.config)

    async def validate_request(
        self, request: Request, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Validate a GraphQL request against all security controls.

        Args:
            request: The FastAPI request
            query: The GraphQL query string
            variables: Optional query variables

        Returns:
            Dict of headers to include in the response

        Raises:
            HTTPException: If any security check fails
        """
        headers: Dict[str, str] = {}

        try:
            # Rate limiting
            rate_limit_headers = await self.rate_limiter.check_rate_limit(request)
            headers.update(rate_limit_headers)

            # Introspection protection
            self.introspection_protector.validate_introspection(query)

            # Query complexity, depth, and field count validation
            self.complexity_analyzer.validate_query(query, variables)

        except GraphQLRateLimitError as e:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(e),
                headers=headers,
            )
        except IntrospectionDisabledError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except (QueryComplexityError, QueryDepthError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        return headers


def create_graphql_security_middleware(
    config: Optional[GraphQLSecurityConfig] = None,
) -> GraphQLSecurityMiddleware:
    """Factory function to create GraphQL security middleware."""
    return GraphQLSecurityMiddleware(config)


# Convenience function for FastAPI dependency injection
async def validate_graphql_request(
    request: Request,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    config: Optional[GraphQLSecurityConfig] = None,
) -> Dict[str, str]:
    """FastAPI dependency for validating GraphQL requests.

    Usage:
        @app.post("/graphql")
        async def graphql_endpoint(
            request: Request,
            query: str,
            headers: Dict[str, str] = Depends(
                lambda r, q: validate_graphql_request(r, q)
            )
        ):
            # Process GraphQL query
            pass
    """
    middleware = GraphQLSecurityMiddleware(config)
    return await middleware.validate_request(request, query, variables)
