# admin_ui/admin_ui.py
# Flask application for the Admin Metrics Dashboard

from flask import Flask, render_template, jsonify
import os
import sys

# --- Import Shared Metrics Module ---
# Adjust path if metrics.py is located elsewhere relative to this script's execution context
# Assuming metrics.py is in the parent directory when run via docker-compose volumes
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from metrics import get_metrics
    METRICS_AVAILABLE = True
    print("Metrics module imported successfully by Admin UI.")
except ImportError as e:
    print(f"Warning: Could not import metrics module in Admin UI: {e}. Metrics will be unavailable.")
    # Define dummy function if metrics unavailable
    def get_metrics():
        return {"error": "Metrics module not available", "service_uptime_seconds": 0}
    METRICS_AVAILABLE = False

# --- Flask App Setup ---
app = Flask(__name__)
# Optional: Configure template folder if not 'templates'
# app.template_folder = 'path/to/templates'

# --- Routes ---

@app.route('/')
def index():
    """Serves the main dashboard HTML page."""
    # The actual metrics data will be fetched by JavaScript in the template via the /metrics endpoint
    print("Serving admin dashboard page.")
    return render_template('index.html')

@app.route('/metrics')
def metrics_endpoint():
    """Provides the current metrics as JSON."""
    if not METRICS_AVAILABLE:
        # Return an error status if metrics couldn't be loaded
        return jsonify({"error": "Metrics module unavailable"}), 500

    try:
        current_metrics = get_metrics()
        # print(f"Serving metrics: {current_metrics}") # Debug logging
        return jsonify(current_metrics)
    except Exception as e:
        print(f"Error retrieving metrics: {e}")
        return jsonify({"error": "Failed to retrieve metrics"}), 500

if __name__ == '__main__':
    # Note: Running directly is for testing. Use docker-compose.yml for production.
    # Port 5002 is used as an example internal port in docker-compose.yml
    app.run(host='0.0.0.0', port=5002, debug=False) # Set debug=True for development only