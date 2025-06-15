# Get current time in UTC and current user from OS
$CurrentTime = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
$CurrentUser = $env:USERNAME
$CurrentHostname = $env:COMPUTERNAME
$SecretsDir = ".\secrets"

Write-Host "Generating secrets for:"
Write-Host "User: $CurrentUser"
Write-Host "Hostname: $CurrentHostname"
Write-Host "Time (UTC): $CurrentTime"
Write-Host "------------------------"

# Create secrets directory if it doesn't exist
New-Item -ItemType Directory -Force -Path $SecretsDir | Out-Null

# Function to generate a random password
function New-Password {
    # Random length between 15 and 32 characters
    $length = Get-Random -Minimum 15 -Maximum 33
    Write-Host "Generating $length-character password..."
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:,.<>?'
    return -join ((1..$length) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
}

# Function to generate a hex string
function New-Generated-Hex {
    param([int]$length)
    return -join ((1..$length) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
}

# Function to create a secret file
function New-Secret {
    param($filename, $content)
    $path = Join-Path $SecretsDir $filename
    [System.IO.File]::WriteAllText($path, $content)
    # Set file permissions to be accessible only by the current user
    $acl = Get-Acl $path
    $acl.SetAccessRuleProtection($true, $false)
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, "FullControl", "Allow")
    $acl.AddAccessRule($accessRule)
    Set-Acl $path $acl
    Write-Host "Created: $filename"
}

# Generate system seed
$systemSeed = "seed_${CurrentHostname}_$((Get-Date $CurrentTime).ToString('yyyyMMddHHmmss'))_$(New-Generated-Hex 8)"
New-Secret "system_seed.txt" $systemSeed

# Generate passwords and keys
$adminPassword = New-Password
New-Secret "admin_ui_password.txt" $adminPassword
New-Secret "redis_password.txt" (New-Password)
New-Secret "pg_password.txt" (New-Password)
New-Secret "training_pg_password.txt" (New-Password)
New-Secret "smtp_password.txt" (New-Password)

# Generate API keys
New-Secret "external_api_key.txt" "key_$(New-Generated-Hex 16)"
New-Secret "ip_reputation_api_key.txt" "key_$(New-Generated-Hex 16)"
New-Secret "community_blocklist_api_key.txt" "key_$(New-Generated-Hex 16)"

# Generate .htpasswd file
$htpasswdPassword = "protected_$((Get-Date $CurrentTime).ToString('yyyyMMddHHmmss'))_$(New-Generated-Hex 4)"
$htpasswd = "${CurrentUser}:{SHA}" + [Convert]::ToBase64String([System.Security.Cryptography.SHA1]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($htpasswdPassword)))
New-Secret ".htpasswd" $htpasswd

# Print summary
Write-Host "`nSecret files generated in ${SecretsDir}:"
Get-ChildItem $SecretsDir | Format-Table Name, Length, LastWriteTime

# Print important passwords
Write-Host "`nImportant Passwords (save these):"
Write-Host "Admin UI Username: $CurrentUser"
Write-Host "Admin UI Password: $adminPassword"
Write-Host "HTPasswd Username: $CurrentUser"
Write-Host "HTPasswd Password: $htpasswd"
Write-Host "System Seed: $systemSeed"

Write-Host "`nDone! Make sure to save these passwords securely and never commit them to version control."