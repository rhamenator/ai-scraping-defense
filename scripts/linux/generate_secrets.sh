#!/bin/bash
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
#   5. Protect exported secret files with strict permissions (mode 600)
#   6. Delete exported secret files after importing to your secret manager
#
# See SECURITY.md for comprehensive secret management guidelines.

# --- Configuration ---
GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
K8S_DIR="$ROOT_DIR/kubernetes"; mkdir -p "$K8S_DIR"; OUTPUT_FILE="$K8S_DIR/secrets.yaml"
HTPASSWD_OUTPUT_FILE="$ROOT_DIR/nginx/.htpasswd"

# --- Functions ---
generate_password() {
  LC_ALL=C tr -dc 'A-Za-z0-9_!@#$%^&*' < /dev/urandom | head -c "${1:-24}"
}

generate_username() {
  LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c "${1:-8}"
}
update_env=false
export_path=""

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
    *)
      shift
      ;;
  esac
done

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

# --- Main Logic ---
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}SECURITY WARNING: Development/Testing Only${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}This script generates secrets for DEVELOPMENT/TESTING only.${NC}"
echo -e "${YELLOW}For PRODUCTION, use a proper secret management solution:${NC}"
echo -e "${YELLOW}  • HashiCorp Vault, AWS Secrets Manager, Azure Key Vault${NC}"
echo -e "${YELLOW}  • Enable encryption at rest and implement key rotation${NC}"
echo -e "${YELLOW}  • See SECURITY.md for complete guidelines${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${CYAN}Generating secrets for Kubernetes...${NC}"

# Generate all values
POSTGRES_USER="postgres"; POSTGRES_DB="markov_db"; POSTGRES_PASSWORD=$(generate_password)
REDIS_PASSWORD=$(generate_password)
ADMIN_UI_USERNAME=${ADMIN_UI_USERNAME:-${SUDO_USER:-$USER}}
if [ -z "$ADMIN_UI_USERNAME" ]; then
  ADMIN_UI_USERNAME="admin-$(generate_username)"
fi
ADMIN_UI_PASSWORD=$(generate_password)
ADMIN_UI_PASSWORD_HASH=$(htpasswd -nbBC 12 "$ADMIN_UI_USERNAME" "$ADMIN_UI_PASSWORD" | cut -d: -f2 | tr -d '\n')
SYSTEM_SEED=$(generate_password 48)
NGINX_PASSWORD=$(generate_password 32)
EXTERNAL_API_KEY="key-for-$(generate_password)"; IP_REPUTATION_API_KEY="key-for-$(generate_password)"; COMMUNITY_BLOCKLIST_API_KEY="key-for-$(generate_password)"
OPENAI_API_KEY="sk-$(generate_password 40)"; ANTHROPIC_API_KEY="sk-ant-$(generate_password 40)"; GOOGLE_API_KEY="AIza$(generate_password 35)"; COHERE_API_KEY="coh-$(generate_password 40)"; MISTRAL_API_KEY="mistral-$(generate_password 40)"

# Create Nginx htpasswd content using bcrypt
HTPASSWD_FILE_CONTENT=$(htpasswd -nbBC 12 "$ADMIN_UI_USERNAME" "$NGINX_PASSWORD" | tr -d '\n')
# Write htpasswd file for local Docker Compose usage
echo "$HTPASSWD_FILE_CONTENT" > "$HTPASSWD_OUTPUT_FILE"

# Write YAML to file
cat > "$OUTPUT_FILE" << EOL
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

if [ -n "$export_path" ]; then
  # Security: Create file with restricted permissions before writing sensitive data
  touch "$export_path"
  chmod 600 "$export_path"

  cat > "$export_path" << EOF
{
  "ADMIN_UI_USERNAME": "$ADMIN_UI_USERNAME",
  "ADMIN_UI_PASSWORD": "$ADMIN_UI_PASSWORD",
  "NGINX_PASSWORD": "$NGINX_PASSWORD",
  "POSTGRES_PASSWORD": "$POSTGRES_PASSWORD",
  "REDIS_PASSWORD": "$REDIS_PASSWORD",
  "SYSTEM_SEED": "$SYSTEM_SEED",
  "OPENAI_API_KEY": "$OPENAI_API_KEY",
  "ANTHROPIC_API_KEY": "$ANTHROPIC_API_KEY",
  "GOOGLE_API_KEY": "$GOOGLE_API_KEY",
  "COHERE_API_KEY": "$COHERE_API_KEY",
  "MISTRAL_API_KEY": "$MISTRAL_API_KEY",
  "EXTERNAL_API_KEY": "$EXTERNAL_API_KEY",
  "IP_REPUTATION_API_KEY": "$IP_REPUTATION_API_KEY",
  "COMMUNITY_BLOCKLIST_API_KEY": "$COMMUNITY_BLOCKLIST_API_KEY",
  "_security_notice": "IMPORTANT: This file contains sensitive credentials. Delete after importing to your secret manager. Never commit to version control."
}
EOF
  echo -e "${GREEN}Credentials exported to: ${export_path} (mode 600)${NC}"
  echo -e "${YELLOW}⚠ SECURITY: Import to your secret manager and DELETE this file${NC}"
fi

# Do not print secrets to stdout. Provide only non-sensitive status.
echo -e "\n${GREEN}✓ Kubernetes secrets manifest created: ${OUTPUT_FILE}${NC}"
if [ -n "$export_path" ]; then
  echo -e "${GREEN}✓ Credentials exported to: ${export_path} (mode 600)${NC}"
  echo -e "${YELLOW}  ⚠ Delete this file after importing to your secret manager${NC}"
fi
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo -e "${YELLOW}  1.${NC} Review generated secrets (do not log or display)"
echo -e "${YELLOW}  2.${NC} Apply to Kubernetes: ${CYAN}kubectl apply -f ${OUTPUT_FILE}${NC}"
echo -e "${YELLOW}  3.${NC} Enable encryption at rest: ${CYAN}kubectl get secrets -n ai-defense${NC}"
echo -e "${YELLOW}  4.${NC} Set up secret rotation schedule (see SECURITY.md)"
echo ""
# Optionally update .env with generated values
if [ "$update_env" = true ]; then
  ENV_FILE="$ROOT_DIR/.env"
  if [ ! -f "$ENV_FILE" ] && [ -f "$ROOT_DIR/sample.env" ]; then
    cp "$ROOT_DIR/sample.env" "$ENV_FILE"
  fi

  echo -e "${YELLOW}⚠ WARNING: Storing secrets in .env file (ensure .env is in .gitignore)${NC}"
  echo -e "${CYAN}Updating ${ENV_FILE} with generated values...${NC}"

  # Set secure permissions on .env file
  chmod 600 "$ENV_FILE"
  update_var POSTGRES_PASSWORD "$POSTGRES_PASSWORD" "$ENV_FILE"
  update_var REDIS_PASSWORD "$REDIS_PASSWORD" "$ENV_FILE"
  update_var ADMIN_UI_USERNAME "$ADMIN_UI_USERNAME" "$ENV_FILE"
  update_var ADMIN_UI_PASSWORD_HASH "$ADMIN_UI_PASSWORD_HASH" "$ENV_FILE"
  update_var SYSTEM_SEED "$SYSTEM_SEED" "$ENV_FILE"
  update_var NGINX_PASSWORD "$NGINX_PASSWORD" "$ENV_FILE"
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
  chmod 700 "$SECRETS_DIR"

  # Create files with secure permissions before writing
  touch "$SECRETS_DIR/pg_password.txt" "$SECRETS_DIR/redis_password.txt"
  chmod 600 "$SECRETS_DIR/pg_password.txt" "$SECRETS_DIR/redis_password.txt"

  echo -n "$POSTGRES_PASSWORD" > "$SECRETS_DIR/pg_password.txt"
  echo -n "$REDIS_PASSWORD" > "$SECRETS_DIR/redis_password.txt"
  echo -e "${CYAN}✓ Secret files written to ${SECRETS_DIR} (mode 600)${NC}"
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ Secrets Generation Complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}IMPORTANT SECURITY REMINDERS:${NC}"
echo -e "${YELLOW}  • These secrets are for DEVELOPMENT/TESTING only${NC}"
echo -e "${YELLOW}  • DO NOT commit .env, secrets/, or exported JSON to git${NC}"
echo -e "${YELLOW}  • Use proper secret management for production (see SECURITY.md)${NC}"
echo -e "${YELLOW}  • Implement regular secret rotation schedules${NC}"
echo -e "${YELLOW}  • Enable encryption at rest for all secret storage${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
# End of script
