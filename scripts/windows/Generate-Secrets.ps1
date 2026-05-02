# Generate-Secrets.ps1 (Updated for Kubernetes)
#
# Creates a complete Kubernetes secrets manifest for the entire application stack.
#
# SECURITY WARNING:
# This script is intended for development and testing purposes only.
# For production deployments:
#   1. Use a proper secret management solution (HashiCorp Vault, AWS Secrets Manager,
#      Azure Key Vault, Google Secret Manager, or Kubernetes Secrets with encryption)
#   2. Enable encryption at rest for all secret storage
#   3. Implement regular secret rotation schedules
#   4. Never commit generated secrets to version control
#   5. Protect exported secret files with strict permissions
#   6. Delete exported secret files after importing to your secret manager
#
# See SECURITY.md for comprehensive secret management guidelines.
#
# Optional arguments
param(
    [string]$ExportPath
)

# Warn if not running as Administrator
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}

$RootDir = Split-Path -Parent $PSScriptRoot
$K8sDir = Join-Path $RootDir "kubernetes"
if (-not (Test-Path $K8sDir)) { New-Item -ItemType Directory -Path $K8sDir | Out-Null }
$OutputFile = Join-Path $K8sDir "secrets.yaml"
$NginxHtpasswdFile = Join-Path $RootDir "nginx/.htpasswd"

function New-RandomPassword {
    param([int]$Length = 24)
    $specialChars = '!@#$%^&*'
    $passwordChars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' + $specialChars
    $random = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    $bytes = New-Object byte[] $Length
    $random.GetBytes($bytes)
    $password = -join ($bytes | ForEach-Object { $passwordChars[$_ % $passwordChars.Length] })
    if ($password -notmatch "[$([regex]::Escape($specialChars))]") {
        $password = $password.Substring(0, $Length - 1) + $specialChars[(Get-Random -Minimum 0 -Maximum $specialChars.Length)]
    }
    return $password
}

function New-RandomToken {
    param([int]$Length = 8)
    $tokenChars = 'abcdefghijklmnopqrstuvwxyz0123456789'
    $random = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    $bytes = New-Object byte[] $Length
    $random.GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $tokenChars[$_ % $tokenChars.Length] })
}

function ConvertTo-Base64 {
    param([string]$InputString)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($InputString)
    return [System.Convert]::ToBase64String($bytes)
}

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "SECURITY WARNING: Development/Testing Only" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "This script generates secrets for DEVELOPMENT/TESTING only." -ForegroundColor Yellow
Write-Host "For PRODUCTION, use a proper secret management solution:" -ForegroundColor Yellow
Write-Host "  • HashiCorp Vault, AWS Secrets Manager, Azure Key Vault" -ForegroundColor Yellow
Write-Host "  • Enable encryption at rest and implement key rotation" -ForegroundColor Yellow
Write-Host "  • See SECURITY.md for complete guidelines" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""
Write-Host "Generating secrets for Kubernetes..." -ForegroundColor Cyan

# Generate all values
$postgresPassword = New-RandomPassword
$redisPassword = New-RandomPassword
if (-not [string]::IsNullOrEmpty($env:ADMIN_UI_USERNAME)) {
    $adminUiUsername = $env:ADMIN_UI_USERNAME
} elseif (-not [string]::IsNullOrEmpty($env:USERNAME)) {
    $adminUiUsername = $env:USERNAME
} else {
    $adminUiUsername = "admin-" + (New-RandomToken -Length 8)
}
$adminUiPassword = New-RandomPassword
$adminUiPasswordHash = (htpasswd -nbBC 12 $adminUiUsername $adminUiPassword).Split(':')[1].Trim()
$systemSeed = New-RandomPassword -Length 48
$nginxPassword = New-RandomPassword -Length 32
$externalApiKey = "key-for-" + (New-RandomPassword)
$ipReputationApiKey = "key-for-" + (New-RandomPassword)
$communityBlocklistApiKey = "key-for-" + (New-RandomPassword)
$openaiApiKey = "sk-" + (New-RandomPassword -Length 40)
$anthropicApiKey = "sk-ant-" + (New-RandomPassword -Length 40)
$googleApiKey = "AIza" + (New-RandomPassword -Length 35)
$cohereApiKey = "coh-" + (New-RandomPassword -Length 40)
$mistralApiKey = "mistral-" + (New-RandomPassword -Length 40)

# Create Nginx htpasswd content using bcrypt
$htpasswdFileContent = (htpasswd -nbBC 12 $adminUiUsername $nginxPassword).Trim()
Set-Content -Path $NginxHtpasswdFile -Value $htpasswdFileContent -Encoding ASCII

# Base64 encode all values
$postgresUser_b64 = ConvertTo-Base64 "postgres"
$postgresDb_b64 = ConvertTo-Base64 "markov_db"
$postgresPassword_b64 = ConvertTo-Base64 $postgresPassword
$redisPassword_b64 = ConvertTo-Base64 $redisPassword
$adminUiUsername_b64 = ConvertTo-Base64 $adminUiUsername
$adminUiPasswordHash_b64 = ConvertTo-Base64 $adminUiPasswordHash
$systemSeed_b64 = ConvertTo-Base64 $systemSeed
$externalApiKey_b64 = ConvertTo-Base64 $externalApiKey
$ipReputationApiKey_b64 = ConvertTo-Base64 $ipReputationApiKey
$communityBlocklistApiKey_b64 = ConvertTo-Base64 $communityBlocklistApiKey
$htpasswdFileContent_b64 = ConvertTo-Base64 $htpasswdFileContent
$openaiApiKey_b64 = ConvertTo-Base64 $openaiApiKey
$anthropicApiKey_b64 = ConvertTo-Base64 $anthropicApiKey
$googleApiKey_b64 = ConvertTo-Base64 $googleApiKey
$cohereApiKey_b64 = ConvertTo-Base64 $cohereApiKey
$mistralApiKey_b64 = ConvertTo-Base64 $mistralApiKey

# Assemble YAML
$yamlContent = @"
# WARNING: This file contains generated secrets for DEVELOPMENT/TESTING only
# DO NOT commit this file to version control (already in .gitignore)
# For production, use a proper secret management solution
# See SECURITY.md for guidelines
---
apiVersion: v1
kind: Secret
metadata:
  name: postgres-credentials
  namespace: ai-defense
type: Opaque
data:
  POSTGRES_USER: $postgresUser_b64
  POSTGRES_DB: $postgresDb_b64
  POSTGRES_PASSWORD: $postgresPassword_b64
---
apiVersion: v1
kind: Secret
metadata:
  name: redis-credentials
  namespace: ai-defense
type: Opaque
data:
  REDIS_PASSWORD: $redisPassword_b64
---
apiVersion: v1
kind: Secret
metadata:
  name: admin-ui-credentials
  namespace: ai-defense
type: Opaque
data:
  ADMIN_UI_USERNAME: $adminUiUsername_b64
  ADMIN_UI_PASSWORD_HASH: $adminUiPasswordHash_b64
---
apiVersion: v1
kind: Secret
metadata:
  name: system-seed-secret
  namespace: ai-defense
type: Opaque
data:
  SYSTEM_SEED: $systemSeed_b64
---
apiVersion: v1
kind: Secret
metadata:
  name: nginx-auth
  namespace: ai-defense
type: Opaque
data:
  .htpasswd: $htpasswdFileContent_b64
---
apiVersion: v1
kind: Secret
metadata:
  name: external-api-keys
  namespace: ai-defense
type: Opaque
data:
  EXTERNAL_API_KEY: $externalApiKey_b64
  OPENAI_API_KEY: $openaiApiKey_b64
  ANTHROPIC_API_KEY: $anthropicApiKey_b64
  GOOGLE_API_KEY: $googleApiKey_b64
  COHERE_API_KEY: $cohereApiKey_b64
  MISTRAL_API_KEY: $mistralApiKey_b64
  IP_REPUTATION_API_KEY: $ipReputationApiKey_b64
  COMMUNITY_BLOCKLIST_API_KEY: $communityBlocklistApiKey_b64
"@

Set-Content -Path $OutputFile -Value $yamlContent -Encoding UTF8

if ($ExportPath) {
    $creds = [ordered]@{
        ADMIN_UI_USERNAME = $adminUiUsername
        ADMIN_UI_PASSWORD = $adminUiPassword
        NGINX_PASSWORD = $nginxPassword
        POSTGRES_PASSWORD = $postgresPassword
        REDIS_PASSWORD = $redisPassword
        SYSTEM_SEED = $systemSeed
        OPENAI_API_KEY = $openaiApiKey
        ANTHROPIC_API_KEY = $anthropicApiKey
        GOOGLE_API_KEY = $googleApiKey
        COHERE_API_KEY = $cohereApiKey
        MISTRAL_API_KEY = $mistralApiKey
        EXTERNAL_API_KEY = $externalApiKey
        IP_REPUTATION_API_KEY = $ipReputationApiKey
        COMMUNITY_BLOCKLIST_API_KEY = $communityBlocklistApiKey
        _security_notice = "IMPORTANT: This file contains sensitive credentials. Delete after importing to your secret manager. Never commit to version control."
    }

    # Security: Create file and set permissions before writing sensitive data
    New-Item -Path $ExportPath -ItemType File -Force | Out-Null
    $creds | ConvertTo-Json -Depth 1 | Set-Content -Path $ExportPath -Encoding UTF8

    # Set restrictive file permissions (Windows ACL)
    try {
        $acl = Get-Acl $ExportPath
        $acl.SetAccessRuleProtection($true, $false)
        $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, "FullControl", "Allow")
        $acl.AddAccessRule($accessRule)
        Set-Acl -Path $ExportPath -AclObject $acl
        Write-Host "✓ Credentials exported to: $ExportPath (restricted permissions)" -ForegroundColor Green
    } catch {
        Write-Host "✓ Credentials exported to: $ExportPath (set permissions manually)" -ForegroundColor Green
    }

    Write-Host "  ⚠ SECURITY: Import to your secret manager and DELETE this file" -ForegroundColor Yellow
}

# Do not print any secrets or secret values to stdout.
Write-Host ""
Write-Host "✓ Kubernetes secrets manifest created: $OutputFile" -ForegroundColor Green

if ($ExportPath) {
    Write-Host "✓ Credentials exported to: $ExportPath" -ForegroundColor Green
    Write-Host "  ⚠ Delete this file after importing to your secret manager" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Review generated secrets (do not log or display)" -ForegroundColor Yellow
Write-Host "  2. Apply to Kubernetes: kubectl apply -f $OutputFile" -ForegroundColor Yellow
Write-Host "  3. Enable encryption at rest: kubectl get secrets -n ai-defense" -ForegroundColor Yellow
Write-Host "  4. Set up secret rotation schedule (see SECURITY.md)" -ForegroundColor Yellow
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "✓ Secrets Generation Complete" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "IMPORTANT SECURITY REMINDERS:" -ForegroundColor Yellow
Write-Host "  • These secrets are for DEVELOPMENT/TESTING only" -ForegroundColor Yellow
Write-Host "  • DO NOT commit .env, secrets/, or exported JSON to git" -ForegroundColor Yellow
Write-Host "  • Use proper secret management for production (see SECURITY.md)" -ForegroundColor Yellow
Write-Host "  • Implement regular secret rotation schedules" -ForegroundColor Yellow
Write-Host "  • Enable encryption at rest for all secret storage" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
