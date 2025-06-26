# Add force parameter
param(
    [switch]$Force
)

# Get current time in UTC and current user from OS
$CurrentTime = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
$CurrentUser = $env:USERNAME
$CurrentHostname = $env:COMPUTERNAME
$SecretsDir = Join-Path (Get-Location) "secrets"  # Use current directory

Write-Host "Generating secrets for:"
Write-Host "User: $CurrentUser"
Write-Host "Hostname: $CurrentHostname"
Write-Host "Time (UTC): $CurrentTime"
Write-Host "------------------------"

# Check for existing secrets before starting
if (Test-Path $SecretsDir) {
    $existingFiles = Get-ChildItem $SecretsDir -File
    if ($existingFiles.Count -gt 0 -and -not $Force) {
        Write-Host "WARNING: Secrets directory already contains files."
        Write-Host "Use -Force parameter to overwrite existing secrets."
        exit 1
    }
}

# Create secrets directory if it doesn't exist
New-Item -ItemType Directory -Force -Path $SecretsDir | Out-Null

# Function to generate highly random system seed
function New-SystemSeed {
    $length = Get-Random -Minimum 128 -Maximum 257
    Write-Host "Generating $length-character system seed..."
    
    $randomBytes = New-Object byte[] $length
    $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::Create()
    $rng.GetBytes($randomBytes)
    
    $chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%^&*()_+[]{}|;:,.<>?~'
    $result = -join ($randomBytes | ForEach-Object {
        $chars[$_ % $chars.Length]
    } | Get-Random -Count $length)
    
    return $result
}

# Function to generate a random password
function New-Password {
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
    try {
        $path = Join-Path $SecretsDir $filename
        [System.IO.File]::WriteAllText($path, $content)
        
        # Try to set file permissions, but continue if it fails
        try {
            $acl = Get-Acl $path
            $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            $accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                $identity, 
                "FullControl",
                "Allow"
            )
            $acl.SetAccessRule($accessRule)
            Set-Acl -Path $path -AclObject $acl -ErrorAction SilentlyContinue
        }
        catch {
            Write-Host "Note: Could not set special file permissions (not critical)" -ForegroundColor Yellow
        }
        
        Write-Host "Created: $filename"
    }
    catch {
        Write-Host "Error creating $filename : $_" -ForegroundColor Red
        exit 1
    }
}

# Generate system seed
$systemSeed = New-SystemSeed
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

# Generate .htpasswd file - completely random without patterns
$htpasswdPassword = -join ((1..(Get-Random -Minimum 30 -Maximum 49)) | 
    ForEach-Object { 
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%^&*()_+[]{}|;:,.<>?~'.ToCharArray() | 
        Get-Random 
    })
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
Write-Host "HTPasswd Password: $htpasswdPassword"
Write-Host "System Seed: $systemSeed"

Write-Host "`nDone! Make sure to save these passwords securely and never commit them to version control."