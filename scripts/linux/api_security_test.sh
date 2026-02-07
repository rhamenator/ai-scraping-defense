#!/usr/bin/env bash
# api_security_test.sh - Automated API security testing
#
# Usage: ./api_security_test.sh <base_url> [openapi_spec_url]
# - base_url: Base URL of the API (e.g., http://localhost:5002)
# - openapi_spec_url: Optional OpenAPI/Swagger spec URL

set -euo pipefail

BASE_URL="$1"
OPENAPI_SPEC="${2:-}"

if [[ -z "$BASE_URL" ]]; then
    echo "Usage: $0 <base_url> [openapi_spec_url]"
    exit 1
fi

mkdir -p reports/api

echo "=== API Security Testing for $BASE_URL ==="

# Common API endpoints to test
API_ENDPOINTS=(
    "/api/health"
    "/api/status"
    "/api/metrics"
    "/api/admin"
    "/api/users"
    "/api/auth"
    "/api/login"
    "/api/config"
    "/api/escalate"
    "/api/analyze"
)

echo "=== 1. Basic API Discovery ==="
for endpoint in "${API_ENDPOINTS[@]}"; do
    echo "Testing $BASE_URL$endpoint"
    curl -s -o /dev/null -w "%{http_code} - $BASE_URL$endpoint\n" "$BASE_URL$endpoint" || true
done > "reports/api/discovery.txt"

echo "=== 2. API Authentication Testing ==="
# Test without auth
echo "Testing endpoints without authentication..."
for endpoint in "${API_ENDPOINTS[@]}"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$endpoint" || echo "000")
    echo "$STATUS - $endpoint (no auth)" >> "reports/api/auth_test.txt"
done

# Test with invalid tokens
echo "Testing with invalid JWT token..."
INVALID_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
for endpoint in "${API_ENDPOINTS[@]}"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $INVALID_TOKEN" "$BASE_URL$endpoint" || echo "000")
    echo "$STATUS - $endpoint (invalid token)" >> "reports/api/auth_test.txt"
done

echo "=== 3. API Injection Testing ==="
# SQL injection payloads
SQL_PAYLOADS=(
    "' OR '1'='1"
    "'; DROP TABLE users--"
    "1' UNION SELECT NULL--"
    "admin'--"
)

# Test SQL injection on common parameters
echo "Testing SQL injection patterns..."
for payload in "${SQL_PAYLOADS[@]}"; do
    ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$payload'))")
    curl -s -o /dev/null -w "%{http_code} - $payload\n" "$BASE_URL/api/users?id=$ENCODED" || true
done > "reports/api/sql_injection.txt"

echo "=== 4. API Rate Limiting Testing ==="
echo "Testing rate limits (100 rapid requests)..."
for i in {1..100}; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" || echo "000")
    echo "$i: $STATUS"
done > "reports/api/rate_limit_test.txt"

# Analyze rate limiting
RATE_LIMITED=$(grep -c "429" "reports/api/rate_limit_test.txt" || echo "0")
echo "Rate limiting triggered: $RATE_LIMITED times" >> "reports/api/rate_limit_test.txt"

echo "=== 5. API CORS Testing ==="
echo "Testing CORS configuration..."
curl -s -H "Origin: http://evil.com" -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: X-Requested-With" \
    -X OPTIONS "$BASE_URL/api/health" -D - > "reports/api/cors_test.txt" || true

echo "=== 6. API HTTP Method Testing ==="
echo "Testing unsupported HTTP methods..."
for method in GET POST PUT DELETE PATCH OPTIONS HEAD TRACE; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$BASE_URL/api/health" || echo "000")
    echo "$method: $STATUS" >> "reports/api/http_methods.txt"
done

echo "=== 7. API Parameter Fuzzing ==="
# Common parameter names that might expose issues
PARAM_NAMES=(
    "id"
    "user"
    "admin"
    "debug"
    "test"
    "redirect"
    "url"
    "callback"
    "file"
    "path"
)

echo "Testing parameter fuzzing..."
for param in "${PARAM_NAMES[@]}"; do
    curl -s -o /dev/null -w "%{http_code} - $param=test\n" "$BASE_URL/api/health?$param=test" || true
done > "reports/api/param_fuzzing.txt"

echo "=== 8. API Content-Type Testing ==="
# Test various content types
CONTENT_TYPES=(
    "application/json"
    "application/xml"
    "text/plain"
    "text/html"
    "multipart/form-data"
)

echo "Testing content types..."
for ct in "${CONTENT_TYPES[@]}"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Content-Type: $ct" \
        -d '{"test":"data"}' "$BASE_URL/api/health" || echo "000")
    echo "$STATUS - $ct" >> "reports/api/content_type_test.txt"
done

echo "=== 9. API Security Headers Testing ==="
echo "Checking security headers..."
curl -s -D - "$BASE_URL/api/health" | grep -E "(X-Frame-Options|X-Content-Type-Options|Strict-Transport-Security|Content-Security-Policy|X-XSS-Protection)" > "reports/api/security_headers.txt" || echo "No security headers found" > "reports/api/security_headers.txt"

echo "=== 10. API Mass Assignment Testing ==="
# Test for mass assignment vulnerabilities
echo "Testing mass assignment..."
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE_URL/api/users" \
    -H "Content-Type: application/json" \
    -d '{"username":"test","password":"test","is_admin":true,"role":"admin"}' \
    > "reports/api/mass_assignment.txt" || true

echo "=== 11. OpenAPI/Swagger Spec Testing ==="
if [[ -n "$OPENAPI_SPEC" ]]; then
    echo "Fetching OpenAPI specification..."
    curl -s "$OPENAPI_SPEC" > "reports/api/openapi_spec.json" || echo "Failed to fetch OpenAPI spec"

    # Use Schemathesis if available
    if command -v schemathesis >/dev/null 2>&1; then
        echo "Running Schemathesis tests..."
        schemathesis run "$OPENAPI_SPEC" --base-url="$BASE_URL" \
            --checks all > "reports/api/schemathesis.txt" 2>&1 || true
    fi
else
    echo "No OpenAPI spec provided. Skipping spec-based testing."
fi

echo "=== 12. API Response Analysis ==="
# Analyze responses for sensitive information
echo "Checking for sensitive data exposure..."
curl -s "$BASE_URL/api/health" | grep -iE "(password|secret|token|key|api_key|private)" > "reports/api/sensitive_data.txt" || echo "No obvious sensitive data found" > "reports/api/sensitive_data.txt"

echo "API security testing complete. Results saved in reports/api/"
