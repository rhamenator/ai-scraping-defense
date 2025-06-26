# admin_ui/admin_ui.py
# Flask application for the Admin Metrics Dashboard

from flask import Flask, render_template, jsonify
from flask import Response as FlaskResponse # For type hinting if needed elsewhere
import os
import sys
from typing import Dict, Union, Tuple, Any, Callable # Added Callable
import json # For parsing, if needed
import datetime

# --- Global placeholder for the function that will provide metrics as a dictionary ---
_get_metrics_dict_func: Callable[[], Dict[str, Union[str, int, float, None]]]
METRICS_TRULY_AVAILABLE: bool = False

try:
    # Attempt to import the original get_metrics function that might return bytes
    from src.shared.metrics import get_metrics as _get_prometheus_metrics_bytes
    
    def _parse_prometheus_to_dict(prometheus_bytes: bytes) -> Dict[str, Union[str, int, float, None]]:
        """
        Parses Prometheus text format into a dictionary.
        This is a very basic parser and might need to be more robust for complex metrics.
        """
        metrics_data: Dict[str, Union[str, int, float, None]] = {}
        try:
            decoded_output = prometheus_bytes.decode('utf-8')
            # Add a general 'last_updated_utc' and 'service_uptime_seconds' if parsing Prometheus format
            # These might not be directly in Prometheus text format unless specifically added.
            # For admin UI, it's common to have these.
            # This parsing logic needs to be robust.
            # If your main metrics.py adds these to its output, this becomes simpler.
            
            # Example of very naive parsing (Prometheus format is more complex)
            # A proper Prometheus client library parser would be better here.
            lines = decoded_output.splitlines()
            raw_data_preview = []
            for line in lines:
                if line.startswith('#') or not line.strip():
                    continue
                raw_data_preview.append(line)
                parts = line.split(' ', 1) # Split metric name from value
                if len(parts) == 2:
                    metric_name_full = parts[0]
                    value_str = parts[1]
                    metric_base_name = metric_name_full.split('{')[0] # Get name before labels
                    try:
                        metrics_data[metric_base_name] = float(value_str)
                    except ValueError:
                        metrics_data[metric_base_name] = value_str # Store as string if not float
            
            if not metrics_data and decoded_output: # If parsing yields nothing but there was output
                 metrics_data["raw_metrics_preview"] = "\n".join(raw_data_preview[:5]) # Show first 5 lines
            elif not metrics_data and not decoded_output:
                 metrics_data["info"] = "Empty metrics data received from source"

            # Ensure standard fields expected by the frontend are present
            if "service_uptime_seconds" not in metrics_data:
                 metrics_data["service_uptime_seconds"] = -1 # Indicate not available from source
            if "last_updated_utc" not in metrics_data:
                 metrics_data["last_updated_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

            return metrics_data
        except Exception as e:
            return {"error": f"Failed to parse Prometheus metrics bytes: {str(e)}"}

    _get_metrics_dict_func = lambda: _parse_prometheus_to_dict(_get_prometheus_metrics_bytes())
    METRICS_TRULY_AVAILABLE = True
    print("Metrics module imported successfully. Metrics will be parsed.")

except ImportError as e:
    print(f"Warning: Could not import metrics module in Admin UI: {e}. Metrics will be unavailable.")
    def _dummy_get_metrics_dict() -> Dict[str, Union[str, int, float, None]]:
        # This is the fallback if the import fails
        return {"error": "Metrics module not available", "service_uptime_seconds": 0}
    _get_metrics_dict_func = _dummy_get_metrics_dict
    METRICS_TRULY_AVAILABLE = False

# --- Flask App Setup ---
app = Flask(__name__)
# Optional: Configure template folder if not 'templates'
# app.template_folder = 'path/to/templates'

# --- Routes ---

@app.route('/')
def index() -> str: # render_template returns a string
    """Serves the main dashboard HTML page."""
    print("Serving admin dashboard page.")
    return render_template('index.html')

@app.route('/metrics')
def metrics_endpoint() -> Tuple[FlaskResponse, int]: 
    """Provides the current metrics as JSON by calling the appropriate getter."""
    # METRICS_TRULY_AVAILABLE reflects the import status
    # _get_metrics_dict_func handles both cases (successful import+parse, or dummy)
    
    try:
        # _get_metrics_dict_func is guaranteed to be defined and return a Dict
        current_metrics: Dict[str, Any] = _get_metrics_dict_func()
        
        # If the import failed, the dummy function already includes an error.
        # If parsing failed, _parse_prometheus_to_dict includes an error.
        if "error" in current_metrics and METRICS_TRULY_AVAILABLE and "Failed to parse" in str(current_metrics.get("error")):
            # Parsing failed after successful import
            return jsonify(current_metrics), 500 
        elif "error" in current_metrics and not METRICS_TRULY_AVAILABLE:
            # Module import failed, dummy function is active
            return jsonify(current_metrics), 500

        return jsonify(current_metrics), 200
    except Exception as e:
        # This is a fallback for unexpected errors within this endpoint itself
        print(f"Error in metrics_endpoint: {e}")
        return jsonify({"error": "Failed to retrieve metrics due to an internal error in admin_ui"}), 500

if __name__ == '__main__':
    # Note: Running directly is for testing. Use docker-compose.yml for production.
    # Port 5002 is used as an example internal port in docker-compose.yml
    app.run(host='0.0.0.0', port=5002, debug=False)