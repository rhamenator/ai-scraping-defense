#!/bin/bash
#
# Unified secret generation script with HashiCorp Vault support.
# This script can generate secrets locally or store them in Vault.

set -euo pipefail

# --- Configuration ---
GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
K8S_DIR="$ROOT_DIR/kubernetes"
mkdir -p "$K8S_DIR"
OUTPUT_FILE="$K8S_DIR/secrets.yaml"
HTPASSWD_OUTPUT_FILE="$ROOT_DIR/nginx/.htpasswd"

# --- Functions ---
generate_password() {
  LC_ALL=C tr -dc 'A-Za-z0-9_!@#$%^&*' < /dev/urandom | head -c "${1:-24}"
}

print_usage() {
  cat << EOF
Usage: $0 [OPTIONS]

Generate secrets for AI Scraping Defense with optional Vault integration.

OPTIONS:
  --update-env          Update .env file with generated secrets
  --export-path PATH    Export secrets to JSON file at PATH
  --vault              Store secrets in HashiCorp Vault
  --vault-addr ADDR    Vault server address (default: VAULT_ADDR env var)
  --vault-token TOKEN  Vault authentication token (default: VAULT_TOKEN env var)
  --vault-mount PATH   Vault mount point (default: secret)
  --vault-path PREFIX  Vault secret path prefix (default: ai-defense)
  --help               Show this help message

EXAMPLES:
  # Generate secrets locally
  $0 --update-env --export-path /tmp/secrets.json

  # Generate and store in Vault
  $0 --vault --vault-addr https://vault.example.com:8200

  # Generate for Kubernetes without Vault
  $0
EOF
}

update_var() {
  local key="$1" value="$2" file="$3"
  # Escape dollar signs so docker compose doesn't treat them as variables
  local escaped="${value//\$/\$\$}"
  if grep -q "^${key}=" "$file"; then
    sed -i.bak "s|^${key}=.*|${key}=${escaped}|" "$file" && rm -f "${file}.bak"
  else
    echo "${key}=${escaped}" >> "$file"
  fi
}

store_in_vault() {
  local path="$1" key="$2" value="$3"
  local vault_addr="${VAULT_ADDR:-}"
  local vault_token="${VAULT_TOKEN:-}"
  local mount_point="${VAULT_MOUNT:-secret}"

  if [ -z "$vault_addr" ] || [ -z "$vault_token" ]; then
    echo -e "${RED}Error: VAULT_ADDR and VAULT_TOKEN must be set${NC}"
    return 1
  fi

  # Use KV v2 API
  local url="${vault_addr}/v1/${mount_point}/data/${path}"

  # Read existing secret to merge with new value
  local existing_data=""
  local existing_response
  existing_response=$(curl -s -H "X-Vault-Token: ${vault_token}" "${url}" || echo "")
  if [ -n "$existing_response" ]; then
    existing_data=$(echo "$existing_response" | jq -r '.data.data // {}' 2>/dev/null || echo "{}")
  else
    existing_data="{}"
  fi

  # Merge new key-value with existing data
  local merged_data
  merged_data=$(echo "$existing_data" | jq --arg key "$key" --arg value "$value" '. + {($key): $value}')

  # Write to Vault
  local response
  response=$(curl -s -w "\n%{http_code}" -X POST \
    -H "X-Vault-Token: ${vault_token}" \
    -H "Content-Type: application/json" \
    -d "{\"data\": $merged_data}" \
    "${url}")

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
    echo -e "${GREEN}✓${NC} Stored ${path}:${key} in Vault"
    return 0
  else
    echo -e "${RED}✗${NC} Failed to store ${path}:${key} in Vault (HTTP $http_code)"
    return 1
  fi
}

# --- Parse Arguments ---
update_env=false
export_path=""
use_vault=false
vault_path_prefix="ai-defense"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --update-env)
      update_env=true
      shift
      ;;
    --export-path)
      export_path="$2"
      shift 2
      ;;
    --vault)
      use_vault=true
      shift
      ;;
    --vault-addr)
      export VAULT_ADDR="$2"
      shift 2
      ;;
    --vault-token)
      export VAULT_TOKEN="$2"
      shift 2
      ;;
    --vault-mount)
      export VAULT_MOUNT="$2"
      shift 2
      ;;
    --vault-path)
      vault_path_prefix="$2"
      shift 2
      ;;
    --help)
      print_usage
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      print_usage
      exit 1
      ;;
  esac
done

# --- Main Logic ---
echo -e "${CYAN}=== AI Scraping Defense Secret Generator ===${NC}"
echo -e "${CYAN}Generating secrets...${NC}"

# Check for required tools
if ! command -v htpasswd &> /dev/null; then
  echo -e "${RED}Error: htpasswd command not found. Please install apache2-utils${NC}"
  exit 1
fi

if [ "$use_vault" = true ] && ! command -v jq &> /dev/null; then
  echo -e "${RED}Error: jq command not found. Required for Vault integration${NC}"
  exit 1
fi

# Generate all values
POSTGRES_USER="postgres"
POSTGRES_DB="markov_db"
POSTGRES_PASSWORD=$(generate_password)
REDIS_PASSWORD=$(generate_password)
ADMIN_UI_USERNAME=${SUDO_USER:-$USER}
if [ -z "$ADMIN_UI_USERNAME" ]; then
  ADMIN_UI_USERNAME="defense-admin"
fi
ADMIN_UI_PASSWORD=$(generate_password)
ADMIN_UI_PASSWORD_HASH=$(htpasswd -nbBC 12 "$ADMIN_UI_USERNAME" "$ADMIN_UI_PASSWORD" | cut -d: -f2 | tr -d '\n')
SYSTEM_SEED=$(generate_password 48)
NGINX_PASSWORD=$(generate_password 32)
EXTERNAL_API_KEY="key-for-$(generate_password)"
IP_REPUTATION_API_KEY="key-for-$(generate_password)"
COMMUNITY_BLOCKLIST_API_KEY="key-for-$(generate_password)"
OPENAI_API_KEY="sk-$(generate_password 40)"
ANTHROPIC_API_KEY="sk-ant-$(generate_password 40)"
GOOGLE_API_KEY="AIza$(generate_password 35)"
COHERE_API_KEY="coh-$(generate_password 40)"
MISTRAL_API_KEY="mistral-$(generate_password 40)"
JWT_SECRET=$(generate_password 64)

# Create Nginx htpasswd content using bcrypt
HTPASSWD_FILE_CONTENT=$(htpasswd -nbBC 12 "$ADMIN_UI_USERNAME" "$NGINX_PASSWORD" | tr -d '\n')
echo "$HTPASSWD_FILE_CONTENT" > "$HTPASSWD_OUTPUT_FILE"
echo -e "${GREEN}✓${NC} Created Nginx htpasswd file"

# Store in Vault if enabled
if [ "$use_vault" = true ]; then
  echo -e "${CYAN}Storing secrets in Vault...${NC}"

  store_in_vault "${vault_path_prefix}/database/postgres" "user" "$POSTGRES_USER"
  store_in_vault "${vault_path_prefix}/database/postgres" "database" "$POSTGRES_DB"
  store_in_vault "${vault_path_prefix}/database/postgres" "password" "$POSTGRES_PASSWORD"
  store_in_vault "${vault_path_prefix}/database/redis" "password" "$REDIS_PASSWORD"
  store_in_vault "${vault_path_prefix}/admin/credentials" "username" "$ADMIN_UI_USERNAME"
  store_in_vault "${vault_path_prefix}/admin/credentials" "password_hash" "$ADMIN_UI_PASSWORD_HASH"
  store_in_vault "${vault_path_prefix}/system/seed" "value" "$SYSTEM_SEED"
  store_in_vault "${vault_path_prefix}/nginx/auth" "password" "$NGINX_PASSWORD"
  store_in_vault "${vault_path_prefix}/auth/jwt_secret" "value" "$JWT_SECRET"
  store_in_vault "${vault_path_prefix}/api/external" "key" "$EXTERNAL_API_KEY"
  store_in_vault "${vault_path_prefix}/api/ip_reputation" "key" "$IP_REPUTATION_API_KEY"
  store_in_vault "${vault_path_prefix}/api/community_blocklist" "key" "$COMMUNITY_BLOCKLIST_API_KEY"
  store_in_vault "${vault_path_prefix}/llm/openai" "api_key" "$OPENAI_API_KEY"
  store_in_vault "${vault_path_prefix}/llm/anthropic" "api_key" "$ANTHROPIC_API_KEY"
  store_in_vault "${vault_path_prefix}/llm/google" "api_key" "$GOOGLE_API_KEY"
  store_in_vault "${vault_path_prefix}/llm/cohere" "api_key" "$COHERE_API_KEY"
  store_in_vault "${vault_path_prefix}/llm/mistral" "api_key" "$MISTRAL_API_KEY"

  echo -e "${GREEN}✓${NC} All secrets stored in Vault"
fi

# Write Kubernetes YAML manifest
cat > "$OUTPUT_FILE" << EOL
apiVersion: v1
kind: Secret
metadata:
  name: postgres-credentials
  namespace: ai-defense
type: Opaque
data:
  POSTGRES_USER: $(echo -n "$POSTGRES_USER" | base64 | tr -d '\n')
  POSTGRES_DB: $(echo -n "$POSTGRES_DB" | base64 | tr -d '\n')
  POSTGRES_PASSWORD: $(echo -n "$POSTGRES_PASSWORD" | base64 | tr -d '\n')
---
apiVersion: v1
kind: Secret
metadata:
  name: redis-credentials
  namespace: ai-defense
type: Opaque
data:
  REDIS_PASSWORD: $(echo -n "$REDIS_PASSWORD" | base64 | tr -d '\n')
---
apiVersion: v1
kind: Secret
metadata:
  name: admin-ui-credentials
  namespace: ai-defense
type: Opaque
data:
  ADMIN_UI_USERNAME: $(echo -n "$ADMIN_UI_USERNAME" | base64 | tr -d '\n')
  ADMIN_UI_PASSWORD_HASH: $(echo -n "$ADMIN_UI_PASSWORD_HASH" | base64 | tr -d '\n')
---
apiVersion: v1
kind: Secret
metadata:
  name: system-seed-secret
  namespace: ai-defense
type: Opaque
data:
  SYSTEM_SEED: $(echo -n "$SYSTEM_SEED" | base64 | tr -d '\n')
---
apiVersion: v1
kind: Secret
metadata:
  name: jwt-secret
  namespace: ai-defense
type: Opaque
data:
  JWT_SECRET: $(echo -n "$JWT_SECRET" | base64 | tr -d '\n')
---
apiVersion: v1
kind: Secret
metadata:
  name: nginx-auth
  namespace: ai-defense
type: Opaque
data:
  .htpasswd: $(echo -n "$HTPASSWD_FILE_CONTENT" | base64 | tr -d '\n')
---
apiVersion: v1
kind: Secret
metadata:
  name: external-api-keys
  namespace: ai-defense
type: Opaque
data:
  EXTERNAL_API_KEY: $(echo -n "$EXTERNAL_API_KEY" | base64 | tr -d '\n')
  OPENAI_API_KEY: $(echo -n "$OPENAI_API_KEY" | base64 | tr -d '\n')
  ANTHROPIC_API_KEY: $(echo -n "$ANTHROPIC_API_KEY" | base64 | tr -d '\n')
  GOOGLE_API_KEY: $(echo -n "$GOOGLE_API_KEY" | base64 | tr -d '\n')
  COHERE_API_KEY: $(echo -n "$COHERE_API_KEY" | base64 | tr -d '\n')
  MISTRAL_API_KEY: $(echo -n "$MISTRAL_API_KEY" | base64 | tr -d '\n')
  IP_REPUTATION_API_KEY: $(echo -n "$IP_REPUTATION_API_KEY" | base64 | tr -d '\n')
  COMMUNITY_BLOCKLIST_API_KEY: $(echo -n "$COMMUNITY_BLOCKLIST_API_KEY" | base64 | tr -d '\n')
EOL

echo -e "${GREEN}✓${NC} Created Kubernetes secrets manifest: ${OUTPUT_FILE}"

# Export to JSON if requested
if [ -n "$export_path" ]; then
  cat > "$export_path" << EOF
{
  "ADMIN_UI_USERNAME": "$ADMIN_UI_USERNAME",
  "ADMIN_UI_PASSWORD": "$ADMIN_UI_PASSWORD",
  "NGINX_PASSWORD": "$NGINX_PASSWORD",
  "POSTGRES_USER": "$POSTGRES_USER",
  "POSTGRES_DB": "$POSTGRES_DB",
  "POSTGRES_PASSWORD": "$POSTGRES_PASSWORD",
  "REDIS_PASSWORD": "$REDIS_PASSWORD",
  "SYSTEM_SEED": "$SYSTEM_SEED",
  "JWT_SECRET": "$JWT_SECRET",
  "OPENAI_API_KEY": "$OPENAI_API_KEY",
  "ANTHROPIC_API_KEY": "$ANTHROPIC_API_KEY",
  "GOOGLE_API_KEY": "$GOOGLE_API_KEY",
  "COHERE_API_KEY": "$COHERE_API_KEY",
  "MISTRAL_API_KEY": "$MISTRAL_API_KEY",
  "EXTERNAL_API_KEY": "$EXTERNAL_API_KEY",
  "IP_REPUTATION_API_KEY": "$IP_REPUTATION_API_KEY",
  "COMMUNITY_BLOCKLIST_API_KEY": "$COMMUNITY_BLOCKLIST_API_KEY"
}
EOF
  chmod 600 "$export_path"
  echo -e "${GREEN}✓${NC} Exported secrets to: ${export_path}"
fi

# Update .env file if requested
if [ "$update_env" = true ]; then
  ENV_FILE="$ROOT_DIR/.env"
  if [ ! -f "$ENV_FILE" ] && [ -f "$ROOT_DIR/sample.env" ]; then
    cp "$ROOT_DIR/sample.env" "$ENV_FILE"
  fi

  echo -e "${CYAN}Updating ${ENV_FILE}...${NC}"
  update_var POSTGRES_PASSWORD "$POSTGRES_PASSWORD" "$ENV_FILE"
  update_var REDIS_PASSWORD "$REDIS_PASSWORD" "$ENV_FILE"
  update_var ADMIN_UI_USERNAME "$ADMIN_UI_USERNAME" "$ENV_FILE"
  update_var ADMIN_UI_PASSWORD_HASH "$ADMIN_UI_PASSWORD_HASH" "$ENV_FILE"
  update_var SYSTEM_SEED "$SYSTEM_SEED" "$ENV_FILE"
  update_var NGINX_PASSWORD "$NGINX_PASSWORD" "$ENV_FILE"
  update_var AUTH_JWT_SECRET "$JWT_SECRET" "$ENV_FILE"
  update_var OPENAI_API_KEY "$OPENAI_API_KEY" "$ENV_FILE"
  update_var ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY" "$ENV_FILE"
  update_var GOOGLE_API_KEY "$GOOGLE_API_KEY" "$ENV_FILE"
  update_var COHERE_API_KEY "$COHERE_API_KEY" "$ENV_FILE"
  update_var MISTRAL_API_KEY "$MISTRAL_API_KEY" "$ENV_FILE"
  update_var EXTERNAL_API_KEY "$EXTERNAL_API_KEY" "$ENV_FILE"
  update_var IP_REPUTATION_API_KEY "$IP_REPUTATION_API_KEY" "$ENV_FILE"
  update_var COMMUNITY_BLOCKLIST_API_KEY "$COMMUNITY_BLOCKLIST_API_KEY" "$ENV_FILE"

  # Write secret files for Docker Compose
  SECRETS_DIR="$ROOT_DIR/secrets"
  mkdir -p "$SECRETS_DIR"
  echo -n "$POSTGRES_PASSWORD" > "$SECRETS_DIR/pg_password.txt"
  echo -n "$REDIS_PASSWORD" > "$SECRETS_DIR/redis_password.txt"
  chmod 600 "$SECRETS_DIR/pg_password.txt" "$SECRETS_DIR/redis_password.txt"
  echo -e "${GREEN}✓${NC} Updated .env and created secret files"
fi

# Summary
echo -e "\n${GREEN}=== Secret Generation Complete ===${NC}"
echo -e "${CYAN}Next steps:${NC}"
if [ "$use_vault" = true ]; then
  echo -e "  • Secrets stored in Vault at path: ${vault_path_prefix}"
  echo -e "  • Configure services to read from Vault using VAULT_ADDR and authentication"
fi
echo -e "  • Apply Kubernetes secrets: ${YELLOW}kubectl apply -f ${OUTPUT_FILE}${NC}"
if [ -n "$export_path" ]; then
  echo -e "  • Secure the exported secrets file: ${export_path}"
fi
if [ "$update_env" = true ]; then
  echo -e "  • Review and secure your .env file"
fi

echo -e "${YELLOW}⚠ Important: Keep all secret files secure and never commit them to version control${NC}"
