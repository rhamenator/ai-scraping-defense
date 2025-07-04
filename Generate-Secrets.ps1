# Generate-Secrets.ps1 (Updated for Kubernetes)
#
# Creates a complete Kubernetes secrets manifest for the entire application stack.
# Creates a complete Kubernetes secrets manifest for the entire application stack.

$K8sDir = Join-Path $PSScriptRoot "kubernetes"
if (-not (Test-Path $K8sDir)) { New-Item -ItemType Directory -Path $K8sDir | Out-Null }
if (-not (Test-Path $K8sDir)) { New-Item -ItemType Directory -Path $K8sDir | Out-Null }
$OutputFile = Join-Path $K8sDir "secrets.yaml"

function New-RandomPassword { param([int]$Length = 24); $specialChars = '!@#$%^&*'; $passwordChars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' + $specialChars; $random = New-Object System.Security.Cryptography.RNGCryptoServiceProvider; $bytes = New-Object byte[] $Length; $random.GetBytes($bytes); $password = -join ($bytes | ForEach-Object { $passwordChars[$_ % $passwordChars.Length] }); if ($password -notmatch "[$([regex]::Escape($specialChars))]") { $password = $password.Substring(0, $Length - 1) + $specialChars[(Get-Random -Minimum 0 -Maximum $specialChars.Length)] }; return $password }
function ConvertTo-Base64 { param([string]$InputString); $bytes = [System.Text.Encoding]::UTF8.GetBytes($InputString); return [System.Convert]::ToBase64String($bytes) }
function New-RandomPassword { param([int]$Length = 24); $specialChars = '!@#$%^&*'; $passwordChars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' + $specialChars; $random = New-Object System.Security.Cryptography.RNGCryptoServiceProvider; $bytes = New-Object byte[] $Length; $random.GetBytes($bytes); $password = -join ($bytes | ForEach-Object { $passwordChars[$_ % $passwordChars.Length] }); if ($password -notmatch "[$([regex]::Escape($specialChars))]") { $password = $password.Substring(0, $Length - 1) + $specialChars[(Get-Random -Minimum 0 -Maximum $specialChars.Length)] }; return $password }
function ConvertTo-Base64 { param([string]$InputString); $bytes = [System.Text.Encoding]::UTF8.GetBytes($InputString); return [System.Convert]::ToBase64String($bytes) }

Write-Host "Generating secrets for Kubernetes..."

# Generate all values
# Generate all values
$postgresPassword = New-RandomPassword
$redisPassword = New-RandomPassword
$adminUiUsername = if ([string]::IsNullOrEmpty($env:USERNAME)) { "defense-admin" } else { $env:USERNAME }
$adminUiUsername = if ([string]::IsNullOrEmpty($env:USERNAME)) { "defense-admin" } else { $env:USERNAME }
$adminUiPassword = New-RandomPassword
$systemSeed = New-RandomPassword -Length 48
$nginxPassword = New-RandomPassword -Length 32
$externalApiKey = "key-for-" + (New-RandomPassword)
$ipReputationApiKey = "key-for-" + (New-RandomPassword)
$communityBlocklistApiKey = "key-for-" + (New-RandomPassword)
$smtpPassword = New-RandomPassword
$openaiApiKey = "sk-" + (New-RandomPassword -Length 40)
$anthropicApiKey = "sk-ant-" + (New-RandomPassword -Length 40)
$googleApiKey = "AIza" + (New-RandomPassword -Length 35)
$cohereApiKey = "coh-" + (New-RandomPassword -Length 40)
$mistralApiKey = "mistral-" + (New-RandomPassword -Length 40)

# Create Nginx htpasswd content
$sha1 = [System.Security.Cryptography.SHA1]::Create(); $passwordBytes = [System.Text.Encoding]::UTF8.GetBytes($nginxPassword); $hashBytes = $sha1.ComputeHash($passwordBytes); $hash_b64 = [System.Convert]::ToBase64String($hashBytes); $htpasswdFileContent = "${adminUiUsername}:{SHA}${hash_b64}"
$externalApiKey = "key-for-" + (New-RandomPassword)
$ipReputationApiKey = "key-for-" + (New-RandomPassword)
$communityBlocklistApiKey = "key-for-" + (New-RandomPassword)
$smtpPassword = New-RandomPassword
$openaiApiKey = "sk-" + (New-RandomPassword -Length 40)
$anthropicApiKey = "sk-ant-" + (New-RandomPassword -Length 40)
$googleApiKey = "AIza" + (New-RandomPassword -Length 35)
$cohereApiKey = "coh-" + (New-RandomPassword -Length 40)
$mistralApiKey = "mistral-" + (New-RandomPassword -Length 40)

# Create Nginx htpasswd content
$sha1 = [System.Security.Cryptography.SHA1]::Create(); $passwordBytes = [System.Text.Encoding]::UTF8.GetBytes($nginxPassword); $hashBytes = $sha1.ComputeHash($passwordBytes); $hash_b64 = [System.Convert]::ToBase64String($hashBytes); $htpasswdFileContent = "${adminUiUsername}:{SHA}${hash_b64}"

# Base64 encode all values
$postgresUser_b64 = ConvertTo-Base64 "postgres"; $postgresDb_b64 = ConvertTo-Base64 "markov_db"; $postgresPassword_b64 = ConvertTo-Base64 $postgresPassword; $redisPassword_b64 = ConvertTo-Base64 $redisPassword; $adminUiUsername_b64 = ConvertTo-Base64 $adminUiUsername; $adminUiPassword_b64 = ConvertTo-Base64 $adminUiPassword; $systemSeed_b64 = ConvertTo-Base64 $systemSeed; $externalApiKey_b64 = ConvertTo-Base64 $externalApiKey; $ipReputationApiKey_b64 = ConvertTo-Base64 $ipReputationApiKey; $communityBlocklistApiKey_b64 = ConvertTo-Base64 $communityBlocklistApiKey; $smtpPassword_b64 = ConvertTo-Base64 $smtpPassword; $htpasswdFileContent_b64 = ConvertTo-Base64 $htpasswdFileContent; $openaiApiKey_b64 = ConvertTo-Base64 $openaiApiKey; $anthropicApiKey_b64 = ConvertTo-Base64 $anthropicApiKey; $googleApiKey_b64 = ConvertTo-Base64 $googleApiKey; $cohereApiKey_b64 = ConvertTo-Base64 $cohereApiKey; $mistralApiKey_b64 = ConvertTo-Base64 $mistralApiKey

# Assemble YAML
$yamlContent = @"
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
  ADMIN_UI_PASSWORD: $adminUiPassword_b64
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
  SMTP_PASSWORD: $smtpPassword_b64
"@

Set-Content -Path $OutputFile -Value $yamlContent -Encoding UTF8

# Output credentials
Write-Host "Successfully created Kubernetes secrets file at: $OutputFile" -ForegroundColor Green
Write-Host "--- IMPORTANT: Save the following credentials in a secure place! ---" -ForegroundColor Yellow
Write-Host "NGINX / Admin UI Credentials:" -ForegroundColor Cyan
Write-Host "  Username: $adminUiUsername"
Write-Host "  Password: $nginxPassword"
Write-Host "Service Passwords & Keys:" -ForegroundColor Cyan
Write-Host "  PostgreSQL Password: $postgresPassword"
Write-Host "  Redis Password:      $redisPassword"
Write-Host "  System Seed:         $systemSeed"
Write-Host "LLM API Keys (placeholders, replace with real keys if needed):" -ForegroundColor Cyan
Write-Host "  OpenAI API Key:    $openaiApiKey"
Write-Host "  Anthropic API Key: $anthropicApiKey"
Write-Host "  Google API Key:    $googleApiKey"
Write-Host "  Cohere API Key:    $cohereApiKey"
Write-Host "  Mistral API Key:   $mistralApiKey"
Write-Host "  External API Key:  $external"
Write-Host "  IP Reputation API Key: $ipReputationApiKey"
Write-Host "  Community Blocklist API Key: $communityBlocklistApiKey"
Write-Host "  SMTP Password: $smtpPassword"
Write-Host "--- End of credentials ---" -ForegroundColor Yellow
Write-Host "Kubernetes secrets mainfest file created at: $OutputFile" -ForegroundColor Green
Write-Host "You can now apply the secrets to your Kubernetes cluster using:" -ForegroundColor Yellow
Write-Host "  kubectl apply -f $OutputFile" -ForegroundColor Yellow
Write-Host "To view the secrets in your cluster, use:" -ForegroundColor Green
Write-Host "  kubectl get secrets -n ai-defense" -ForegroundColor Green
Write-Host "To view the details of a specific secret, use:" -ForegroundColor Green
Write-Host "  kubectl describe secret <secret-name> -n ai-defense" -ForegroundColor Green
Write-Host "Secrets generation complete!" -ForegroundColor Green
# End of script