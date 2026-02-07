<#
.SYNOPSIS
    Windows PowerShell version of api_security_test.sh - Automated API security testing
.DESCRIPTION
    Comprehensive API security validation including authentication, injection, rate limiting, CORS, and more.
.PARAMETER BaseUrl
    Base URL of the API (e.g., http://localhost:5002)
.PARAMETER OpenApiSpec
    Optional OpenAPI/Swagger spec URL
#>
param(
    [Parameter(Mandatory=$true)][string]$BaseUrl,
    [string]$OpenApiSpec
)

$ErrorActionPreference = 'Continue'

if (-not (Test-Path 'reports/api')) {
    New-Item -ItemType Directory -Path 'reports/api' -Force | Out-Null
}

Write-Host "=== API Security Testing for $BaseUrl ==="

# Common API endpoints to test
$ApiEndpoints = @(
    '/api/health',
    '/api/status',
    '/api/metrics',
    '/api/admin',
    '/api/users',
    '/api/auth',
    '/api/login',
    '/api/config',
    '/api/escalate',
    '/api/analyze'
)

Write-Host '=== 1. Basic API Discovery ==='
foreach ($endpoint in $ApiEndpoints) {
    Write-Host "Testing $BaseUrl$endpoint"
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl$endpoint" -UseBasicParsing -ErrorAction SilentlyContinue
        "$($response.StatusCode) - $BaseUrl$endpoint" | Out-File -Append 'reports/api/discovery.txt'
    } catch {
        "$($_.Exception.Response.StatusCode.value__) - $BaseUrl$endpoint" | Out-File -Append 'reports/api/discovery.txt'
    }
}

Write-Host '=== 2. API Authentication Testing ==='
Write-Host 'Testing endpoints without authentication...'
foreach ($endpoint in $ApiEndpoints) {
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl$endpoint" -UseBasicParsing -ErrorAction SilentlyContinue
        "$($response.StatusCode) - $endpoint (no auth)" | Out-File -Append 'reports/api/auth_test.txt'
    } catch {
        "$($_.Exception.Response.StatusCode.value__) - $endpoint (no auth)" | Out-File -Append 'reports/api/auth_test.txt'
    }
}

Write-Host 'Testing with invalid JWT token...'
$InvalidToken = 'Bearer invalid.jwt.token'
foreach ($endpoint in $ApiEndpoints) {
    try {
        $headers = @{ 'Authorization' = $InvalidToken }
        $response = Invoke-WebRequest -Uri "$BaseUrl$endpoint" -Headers $headers -UseBasicParsing -ErrorAction SilentlyContinue
        "$($response.StatusCode) - $endpoint (invalid token)" | Out-File -Append 'reports/api/auth_test.txt'
    } catch {
        "$($_.Exception.Response.StatusCode.value__) - $endpoint (invalid token)" | Out-File -Append 'reports/api/auth_test.txt'
    }
}

Write-Host '=== 3. API Injection Testing ==='
$SqlPayloads = @(
    "' OR '1'='1",
    "'; DROP TABLE users--",
    "1' UNION SELECT NULL--",
    "admin'--"
)

Write-Host 'Testing SQL injection patterns...'
foreach ($payload in $SqlPayloads) {
    $encoded = [System.Web.HttpUtility]::UrlEncode($payload)
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/api/users?id=$encoded" -UseBasicParsing -ErrorAction SilentlyContinue
        "$($response.StatusCode) - $payload" | Out-File -Append 'reports/api/sql_injection.txt'
    } catch {
        "$($_.Exception.Response.StatusCode.value__) - $payload" | Out-File -Append 'reports/api/sql_injection.txt'
    }
}

Write-Host '=== 4. API Rate Limiting Testing ==='
Write-Host 'Testing rate limits (100 rapid requests)...'
for ($i = 1; $i -le 100; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/api/health" -UseBasicParsing -ErrorAction SilentlyContinue
        "$i : $($response.StatusCode)" | Out-File -Append 'reports/api/rate_limit_test.txt'
    } catch {
        "$i : $($_.Exception.Response.StatusCode.value__)" | Out-File -Append 'reports/api/rate_limit_test.txt'
    }
}

$rateLimited = (Select-String -Path 'reports/api/rate_limit_test.txt' -Pattern '429' -AllMatches).Matches.Count
"Rate limiting triggered: $rateLimited times" | Out-File -Append 'reports/api/rate_limit_test.txt'

Write-Host '=== 5. API CORS Testing ==='
Write-Host 'Testing CORS configuration...'
try {
    $headers = @{
        'Origin' = 'http://evil.com'
        'Access-Control-Request-Method' = 'POST'
        'Access-Control-Request-Headers' = 'X-Requested-With'
    }
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/health" -Method OPTIONS -Headers $headers -UseBasicParsing
    $response.Headers | Out-File 'reports/api/cors_test.txt'
} catch {
    $_.Exception.Message | Out-File 'reports/api/cors_test.txt'
}

Write-Host '=== 6. API HTTP Method Testing ==='
Write-Host 'Testing unsupported HTTP methods...'
$methods = @('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD', 'TRACE')
foreach ($method in $methods) {
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/api/health" -Method $method -UseBasicParsing -ErrorAction SilentlyContinue
        "$method : $($response.StatusCode)" | Out-File -Append 'reports/api/http_methods.txt'
    } catch {
        "$method : $($_.Exception.Response.StatusCode.value__)" | Out-File -Append 'reports/api/http_methods.txt'
    }
}

Write-Host '=== 7. API Parameter Fuzzing ==='
$paramNames = @('id', 'user', 'admin', 'debug', 'test', 'redirect', 'url', 'callback', 'file', 'path')
Write-Host 'Testing parameter fuzzing...'
foreach ($param in $paramNames) {
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/api/health?$param=test" -UseBasicParsing -ErrorAction SilentlyContinue
        "$($response.StatusCode) - $param=test" | Out-File -Append 'reports/api/param_fuzzing.txt'
    } catch {
        "$($_.Exception.Response.StatusCode.value__) - $param=test" | Out-File -Append 'reports/api/param_fuzzing.txt'
    }
}

Write-Host '=== 8. API Content-Type Testing ==='
$contentTypes = @('application/json', 'application/xml', 'text/plain', 'text/html', 'multipart/form-data')
Write-Host 'Testing content types...'
foreach ($ct in $contentTypes) {
    try {
        $headers = @{ 'Content-Type' = $ct }
        $body = '{"test":"data"}'
        $response = Invoke-WebRequest -Uri "$BaseUrl/api/health" -Method POST -Headers $headers -Body $body -UseBasicParsing -ErrorAction SilentlyContinue
        "$($response.StatusCode) - $ct" | Out-File -Append 'reports/api/content_type_test.txt'
    } catch {
        "$($_.Exception.Response.StatusCode.value__) - $ct" | Out-File -Append 'reports/api/content_type_test.txt'
    }
}

Write-Host '=== 9. API Security Headers Testing ==='
Write-Host 'Checking security headers...'
try {
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/health" -UseBasicParsing
    $securityHeaders = @('X-Frame-Options', 'X-Content-Type-Options', 'Strict-Transport-Security', 'Content-Security-Policy', 'X-XSS-Protection')
    foreach ($header in $securityHeaders) {
        if ($response.Headers[$header]) {
            "$header : $($response.Headers[$header])" | Out-File -Append 'reports/api/security_headers.txt'
        }
    }
} catch {
    'Error checking headers' | Out-File 'reports/api/security_headers.txt'
}

Write-Host '=== 10. API Mass Assignment Testing ==='
Write-Host 'Testing mass assignment...'
try {
    $headers = @{ 'Content-Type' = 'application/json' }
    $body = '{"username":"test","password":"test","is_admin":true,"role":"admin"}'
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/users" -Method POST -Headers $headers -Body $body -UseBasicParsing -ErrorAction SilentlyContinue
    $response.StatusCode | Out-File 'reports/api/mass_assignment.txt'
} catch {
    $_.Exception.Response.StatusCode.value__ | Out-File 'reports/api/mass_assignment.txt'
}

Write-Host '=== 11. OpenAPI/Swagger Spec Testing ==='
if ($OpenApiSpec) {
    Write-Host 'Fetching OpenAPI specification...'
    try {
        $spec = Invoke-WebRequest -Uri $OpenApiSpec -UseBasicParsing
        $spec.Content | Out-File 'reports/api/openapi_spec.json'

        if (Get-Command schemathesis -ErrorAction SilentlyContinue) {
            Write-Host 'Running Schemathesis tests...'
            schemathesis run $OpenApiSpec --base-url=$BaseUrl --checks all > 'reports/api/schemathesis.txt' 2>&1
        }
    } catch {
        'Failed to fetch OpenAPI spec' | Out-File 'reports/api/openapi_spec.json'
    }
} else {
    Write-Host 'No OpenAPI spec provided. Skipping spec-based testing.'
}

Write-Host '=== 12. API Response Analysis ==='
Write-Host 'Checking for sensitive data exposure...'
try {
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/health" -UseBasicParsing
    if ($response.Content -match '(password|secret|token|key|api_key|private)') {
        'Potential sensitive data found' | Out-File 'reports/api/sensitive_data.txt'
    } else {
        'No obvious sensitive data found' | Out-File 'reports/api/sensitive_data.txt'
    }
} catch {
    'Error analyzing response' | Out-File 'reports/api/sensitive_data.txt'
}

Write-Host 'API security testing complete. Results saved in reports/api/'
