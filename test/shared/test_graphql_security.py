"""Tests for GraphQL security controls."""

import asyncio
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, Request

from src.shared.graphql_security import (
    EnvironmentMode,
    GraphQLRateLimiter,
    GraphQLRateLimitError,
    GraphQLSecurityConfig,
    GraphQLSecurityMiddleware,
    IntrospectionDisabledError,
    IntrospectionProtector,
    QueryComplexityAnalyzer,
    QueryComplexityError,
    QueryDepthError,
    create_graphql_security_middleware,
    validate_graphql_request,
)


class TestGraphQLSecurityConfig(unittest.TestCase):
    """Tests for GraphQLSecurityConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GraphQLSecurityConfig()
        self.assertEqual(config.max_query_complexity, 1000)
        self.assertEqual(config.max_query_depth, 10)
        self.assertEqual(config.max_field_count, 100)
        self.assertTrue(config.enable_introspection)
        self.assertEqual(config.environment, EnvironmentMode.DEVELOPMENT)
        self.assertEqual(config.rate_limit_requests, 100)
        self.assertEqual(config.rate_limit_window, 60)

    @patch.dict("os.environ", {"ENVIRONMENT": "production"})
    def test_config_from_env_production(self):
        """Test configuration from environment in production mode."""
        config = GraphQLSecurityConfig.from_env()
        self.assertEqual(config.environment, EnvironmentMode.PRODUCTION)
        self.assertFalse(config.enable_introspection)

    @patch.dict(
        "os.environ",
        {
            "ENVIRONMENT": "staging",
            "GRAPHQL_INTROSPECTION": "true",
            "GRAPHQL_MAX_COMPLEXITY": "500",
            "GRAPHQL_MAX_DEPTH": "5",
        },
    )
    def test_config_from_env_staging(self):
        """Test configuration from environment in staging mode."""
        config = GraphQLSecurityConfig.from_env()
        self.assertEqual(config.environment, EnvironmentMode.STAGING)
        self.assertTrue(config.enable_introspection)
        self.assertEqual(config.max_query_complexity, 500)
        self.assertEqual(config.max_query_depth, 5)

    @patch.dict("os.environ", {"ENVIRONMENT": "development"})
    def test_config_from_env_development(self):
        """Test configuration from environment in development mode."""
        config = GraphQLSecurityConfig.from_env()
        self.assertEqual(config.environment, EnvironmentMode.DEVELOPMENT)
        self.assertTrue(config.enable_introspection)


class TestQueryComplexityAnalyzer(unittest.TestCase):
    """Tests for QueryComplexityAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = GraphQLSecurityConfig(
            max_query_complexity=100,
            max_query_depth=5,
            max_field_count=20,
        )
        self.analyzer = QueryComplexityAnalyzer(self.config)

    def test_calculate_complexity_simple_query(self):
        """Test complexity calculation for a simple query."""
        query = """
        query {
            user {
                id
                name
            }
        }
        """
        complexity = self.analyzer.calculate_complexity(query)
        self.assertGreater(complexity, 0)
        self.assertLess(complexity, 100)

    def test_calculate_complexity_nested_query(self):
        """Test complexity calculation for a deeply nested query."""
        query = """
        query {
            user {
                posts {
                    comments {
                        author {
                            id
                        }
                    }
                }
            }
        }
        """
        complexity = self.analyzer.calculate_complexity(query)
        self.assertGreater(complexity, 0)

    def test_calculate_complexity_mutation(self):
        """Test that mutations have higher complexity."""
        query = """
        mutation {
            createUser(name: "test") {
                id
                name
            }
        }
        """
        complexity = self.analyzer.calculate_complexity(query)
        # Mutations should have the multiplier applied
        self.assertGreater(complexity, 10)

    def test_calculate_depth_simple(self):
        """Test depth calculation for a simple query."""
        query = """
        query {
            user {
                name
            }
        }
        """
        depth = self.analyzer.calculate_depth(query)
        self.assertEqual(depth, 2)

    def test_calculate_depth_nested(self):
        """Test depth calculation for a nested query."""
        query = """
        query {
            user {
                posts {
                    comments {
                        text
                    }
                }
            }
        }
        """
        depth = self.analyzer.calculate_depth(query)
        self.assertEqual(depth, 4)

    def test_count_fields_simple(self):
        """Test field counting for a simple query."""
        query = """
        query {
            user {
                id
                name
                email
            }
        }
        """
        field_count = self.analyzer.count_fields(query)
        self.assertGreater(field_count, 2)

    def test_validate_query_passes(self):
        """Test that a valid query passes validation."""
        query = """
        query {
            user {
                id
                name
            }
        }
        """
        # Should not raise an exception
        self.analyzer.validate_query(query)

    def test_validate_query_complexity_exceeds(self):
        """Test that a query exceeding complexity limit raises an error."""
        # Create a very complex query
        fields = "\n".join([f"field{i}" for i in range(50)])
        query = f"""
        query {{
            user {{
                {fields}
                posts {{
                    {fields}
                }}
            }}
        }}
        """
        with self.assertRaises(QueryComplexityError):
            self.analyzer.validate_query(query)

    def test_validate_query_depth_exceeds(self):
        """Test that a query exceeding depth limit raises an error."""
        # Create a deeply nested query that doesn't trigger complexity limit
        # Use a config with lower complexity threshold for this test
        config = GraphQLSecurityConfig(
            max_query_complexity=500,
            max_query_depth=5,
            max_field_count=100,
        )
        analyzer = QueryComplexityAnalyzer(config)
        nested = "{ field " * 10 + "}" * 10
        query = f"query {nested}"
        with self.assertRaises(QueryDepthError):
            analyzer.validate_query(query)

    def test_validate_query_field_count_exceeds(self):
        """Test that a query exceeding field count limit raises an error."""
        # Create a query with many fields
        fields = "\n".join([f"field{i}" for i in range(30)])
        query = f"""
        query {{
            {fields}
        }}
        """
        with self.assertRaises(ValueError):
            self.analyzer.validate_query(query)


class TestIntrospectionProtector(unittest.TestCase):
    """Tests for IntrospectionProtector."""

    def test_is_introspection_query_schema(self):
        """Test detection of __schema introspection query."""
        config = GraphQLSecurityConfig(enable_introspection=False)
        protector = IntrospectionProtector(config)

        query = """
        query {
            __schema {
                types {
                    name
                }
            }
        }
        """
        self.assertTrue(protector.is_introspection_query(query))

    def test_is_introspection_query_type(self):
        """Test detection of __type introspection query."""
        config = GraphQLSecurityConfig(enable_introspection=False)
        protector = IntrospectionProtector(config)

        query = """
        query {
            __type(name: "User") {
                fields {
                    name
                }
            }
        }
        """
        self.assertTrue(protector.is_introspection_query(query))

    def test_is_introspection_query_typename(self):
        """Test detection of __typename introspection field."""
        config = GraphQLSecurityConfig(enable_introspection=False)
        protector = IntrospectionProtector(config)

        query = """
        query {
            user {
                __typename
                name
            }
        }
        """
        self.assertTrue(protector.is_introspection_query(query))

    def test_is_not_introspection_query(self):
        """Test that regular queries are not detected as introspection."""
        config = GraphQLSecurityConfig(enable_introspection=False)
        protector = IntrospectionProtector(config)

        query = """
        query {
            user {
                id
                name
            }
        }
        """
        self.assertFalse(protector.is_introspection_query(query))

    def test_validate_introspection_allowed(self):
        """Test that introspection passes when enabled."""
        config = GraphQLSecurityConfig(enable_introspection=True)
        protector = IntrospectionProtector(config)

        query = """
        query {
            __schema {
                types {
                    name
                }
            }
        }
        """
        # Should not raise an exception
        protector.validate_introspection(query)

    def test_validate_introspection_blocked(self):
        """Test that introspection is blocked when disabled."""
        config = GraphQLSecurityConfig(
            enable_introspection=False, environment=EnvironmentMode.PRODUCTION
        )
        protector = IntrospectionProtector(config)

        query = """
        query {
            __schema {
                types {
                    name
                }
            }
        }
        """
        with self.assertRaises(IntrospectionDisabledError) as context:
            protector.validate_introspection(query)
        self.assertIn("production", str(context.exception).lower())


class TestGraphQLRateLimiter(unittest.IsolatedAsyncioTestCase):
    """Tests for GraphQLRateLimiter."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = GraphQLSecurityConfig(rate_limit_requests=5, rate_limit_window=60)
        self.limiter = GraphQLRateLimiter(self.config)

    def _create_mock_request(self, client_host: str = "127.0.0.1") -> Request:
        """Create a mock FastAPI request."""
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = client_host
        request.state = MagicMock()
        return request

    async def test_check_rate_limit_within_limit(self):
        """Test that requests within the rate limit pass."""
        request = self._create_mock_request()

        for i in range(5):
            headers = await self.limiter.check_rate_limit(request)
            self.assertIn("X-RateLimit-Limit", headers)
            self.assertIn("X-RateLimit-Remaining", headers)
            self.assertEqual(headers["X-RateLimit-Limit"], "5")

    async def test_check_rate_limit_exceeds_limit(self):
        """Test that exceeding the rate limit raises an error."""
        request = self._create_mock_request()

        # Use up the limit
        for i in range(5):
            await self.limiter.check_rate_limit(request)

        # Next request should fail
        with self.assertRaises(GraphQLRateLimitError) as context:
            await self.limiter.check_rate_limit(request)
        self.assertIn("rate limit exceeded", str(context.exception).lower())

    async def test_check_rate_limit_different_clients(self):
        """Test that different clients have separate rate limits."""
        request1 = self._create_mock_request("127.0.0.1")
        request2 = self._create_mock_request("192.168.1.1")

        # Both clients should be able to make requests
        for i in range(5):
            await self.limiter.check_rate_limit(request1)
            await self.limiter.check_rate_limit(request2)

        # Both should now be rate limited
        with self.assertRaises(GraphQLRateLimitError):
            await self.limiter.check_rate_limit(request1)
        with self.assertRaises(GraphQLRateLimitError):
            await self.limiter.check_rate_limit(request2)

    async def test_rate_limit_window_reset(self):
        """Test that rate limits reset after the window expires."""
        # Use a short window for testing
        config = GraphQLSecurityConfig(rate_limit_requests=2, rate_limit_window=1)
        limiter = GraphQLRateLimiter(config)
        request = self._create_mock_request()

        # Use up the limit
        await limiter.check_rate_limit(request)
        await limiter.check_rate_limit(request)

        # Should be rate limited
        with self.assertRaises(GraphQLRateLimitError):
            await limiter.check_rate_limit(request)

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should work again
        headers = await limiter.check_rate_limit(request)
        self.assertIn("X-RateLimit-Remaining", headers)

    async def test_get_client_identifier_with_user_id(self):
        """Test client identification with user ID."""
        request = self._create_mock_request()
        request.state.user_id = "user123"

        identifier = self.limiter._get_client_identifier(request)
        self.assertEqual(identifier, "user:user123")

    async def test_get_client_identifier_with_ip(self):
        """Test client identification with IP address."""
        request = self._create_mock_request("192.168.1.1")
        # Remove user_id from state to test IP-based identification
        delattr(request.state, "user_id")

        identifier = self.limiter._get_client_identifier(request)
        self.assertEqual(identifier, "ip:192.168.1.1")


class TestGraphQLSecurityMiddleware(unittest.IsolatedAsyncioTestCase):
    """Tests for GraphQLSecurityMiddleware."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = GraphQLSecurityConfig(
            max_query_complexity=100,
            max_query_depth=5,
            max_field_count=20,
            enable_introspection=False,
            environment=EnvironmentMode.PRODUCTION,
            rate_limit_requests=10,
        )
        self.middleware = GraphQLSecurityMiddleware(self.config)

    def _create_mock_request(self, client_host: str = "127.0.0.1") -> Request:
        """Create a mock FastAPI request."""
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = client_host
        request.state = MagicMock()
        return request

    async def test_validate_request_success(self):
        """Test successful validation of a valid query."""
        request = self._create_mock_request()
        query = """
        query {
            user {
                id
                name
            }
        }
        """
        headers = await self.middleware.validate_request(request, query)
        self.assertIn("X-RateLimit-Limit", headers)

    async def test_validate_request_introspection_blocked(self):
        """Test that introspection queries are blocked."""
        request = self._create_mock_request()
        query = """
        query {
            __schema {
                types {
                    name
                }
            }
        }
        """
        with self.assertRaises(HTTPException) as context:
            await self.middleware.validate_request(request, query)
        self.assertEqual(context.exception.status_code, 400)

    async def test_validate_request_complexity_exceeded(self):
        """Test that complex queries are rejected."""
        request = self._create_mock_request()
        # Create a very complex query
        fields = "\n".join([f"field{i}" for i in range(50)])
        query = f"""
        query {{
            user {{
                {fields}
                posts {{
                    {fields}
                }}
            }}
        }}
        """
        with self.assertRaises(HTTPException) as context:
            await self.middleware.validate_request(request, query)
        self.assertEqual(context.exception.status_code, 400)

    async def test_validate_request_rate_limit_exceeded(self):
        """Test that rate limit is enforced."""
        request = self._create_mock_request()
        query = """
        query {
            user {
                id
            }
        }
        """
        # Use up the rate limit
        for i in range(10):
            await self.middleware.validate_request(request, query)

        # Next request should fail
        with self.assertRaises(HTTPException) as context:
            await self.middleware.validate_request(request, query)
        self.assertEqual(context.exception.status_code, 429)


class TestFactoryFunctions(unittest.TestCase):
    """Tests for factory functions."""

    def test_create_graphql_security_middleware(self):
        """Test creating middleware with default config."""
        middleware = create_graphql_security_middleware()
        self.assertIsInstance(middleware, GraphQLSecurityMiddleware)
        self.assertIsNotNone(middleware.config)

    def test_create_graphql_security_middleware_with_config(self):
        """Test creating middleware with custom config."""
        config = GraphQLSecurityConfig(max_query_complexity=500)
        middleware = create_graphql_security_middleware(config)
        self.assertIsInstance(middleware, GraphQLSecurityMiddleware)
        self.assertEqual(middleware.config.max_query_complexity, 500)


class TestValidateGraphQLRequestFunction(unittest.IsolatedAsyncioTestCase):
    """Tests for the validate_graphql_request convenience function."""

    def _create_mock_request(self, client_host: str = "127.0.0.1") -> Request:
        """Create a mock FastAPI request."""
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = client_host
        request.state = MagicMock()
        return request

    async def test_validate_graphql_request_success(self):
        """Test the convenience function with a valid query."""
        request = self._create_mock_request()
        query = """
        query {
            user {
                id
                name
            }
        }
        """
        headers = await validate_graphql_request(request, query)
        self.assertIn("X-RateLimit-Limit", headers)

    async def test_validate_graphql_request_with_custom_config(self):
        """Test the convenience function with custom config."""
        config = GraphQLSecurityConfig(
            max_query_complexity=50, enable_introspection=False
        )
        request = self._create_mock_request()
        query = """
        query {
            user {
                id
            }
        }
        """
        headers = await validate_graphql_request(request, query, config=config)
        self.assertIn("X-RateLimit-Limit", headers)


if __name__ == "__main__":
    unittest.main()
