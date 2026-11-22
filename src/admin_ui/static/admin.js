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

// ---- Blocklist: browse, block and unblock (#1950) ----
const blocklistBody = document.getElementById('blocklist-body');
const blocklistStatus = document.getElementById('blocklist-status');
const blocklistSearch = document.getElementById('blocklist-search');
const blocklistError = document.getElementById('blocklist-error');
const blockForm = document.getElementById('block-form');
let blockedAddresses = [];

function csrfToken() {
    // The CSRF cookie is HttpOnly, so the server also renders the token into the page.
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

function showBlocklistError(message) {
    if (!blocklistError) return;
    blocklistError.textContent = message || '';
    blocklistError.hidden = !message;
}

function confirmAction(title, message) {
    const dialog = document.getElementById('confirm-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') {
        return Promise.resolve(window.confirm(`${title}\n\n${message}`));
    }
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    return new Promise(resolve => {
        dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true });
        dialog.returnValue = 'cancel';
        dialog.showModal();
    });
}

function renderBlocklist() {
    if (!blocklistBody) return;
    clearElement(blocklistBody);
    const query = blocklistSearch ? blocklistSearch.value.trim().toLowerCase() : '';
    const shown = blockedAddresses.filter(ip => !query || ip.toLowerCase().includes(query));
    for (const ip of shown) {
        const row = document.createElement('tr');
        const address = document.createElement('td');
        address.textContent = ip;
        const action = document.createElement('td');
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = 'Unblock';
        button.setAttribute('aria-label', `Unblock ${ip}`);
        button.addEventListener('click', () => unblockAddress(ip));
        action.appendChild(button);
        row.append(address, action);
        blocklistBody.appendChild(row);
    }
    if (blocklistStatus) {
        blocklistStatus.textContent = blockedAddresses.length
            ? `Showing ${shown.length} of ${blockedAddresses.length} blocked addresses.`
            : 'No addresses are blocked.';
    }
}

async function fetchBlocklist() {
    try {
        const response = await fetch('/blocklist', { credentials: 'same-origin' });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'The blocklist could not be loaded.');
        blockedAddresses = payload.map(String).sort();
        renderBlocklist();
    } catch (err) {
        if (blocklistStatus) blocklistStatus.textContent = `Blocklist unavailable: ${err.message}`;
    }
}

async function readChangeResponse(response) {
    let payload = {};
    try { payload = await response.json(); } catch (e) { /* non-JSON error body */ }
    if (!response.ok) {
        throw new Error(payload.error || payload.detail || `Request failed (${response.status}).`);
    }
    return payload;
}

function changeRequestInit(body) {
    return {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
        body: JSON.stringify(body)
    };
}

// Fixed URLs, one function each: the endpoints are never built from user input.
const blockRequest = async body => readChangeResponse(await fetch('/block', changeRequestInit(body)));
const unblockRequest = async body => readChangeResponse(await fetch('/unblock', changeRequestInit(body)));

async function unblockAddress(ip) {
    showBlocklistError('');
    if (!await confirmAction('Unblock this address?', `${ip} will be able to reach the protected site again.`)) return;
    try {
        await unblockRequest({ ip });
        await fetchBlocklist();
        fetchBlockStats();
    } catch (err) {
        showBlocklistError(err.message);
    }
}

async function blockAddress(event) {
    event.preventDefault();
    showBlocklistError('');
    const ip = document.getElementById('block-ip').value.trim();
    const reason = document.getElementById('block-reason').value.trim();
    if (!ip || !reason) {
        showBlocklistError('Enter both an IP address and a reason.');
        return;
    }
    if (!await confirmAction('Block this address?', `${ip} will be refused by the protected site. Reason: ${reason}`)) return;
    try {
        await blockRequest({ ip, reason });
        blockForm.reset();
        await fetchBlocklist();
        fetchBlockStats();
    } catch (err) {
        showBlocklistError(err.message);
    }
}

if (blocklistSearch) blocklistSearch.addEventListener('input', renderBlocklist);
if (blockForm) blockForm.addEventListener('submit', blockAddress);

// Start the WebSocket connection
connectWebSocket();

// Periodically fetch block statistics
fetchBlockStats();
setInterval(fetchBlockStats, 10000);

fetchBlocklist();
setInterval(fetchBlocklist, 30000);
