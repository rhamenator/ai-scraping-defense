#!/bin/bash
#
# Creates a complete Kubernetes secrets manifest for the entire application stack.

# --- Configuration ---
GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'
SCRIPT_DIR="$(dirname "$0")"
K8S_DIR="$SCRIPT_DIR/kubernetes"; mkdir -p "$K8S_DIR"; OUTPUT_FILE="$K8S_DIR/secrets.yaml"
HTPASSWD_OUTPUT_FILE="$SCRIPT_DIR/nginx/.htpasswd"

# --- Functions ---
generate_password() { LC_ALL=C tr -dc 'A-Za-z0-9_!@#$%^&*' < /dev/urandom | head -c "${1:-24}"; }

# --- Main Logic ---
echo -e "${CYAN}Generating secrets for Kubernetes...${NC}"

# Generate all values
POSTGRES_USER="postgres"; POSTGRES_DB="markov_db"; POSTGRES_PASSWORD=$(generate_password)
REDIS_PASSWORD=$(generate_password)
ADMIN_UI_USERNAME=${SUDO_USER:-$USER}; if [ -z "$ADMIN_UI_USERNAME" ]; then ADMIN_UI_USERNAME="defense-admin"; fi
ADMIN_UI_PASSWORD=$(generate_password)
SYSTEM_SEED=$(generate_password 48)
NGINX_PASSWORD=$(generate_password 32)
EXTERNAL_API_KEY="key-for-$(generate_password)"; IP_REPUTATION_API_KEY="key-for-$(generate_password)"; COMMUNITY_BLOCKLIST_API_KEY="key-for-$(generate_password)"; SMTP_PASSWORD=$(generate_password)
OPENAI_API_KEY="sk-$(generate_password 40)"; ANTHROPIC_API_KEY="sk-ant-$(generate_password 40)"; GOOGLE_API_KEY="AIza$(generate_password 35)"; COHERE_API_KEY="coh-$(generate_password 40)"; MISTRAL_API_KEY="mistral-$(generate_password 40)"

# Create Nginx htpasswd content using bcrypt
HTPASSWD_FILE_CONTENT=$(htpasswd -nbBC 12 "$ADMIN_UI_USERNAME" "$NGINX_PASSWORD" | tr -d '\n')
# Write htpasswd file for local Docker Compose usage
echo "$HTPASSWD_FILE_CONTENT" > "$HTPASSWD_OUTPUT_FILE"

# Write YAML to file
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
  ADMIN_UI_PASSWORD: $(echo -n "$ADMIN_UI_PASSWORD" | base64 | tr -d '\n')
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
  SMTP_PASSWORD: $(echo -n "$SMTP_PASSWORD" | base64 | tr -d '\n')
EOL

# Output credentials
echo -e "\nSuccessfully created Kubernetes secrets file at: ${GREEN}${OUTPUT_FILE}${NC}"
echo -e "${YELLOW}--- IMPORTANT: Save the following credentials in a secure place! ---${NC}"
echo -e "${CYAN}NGINX / Admin UI Credentials:${NC}"
echo "  Username: $ADMIN_UI_USERNAME"
echo "  Password: $NGINX_PASSWORD"
echo -e "${CYAN}Service Passwords & Keys:${NC}"
echo "  PostgreSQL Password: $POSTGRES_PASSWORD"
echo "  Redis Password:      $REDIS_PASSWORD"
echo "  System Seed:         $SYSTEM_SEED"
echo -e "${CYAN}LLM API Keys (placeholders, replace with real keys if needed):${NC}"
echo "  OpenAI API Key:    $OPENAI_API_KEY"
echo "  Anthropic API Key: $ANTHROPIC_API_KEY"
echo "  Google API Key:    $GOOGLE_API_KEY"
echo "  Cohere API Key:    $COHERE_API_KEY"
echo "  Mistral API Key:   $MISTRAL_API_KEY"
echo -e "${CYAN}IP Reputation API Key: ${NC}"
echo "  $IP_REPUTATION_API_KEY"
echo -e "${CYAN}Community Blocklist API Key: ${NC}"
echo "  $COMMUNITY_BLOCKLIST_API_KEY"
echo -e "${CYAN}SMTP Password: ${NC}"
echo "  $SMTP_PASSWORD"
echo -e "${CYAN}External API Key: ${NC}"
echo "  $EXTERNAL_API_KEY"
echo -e "${NC}"
echo -e "${YELLOW}--- End of credentials ---${NC}"
echo -e "${GREEN}Kubernetes secrets manifest file created at: ${OUTPUT_FILE}${NC}"
echo -e "${YELLOW}You can now apply the secrets to your Kubernetes cluster using:${NC}"
echo -e "  kubectl apply -f ${OUTPUT_FILE}${NC}"
echo -e "${GREEN}Secrets Generation Complete!${NC}"
echo -e "${NC}"
# End of script
