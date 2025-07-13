# src/admin_ui/admin_ui.py
import os
import asyncio
from flask import Flask, render_template, jsonify, request
from src.shared.redis_client import get_redis_connection
from src.shared.metrics import get_metrics

app = Flask(__name__)

@app.route('/')
def index():
    """Serves the main dashboard HTML page."""
    return render_template('index.html')

@app.route('/metrics')
def metrics_endpoint():
    """Provides the current metrics as Prometheus-formatted text."""
    try:
        metrics_data = get_metrics()
        return metrics_data, 200, {'Content-Type': 'text/plain; version=0.0.4'}
    except Exception as e:
        return str(e), 500

@app.route('/blocklist', methods=['GET'])
def get_blocklist():
    redis_conn = get_redis_connection()
    if not redis_conn:
        return jsonify({"error": "Redis service unavailable"}), 503
    
    blocklist_set = redis_conn.smembers('blocklist')
    # If blocklist_set is awaitable (async), await it
    if asyncio.iscoroutine(blocklist_set):
        blocklist_set = asyncio.run(blocklist_set)
    
    # Ensure blocklist_set is a set or list before converting to list
    if blocklist_set and isinstance(blocklist_set, (set, list)):
        return jsonify(list(blocklist_set))
    else:
        # If the set is empty or None, return an empty JSON array.
        return jsonify([])

@app.route('/block', methods=['POST'])
def block_ip():
    # Add a check to ensure request.json is not None.
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Invalid request, missing JSON body"}), 400
    
    ip = json_data.get('ip')
    if not ip:
        return jsonify({"error": "Invalid request, missing 'ip' key in JSON"}), 400
        
    redis_conn = get_redis_connection()
    if not redis_conn:
        return jsonify({"error": "Redis service unavailable"}), 503
        
    redis_conn.sadd('blocklist', ip)
    return jsonify({"status": "success", "ip": ip})

@app.route('/unblock', methods=['POST'])
def unblock_ip():
    # Add a check to ensure request.json is not None.
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Invalid request, missing JSON body"}), 400
        
    ip = json_data.get('ip')
    if not ip:
        return jsonify({"error": "Invalid request, missing 'ip' key in JSON"}), 400
        
    redis_conn = get_redis_connection()
    if not redis_conn:
        return jsonify({"error": "Redis service unavailable"}), 503
        
    redis_conn.srem('blocklist', ip)
    return jsonify({"status": "success", "ip": ip})

@app.route('/settings')
def settings_page():
    """Renders the system settings page."""
    current_settings = {
        "Model URI": os.getenv("MODEL_URI", "Not Set"),
        "Log Level": os.getenv("LOG_LEVEL", "INFO"),
        "Escalation Engine URL": os.getenv("ESCALATION_ENGINE_URL", "http://escalation_engine:8003/escalate"),
    }
    return render_template('settings.html', settings=current_settings)

if __name__ == '__main__':
    # Use environment variables for host and port, with defaults.
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("ADMIN_UI_PORT", 5002))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    app.run(host=host, port=port, debug=debug)
