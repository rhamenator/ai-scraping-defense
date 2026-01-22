const metricsDisplay = document.getElementById('metrics-display');
const lastUpdatedElement = document.getElementById('last-updated');
const errorMessageElement = document.getElementById('error-message');
const blockStatsContainer = document.getElementById('block-stats');
const refreshInterval = 5000; // Attempt reconnect every 5 seconds if needed

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/metrics`);

    ws.onmessage = (event) => {
        errorMessageElement.style.display = 'none';
        try {
            const data = JSON.parse(event.data);
            if (data.error) {
                throw new Error(data.error);
            }
            updateMetricsDisplay(data);
        } catch (err) {
            console.error('Error processing WebSocket message:', err);
            errorMessageElement.textContent = `WebSocket error: ${err.message}`;
            errorMessageElement.style.display = 'block';
        }
    };

    ws.onerror = (event) => {
        console.error('WebSocket error observed:', event);
        errorMessageElement.textContent = 'WebSocket connection error';
        errorMessageElement.style.display = 'block';
    };

    ws.onclose = () => {
        // Attempt to reconnect after a delay
        setTimeout(connectWebSocket, refreshInterval);
    };
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

function clearElement(element) {
    while (element.firstChild) {
        element.removeChild(element.firstChild);
    }
}

function createMetricCard(title, value) {
    const card = document.createElement('div');
    card.className = 'metric-card';

    const heading = document.createElement('h3');
    heading.textContent = title;
    card.appendChild(heading);

    const metricValue = document.createElement('div');
    metricValue.className = 'metric-value';
    metricValue.textContent = String(value);
    card.appendChild(metricValue);

    return card;
}

function updateMetricsDisplay(metrics) {
    if (!metricsDisplay) {
        return;
    }

    clearElement(metricsDisplay);

    // Sort keys alphabetically for consistent order, except uptime/timestamp
    const sortedKeys = Object.keys(metrics)
        .filter(key => !key.includes('uptime_seconds') && !key.includes('last_updated_utc'))
        .sort();

    // Add uptime first
    if (metrics.service_uptime_seconds !== undefined) {
        const uptimeValue = formatMetricValue('service_uptime_seconds', metrics.service_uptime_seconds);
        metricsDisplay.appendChild(createMetricCard('Service Uptime', uptimeValue));
    }

    // Add other metrics
    for (const key of sortedKeys) {
        const label = formatMetricKey(key);
        const metricValue = formatMetricValue(key, metrics[key]);
        metricsDisplay.appendChild(createMetricCard(label, metricValue));
    }

    if (!metricsDisplay.firstChild) {
        metricsDisplay.textContent = 'No metrics available.';
    }

    // Update last updated time
    if (metrics.last_updated_utc) {
        lastUpdatedElement.textContent = `Last updated: ${formatMetricValue('last_updated_utc', metrics.last_updated_utc)}`;
    } else {
        lastUpdatedElement.textContent = `Last updated: ${new Date().toLocaleString()}`;
    }
}

function updateBlockStatsDisplay(stats) {
    if (!blockStatsContainer) return;
    clearElement(blockStatsContainer);

    const heading = document.createElement('h2');
    heading.textContent = 'Blocked Traffic';
    blockStatsContainer.appendChild(heading);

    const blockedIps = document.createElement('p');
    blockedIps.textContent = `Blocked IPs: ${stats.blocked_ip_count || 0}`;
    blockStatsContainer.appendChild(blockedIps);

    const temporaryBlocks = document.createElement('p');
    temporaryBlocks.textContent = `Temporary Blocks: ${stats.temporary_block_count || 0}`;
    blockStatsContainer.appendChild(temporaryBlocks);

    const totalBots = document.createElement('p');
    totalBots.textContent = `Total Bots Detected: ${stats.total_bots_detected || 0}`;
    blockStatsContainer.appendChild(totalBots);

    if (stats.recent_block_events && stats.recent_block_events.length) {
        const list = document.createElement('ul');
        for (const ev of stats.recent_block_events) {
            const ts = ev.timestamp ? new Date(ev.timestamp).toLocaleString() : '';
            const item = document.createElement('li');
            item.textContent = `${ev.ip || 'n/a'} - ${ev.reason || 'n/a'} - ${ts}`;
            list.appendChild(item);
        }
        blockStatsContainer.appendChild(list);
    }
}

function fetchBlockStats() {
    fetch('/block_stats')
        .then(resp => resp.json())
        .then(updateBlockStatsDisplay)
        .catch(err => console.error('Error fetching block stats:', err));
}

// Start the WebSocket connection
connectWebSocket();

// Periodically fetch block statistics
fetchBlockStats();
setInterval(fetchBlockStats, 10000);
