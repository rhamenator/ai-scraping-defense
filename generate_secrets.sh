#!/bin/bash

# Get current time in UTC and current user from OS
CURRENT_TIME=$(date -u +"%Y-%m-%d %H:%M:%S")
CURRENT_USER=$(whoami)
CURRENT_HOSTNAME=$(hostname)
SECRETS_DIR="./secrets"

# Parse command line arguments
FORCE_OVERWRITE=0
while getopts "f" opt; do
    case $opt in
        f) FORCE_OVERWRITE=1 ;;
    esac
done

# Check for existing secrets before starting
if [ -d "$SECRETS_DIR" ] && [ $FORCE_OVERWRITE -eq 0 ]; then
    if ls $SECRETS_DIR/* >/dev/null 2>&1; then
        echo "WARNING: Secrets directory already contains files."
        echo "Use -f flag to force overwrite of existing secrets."
        exit 1
    fi
fi

echo "Generating secrets for:"
echo "User: $CURRENT_USER"
echo "Hostname: $CURRENT_HOSTNAME"
echo "Time (UTC): $CURRENT_TIME"
echo "------------------------"

# Create secrets directory if it doesn't exist
mkdir -p "$SECRETS_DIR"

# Function to generate highly random system seed
generate_system_seed() {
    # Random length between 128 and 256 characters
    local length=$((RANDOM % 129 + 128))
    echo "Generating ${length}-character system seed..." >&2
    
    # Combine multiple sources of entropy
    local seed=$(cat /dev/urandom | tr -dc 'A-Za-z0-9@#$%^&*()_+[]{}|;:,.<>?~' | head -c $length)
    seed+=$(openssl rand -base64 64 | tr -dc 'A-Za-z0-9@#$%^&*()_+[]{}|;:,.<>?~' | head -c 64)
    seed+=$(date +%s%N | sha256sum | base64 | head -c 32)
    
    # Shuffle the combined string
    echo "$seed" | fold -w1 | shuf | tr -d '\n' | head -c $length
}

# Function to generate a complex random password
generate_password() {
    # Random length between 15 and 32 characters
    local length=$((RANDOM % 18 + 15))
    local chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:,.<>?'
    local password=""
    echo "Generating ${length}-character password..." >&2
    for ((i=0; i<length; i++)); do
        pos=$((RANDOM % ${#chars}))
        password+=${chars:$pos:1}
    done
    echo "$password"
}

# Function to create a secret file
create_secret() {
    local filename="$1"
    local content="$2"
    echo "$content" > "$SECRETS_DIR/$filename"
    chmod 600 "$SECRETS_DIR/$filename"
    echo "Created: $filename"
}

# Generate system seed
system_seed=$(generate_system_seed)
create_secret "system_seed.txt" "$system_seed"

# Generate Redis password
create_secret "redis_password.txt" "$(generate_password)"

# Generate PostgreSQL password
create_secret "pg_password.txt" "$(generate_password)"

# Generate training PostgreSQL password
create_secret "training_pg_password.txt" "$(generate_password)"

# Generate admin UI password
admin_password="$(generate_password)"
create_secret "admin_ui_password.txt" "$admin_password"

# Generate SMTP password
create_secret "smtp_password.txt" "$(generate_password)"

# Generate API keys
create_secret "external_api_key.txt" "key_$(openssl rand -hex 16)"
create_secret "ip_reputation_api_key.txt" "key_$(openssl rand -hex 16)"
create_secret "community_blocklist_api_key.txt" "key_$(openssl rand -hex 16)"

# Generate .htpasswd file
if command -v htpasswd >/dev/null 2>&1; then
    htpasswd_password="$(generate_password)_$(openssl rand -base64 32 | tr -d '/+=' | head -c 16)_$(date -u -d "$CURRENT_TIME" +%Y%m%d%H%M%S)"
    echo "$htpasswd_password" | htpasswd -ci "$SECRETS_DIR/.htpasswd" "$CURRENT_USER"
    chmod 600 "$SECRETS_DIR/.htpasswd"
    echo "Created: .htpasswd"
    echo -e "\nHTPasswd Credentials:"
    echo "Username: $CURRENT_USER"
    echo "Password: $htpasswd_password"
else
    echo "Warning: htpasswd command not found. Please install apache2-utils to generate .htpasswd file."
fi

# Print summary
echo -e "\nSecret files generated in $SECRETS_DIR:"
ls -l "$SECRETS_DIR"

# Print important passwords
echo -e "\nImportant Passwords (save these):"
echo "Admin UI Username: $CURRENT_USER"
echo "Admin UI Password: $admin_password"
echo "HTPasswd Username: $CURRENT_USER"
echo "HTPasswd Password: $htpasswd_password"
echo "System Seed: $system_seed"

echo -e "\nDone! Make sure to save these passwords securely and never commit them to version control."