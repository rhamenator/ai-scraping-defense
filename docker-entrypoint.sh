#!/bin/bash
# This script acts as the entrypoint for multiple services.
# It ensures dependencies are ready and performs one-time initialization tasks
# before launching the main application process.

set -e

# Define the expected path for the bot detection model.
# The MODEL_PATH env var should be set in docker-compose.yaml.
MODEL_FILE="${MODEL_PATH:-/app/models/bot_detection_rf_model.joblib}"

# --- Wait for PostgreSQL ---
# Ensures the database is ready before any application logic runs.
echo "Waiting for postgres..."
# The password file is used securely.
export PGPASSWORD=$(cat "$PG_PASSWORD_FILE")
while ! pg_isready -h "$PG_HOST" -p 5432 -q -U "$PG_USER"; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done
echo "PostgreSQL is up - proceeding."

# --- Automatic Model Training ---
# Checks if the bot detection model exists. If not, it runs the training script.
# This logic is triggered only by the service designated as the trainer.
if [ "$RUN_MODEL_TRAINING" == "true" ] && [ ! -f "$MODEL_FILE" ]; then
  echo "Bot detection model not found at $MODEL_FILE. Starting training..."
  # Ensure the target directory exists.
  mkdir -p /app/models
  # Run the training script from its new location in src/
  python src/rag/training.py
  echo "Training complete. Model saved to $MODEL_FILE"
else
  echo "Skipping bot detection model training."
fi

# Execute the main command passed to the container (e.g., uvicorn, gunicorn).
echo "Launching main command: $@"
exec "$@"