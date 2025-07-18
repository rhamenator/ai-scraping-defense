const metricsDisplay = document.getElementById('metrics-display');
const lastUpdatedElement = document.getElementById('last-updated');
const errorMessageElement = document.getElementById('error-message');
const refreshInterval = 5000; // Refresh every 5 seconds (5000 ms)

async function fetchMetrics() {
    errorMessageElement.style.display = 'none'; // Hide error on new fetch attempt
    try {
        // Use relative URL to fetch from the same origin
        const response = await fetch('/metrics'); // Fetches from the Flask endpoint

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        if (data.error) {
             throw new Error(`API Error: ${data.error}`);
        }

        updateMetricsDisplay(data);

    } catch (error) {
        console.error('Error fetching metrics:', error);
        metricsDisplay.innerHTML = '<p>Could not load metrics.</p>'; // Clear display on error
        errorMessageElement.textContent = `Error fetching metrics: ${error.message}`;
        errorMessageElement.style.display = 'block';
        lastUpdatedElement.textContent = 'Last updated: Error';
    }
}

function formatMetricKey(key) {
    // Simple formatting: replace underscores with spaces and capitalize words
    return key.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
}

function formatMetricValue(key, value) {
    // Format uptime specifically
    if (key.includes('uptime_seconds')) {
        const totalSeconds = Math.floor(value);
        const days = Math.floor(totalSeconds / (3600 * 24));
        const hours = Math.floor((totalSeconds % (3600 * 24)) / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        let uptimeString = '';
        if (days > 0) uptimeString += `${days}d `;
        if (hours > 0 || days > 0) uptimeString += `${hours}h `;
        if (minutes > 0 || hours > 0 || days > 0) uptimeString += `${minutes}m `;
        uptimeString += `${seconds}s`;
        return uptimeString || '0s';
    }
    // Format timestamp
     if (key.includes('last_updated_utc')) {
         try {
             return new Date(value).toLocaleString();
         } catch (e) { return value; } // Fallback if date parsing fails
     }
    // Default formatting for numbers
    if (typeof value === 'number') {
        return value.toLocaleString(); // Add commas for large numbers
    }
    return value; // Return other types as is
}

function updateMetricsDisplay(metrics) {
    let html = '';
    // Sort keys alphabetically for consistent order, except uptime/timestamp
    const sortedKeys = Object.keys(metrics)
        .filter(key => !key.includes('uptime_seconds') && !key.includes('last_updated_utc'))
        .sort();

    // Add uptime first
    if (metrics.service_uptime_seconds !== undefined) {
         html += `
            <div class="metric-card">
                <h3>Service Uptime</h3>
                <div class="metric-value">${formatMetricValue('service_uptime_seconds', metrics.service_uptime_seconds)}</div>
            </div>`;
    }

    // Add other metrics
    for (const key of sortedKeys) {
        html += `
            <div class="metric-card">
                <h3>${formatMetricKey(key)}</h3>
                <div class="metric-value">${formatMetricValue(key, metrics[key])}</div>
            </div>`;
    }

    metricsDisplay.innerHTML = html || '<p>No metrics available.</p>'; // Handle empty metrics case

    // Update last updated time
     if (metrics.last_updated_utc) {
         lastUpdatedElement.textContent = `Last updated: ${formatMetricValue('last_updated_utc', metrics.last_updated_utc)}`;
     } else {
         lastUpdatedElement.textContent = `Last updated: ${new Date().toLocaleString()}`;
     }
}

// Initial fetch and set interval for refreshing
fetchMetrics();
setInterval(fetchMetrics, refreshInterval);
