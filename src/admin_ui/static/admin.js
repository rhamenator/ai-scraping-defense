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

let lastMetricsSnapshot = null;
let metricsFilterText = '';
let metricsFilterCategory = 'all';
let histogramViewMode = 'chart';
const openTreeNodes = new Set(['cat:Traffic & Cache', 'cat:Security & Auth']);
let metricsControlsInitialized = false;
let metricsResultsHost = null;
let metricsCountEl = null;

function parseMetricKey(rawKey) {
    const braceIdx = rawKey.indexOf('{');
    if (braceIdx === -1) {
        return { baseName: rawKey, labels: '', labelMap: {} };
    }
    const baseName = rawKey.slice(0, braceIdx);
    const rawLabels = rawKey.slice(braceIdx + 1, rawKey.endsWith('}') ? -1 : undefined);
    const labelMap = {};
    const parts = [];
    for (const entry of rawLabels.split(',')) {
        const trimmed = entry.trim();
        if (!trimmed) continue;
        const eqIdx = trimmed.indexOf('=');
        if (eqIdx === -1) {
            parts.push(trimmed.replace(/"/g, ''));
            continue;
        }
        const k = trimmed.slice(0, eqIdx).trim();
        const v = trimmed.slice(eqIdx + 1).trim().replace(/^"|"$/g, '');
        labelMap[k] = v;
        parts.push(`${k}=${v}`);
    }
    return { baseName, labels: parts.join(', '), labelMap };
}

function categorizeMetric(baseName) {
    if (baseName.includes('login') || baseName.includes('auth') || baseName.includes('security') || baseName.includes('operational')) {
        return 'Security & Auth';
    }
    if (baseName.includes('tarpit') || baseName.includes('captcha') || baseName.includes('blocklist') || baseName.includes('community') || baseName.includes('reputation')) {
        return 'Defense & Blocklist';
    }
    if (baseName.includes('heuristic') || baseName.includes('frequency') || baseName.includes('rf_model') || baseName.includes('llm') || baseName.includes('anomaly')) {
        return 'Detection & ML';
    }
    if (baseName.includes('http_') || baseName.includes('request') || baseName.includes('cache_') || baseName.includes('performance_')) {
        return 'Traffic & Cache';
    }
    return 'System';
}

function formatMetricKey(key) {
    return key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, char => char.toUpperCase())
        .replace(/\bHttp\b/g, 'HTTP')
        .replace(/\bLlm\b/g, 'LLM')
        .replace(/\bIp\b/g, 'IP')
        .replace(/\bRf\b/g, 'RF');
}

function formatMetricValue(key, value) {
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
    if (key.includes('last_updated_utc')) {
        try {
            return new Date(value).toLocaleString();
        } catch (e) { return value; }
    }
    if (key.includes('duration_seconds_sum') && typeof value === 'number') {
        return `${(value * 1000).toFixed(2)} ms`;
    }
    if (typeof value === 'number') {
        return Number.isInteger(value)
            ? value.toLocaleString()
            : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
    }
    return value;
}

function clearElement(element) {
    while (element.firstChild) {
        element.removeChild(element.firstChild);
    }
}

function createMetricRow(category, title, labels, value) {
    const row = document.createElement('tr');

    const catCell = document.createElement('td');
    catCell.className = 'metric-cat-cell';
    catCell.textContent = category;
    row.appendChild(catCell);

    const labelCell = document.createElement('td');
    labelCell.className = 'metric-name-cell';
    labelCell.textContent = title;
    row.appendChild(labelCell);

    const scopeCell = document.createElement('td');
    scopeCell.className = 'metric-key-cell';
    scopeCell.textContent = labels || '—';
    row.appendChild(scopeCell);

    const valueCell = document.createElement('td');
    valueCell.className = 'metric-value-cell';
    valueCell.textContent = String(value);
    row.appendChild(valueCell);

    return row;
}

function formatBucketBoundary(le) {
    if (le === '+Inf') return '+Inf';
    const num = Number(le);
    if (Number.isNaN(num)) return le;
    return num < 1 ? `≤ ${Math.round(num * 1000)} ms` : `≤ ${num} s`;
}

function ensureMetricsChrome() {
    if (metricsControlsInitialized && metricsResultsHost && metricsDisplay.contains(metricsResultsHost)) {
        return;
    }
    clearElement(metricsDisplay);

    const toolbar = document.createElement('div');
    toolbar.className = 'metrics-toolbar';

    const filterGroup = document.createElement('div');
    filterGroup.className = 'metrics-filters';

    const searchInput = document.createElement('input');
    searchInput.type = 'search';
    searchInput.id = 'metrics-filter-input';
    searchInput.placeholder = 'Filter metrics or labels...';
    searchInput.value = metricsFilterText;
    searchInput.addEventListener('input', () => {
        metricsFilterText = searchInput.value.trim().toLowerCase();
        if (lastMetricsSnapshot) {
            renderMetricsContent(lastMetricsSnapshot);
        }
    });

    const catSelect = document.createElement('select');
    catSelect.id = 'metrics-category-filter';
    for (const [val, label] of [
        ['all', 'All categories'],
        ['Traffic & Cache', 'Traffic & Cache'],
        ['Security & Auth', 'Security & Auth'],
        ['Defense & Blocklist', 'Defense & Blocklist'],
        ['Detection & ML', 'Detection & ML'],
        ['System', 'System'],
    ]) {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = label;
        catSelect.appendChild(opt);
    }
    catSelect.value = metricsFilterCategory;
    catSelect.addEventListener('change', () => {
        metricsFilterCategory = catSelect.value;
        if (lastMetricsSnapshot) {
            renderMetricsContent(lastMetricsSnapshot);
        }
    });

    filterGroup.appendChild(searchInput);
    filterGroup.appendChild(catSelect);
    toolbar.appendChild(filterGroup);

    metricsCountEl = document.createElement('span');
    metricsCountEl.className = 'metrics-count';
    toolbar.appendChild(metricsCountEl);

    metricsResultsHost = document.createElement('div');
    metricsResultsHost.id = 'metrics-results-host';

    metricsDisplay.appendChild(toolbar);
    metricsDisplay.appendChild(metricsResultsHost);
    metricsControlsInitialized = true;
}

function matchesFilter(category, title, labels) {
    if (metricsFilterCategory !== 'all' && category !== metricsFilterCategory) {
        return false;
    }
    if (!metricsFilterText) {
        return true;
    }
    const haystack = `${category} ${title} ${labels}`.toLowerCase();
    return haystack.includes(metricsFilterText);
}

function makeStatefulDetails(nodeKey, className, defaultOpen = false) {
    const details = document.createElement('details');
    details.className = className;
    if (openTreeNodes.has(nodeKey) || (defaultOpen && !openTreeNodes.has(`closed:${nodeKey}`))) {
        details.open = true;
    }
    details.addEventListener('toggle', () => {
        if (details.open) {
            openTreeNodes.add(nodeKey);
            openTreeNodes.delete(`closed:${nodeKey}`);
        } else {
            openTreeNodes.delete(nodeKey);
            openTreeNodes.add(`closed:${nodeKey}`);
        }
    });
    return details;
}

function buildHistogramChartSvg(hist) {
    const svgNs = 'http://www.w3.org/2000/svg';
    const buckets = hist.buckets;
    // Convert Prometheus cumulative buckets into per-bucket differential counts for a true distribution chart
    const diffBuckets = buckets.map((b, idx) => {
        const prev = idx === 0 ? 0 : buckets[idx - 1].value;
        return { le: b.le, count: Math.max(0, b.value - prev), cumulative: b.value };
    });
    const maxBucket = Math.max(...diffBuckets.map(b => b.count), 1);

    const width = Math.max(360, diffBuckets.length * 46);
    const height = 148;
    const padLeft = 28;
    const padRight = 10;
    const padTop = 18;
    const padBottom = 34;
    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;
    const step = plotW / Math.max(diffBuckets.length, 1);
    const barW = Math.max(12, Math.min(28, step * 0.62));

    const svg = document.createElementNS(svgNs, 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('class', 'hist-svg');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${hist.title} distribution`);

    // Baseline axis
    const axis = document.createElementNS(svgNs, 'line');
    axis.setAttribute('x1', String(padLeft));
    axis.setAttribute('y1', String(padTop + plotH));
    axis.setAttribute('x2', String(width - padRight));
    axis.setAttribute('y2', String(padTop + plotH));
    axis.setAttribute('stroke', 'rgba(29,34,24,0.22)');
    axis.setAttribute('stroke-width', '1');
    svg.appendChild(axis);

    diffBuckets.forEach((b, i) => {
        const barH = b.count === 0 ? 2 : Math.max(4, (b.count / maxBucket) * plotH);
        const x = padLeft + i * step + (step - barW) / 2;
        const y = padTop + plotH - barH;

        const rect = document.createElementNS(svgNs, 'rect');
        rect.setAttribute('x', x.toFixed(1));
        rect.setAttribute('y', y.toFixed(1));
        rect.setAttribute('width', barW.toFixed(1));
        rect.setAttribute('height', barH.toFixed(1));
        rect.setAttribute('rx', '4');
        rect.setAttribute('fill', b.count > 0 ? '#8d2a1e' : 'rgba(29,34,24,0.12)');
        const titleEl = document.createElementNS(svgNs, 'title');
        titleEl.textContent = `${formatBucketBoundary(b.le)}: ${b.count} requests (cumulative ${b.cumulative})`;
        rect.appendChild(titleEl);
        svg.appendChild(rect);

        if (b.count > 0) {
            const valText = document.createElementNS(svgNs, 'text');
            valText.setAttribute('x', (x + barW / 2).toFixed(1));
            valText.setAttribute('y', (y - 4).toFixed(1));
            valText.setAttribute('text-anchor', 'middle');
            valText.setAttribute('class', 'hist-svg-val');
            valText.textContent = String(b.count);
            svg.appendChild(valText);
        }

        const lblText = document.createElementNS(svgNs, 'text');
        lblText.setAttribute('x', (x + barW / 2).toFixed(1));
        lblText.setAttribute('y', String(padTop + plotH + 14));
        lblText.setAttribute('text-anchor', 'middle');
        lblText.setAttribute('class', 'hist-svg-lbl');
        lblText.textContent = formatBucketBoundary(b.le).replace('≤ ', '');
        svg.appendChild(lblText);
    });

    return svg;
}

function renderHistogramSection(histograms) {
    if (histograms.length === 0) {
        return null;
    }
    const wrapper = document.createElement('div');
    wrapper.className = 'histogram-tree';

    const headerBar = document.createElement('div');
    headerBar.className = 'histogram-header-bar';

    const switcher = document.createElement('div');
    switcher.className = 'view-switch';
    switcher.setAttribute('role', 'group');
    switcher.setAttribute('aria-label', 'Histogram view mode');
    for (const [mode, label] of [['chart', 'Graphical'], ['tree', 'Tabular / Tree']]) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `view-switch-btn${histogramViewMode === mode ? ' active' : ''}`;
        btn.textContent = label;
        btn.addEventListener('click', () => {
            histogramViewMode = mode;
            if (lastMetricsSnapshot) {
                renderMetricsContent(lastMetricsSnapshot);
            }
        });
        switcher.appendChild(btn);
    }
    headerBar.appendChild(switcher);
    wrapper.appendChild(headerBar);

    for (const hist of histograms) {
        const nodeKey = `hist:${hist.title}:${hist.labels}`;
        const details = makeStatefulDetails(nodeKey, 'histogram-node', histogramViewMode === 'chart');

        const summary = document.createElement('summary');
        const titleSpan = document.createElement('span');
        titleSpan.className = 'hist-title';
        titleSpan.textContent = hist.title;

        const scopeSpan = document.createElement('span');
        scopeSpan.className = 'hist-scope';
        scopeSpan.textContent = hist.labels || 'all';

        const statsSpan = document.createElement('span');
        statsSpan.className = 'hist-stats';
        const avgMs = hist.count > 0 ? ((hist.sum / hist.count) * 1000).toFixed(2) : '0.00';
        const totalMs = (hist.sum * 1000).toFixed(2);
        statsSpan.textContent = `count: ${hist.count.toLocaleString()} · avg: ${avgMs} ms · total: ${totalMs} ms`;

        summary.appendChild(titleSpan);
        summary.appendChild(scopeSpan);
        summary.appendChild(statsSpan);
        details.appendChild(summary);

        if (histogramViewMode === 'chart') {
            const chartWrap = document.createElement('div');
            chartWrap.className = 'hist-chart-wrap';
            chartWrap.appendChild(buildHistogramChartSvg(hist));
            details.appendChild(chartWrap);
        } else {
            const bucketTable = document.createElement('table');
            bucketTable.className = 'bucket-table';
            const tbody = document.createElement('tbody');
            const maxCount = Math.max(hist.count, 1);

            for (const bucket of hist.buckets) {
                const tr = document.createElement('tr');
                const leTd = document.createElement('td');
                leTd.className = 'bucket-le';
                leTd.textContent = formatBucketBoundary(bucket.le);

                const barTd = document.createElement('td');
                barTd.className = 'bucket-bar-cell';
                const bar = document.createElement('div');
                bar.className = 'bucket-bar';
                bar.style.width = `${Math.round((bucket.value / maxCount) * 100)}%`;
                barTd.appendChild(bar);

                const valTd = document.createElement('td');
                valTd.className = 'metric-value-cell';
                valTd.textContent = bucket.value.toLocaleString();

                tr.appendChild(leTd);
                tr.appendChild(barTd);
                tr.appendChild(valTd);
                tbody.appendChild(tr);
            }
            bucketTable.appendChild(tbody);
            details.appendChild(bucketTable);
        }
        wrapper.appendChild(details);
    }

    return wrapper;
}

function renderMetricsTree(entries) {
    const treeRoot = document.createElement('div');
    treeRoot.className = 'metrics-tree';

    const byCategory = new Map();
    for (const item of entries) {
        if (!byCategory.has(item.category)) {
            byCategory.set(item.category, []);
        }
        byCategory.get(item.category).push(item);
    }

    for (const [category, items] of byCategory.entries()) {
        const catDetails = makeStatefulDetails(`cat:${category}`, 'metric-tree-group', Boolean(metricsFilterText));
        const catSummary = document.createElement('summary');

        const catTitle = document.createElement('span');
        catTitle.className = 'tree-cat-title';
        catTitle.textContent = category;

        const catMeta = document.createElement('span');
        catMeta.className = 'tree-cat-meta';
        catMeta.textContent = `${items.length} series`;

        catSummary.appendChild(catTitle);
        catSummary.appendChild(catMeta);
        catDetails.appendChild(catSummary);

        // Group identical metric titles with multiple label scopes into nested nodes
        const byTitle = new Map();
        for (const item of items) {
            if (!byTitle.has(item.title)) {
                byTitle.set(item.title, []);
            }
            byTitle.get(item.title).push(item);
        }

        const table = document.createElement('table');
        table.className = 'metrics-sheet tree-leaf-table';
        const tbody = document.createElement('tbody');
        let hasSingleRows = false;

        for (const [title, series] of byTitle.entries()) {
            if (series.length === 1) {
                hasSingleRows = true;
                const s = series[0];
                const tr = document.createElement('tr');
                const nameTd = document.createElement('td');
                nameTd.className = 'metric-name-cell';
                nameTd.textContent = s.title;
                const scopeTd = document.createElement('td');
                scopeTd.className = 'metric-key-cell';
                scopeTd.textContent = s.labels || '—';
                const valTd = document.createElement('td');
                valTd.className = 'metric-value-cell';
                valTd.textContent = String(s.formattedValue);
                tr.appendChild(nameTd);
                tr.appendChild(scopeTd);
                tr.appendChild(valTd);
                tbody.appendChild(tr);
            } else {
                const subDetails = makeStatefulDetails(
                    `series:${category}:${title}`,
                    'metric-series-node',
                    Boolean(metricsFilterText)
                );
                const subSummary = document.createElement('summary');
                const subTitle = document.createElement('span');
                subTitle.className = 'metric-name-cell';
                subTitle.textContent = title;

                const subMeta = document.createElement('span');
                subMeta.className = 'hist-stats';
                const numericSum = series.every(s => typeof s.rawValue === 'number')
                    ? series.reduce((acc, s) => acc + s.rawValue, 0)
                    : null;
                subMeta.textContent = numericSum !== null
                    ? `${series.length} scopes · total: ${formatMetricValue(series[0].baseName, numericSum)}`
                    : `${series.length} scopes`;

                subSummary.appendChild(subTitle);
                subSummary.appendChild(subMeta);
                subDetails.appendChild(subSummary);

                const subTable = document.createElement('table');
                subTable.className = 'metrics-sheet tree-leaf-table';
                const subBody = document.createElement('tbody');
                for (const s of series) {
                    const tr = document.createElement('tr');
                    const scopeTd = document.createElement('td');
                    scopeTd.className = 'metric-key-cell';
                    scopeTd.textContent = s.labels || '—';
                    const valTd = document.createElement('td');
                    valTd.className = 'metric-value-cell';
                    valTd.textContent = String(s.formattedValue);
                    tr.appendChild(scopeTd);
                    tr.appendChild(valTd);
                    subBody.appendChild(tr);
                }
                subTable.appendChild(subBody);
                subDetails.appendChild(subTable);
                catDetails.appendChild(subDetails);
            }
        }

        if (hasSingleRows) {
            table.appendChild(tbody);
            catDetails.appendChild(table);
        }
        treeRoot.appendChild(catDetails);
    }

    return treeRoot;
}

function renderMetricsContent(metrics) {
    clearElement(metricsResultsHost);

    const entries = [];
    const histMap = new Map();

    if (metrics.service_uptime_seconds !== undefined) {
        const uptimeValue = formatMetricValue('service_uptime_seconds', metrics.service_uptime_seconds);
        if (matchesFilter('System', 'Service Uptime', '')) {
            entries.push({
                category: 'System',
                baseName: 'service_uptime_seconds',
                title: 'Service Uptime',
                labels: '',
                rawValue: metrics.service_uptime_seconds,
                formattedValue: uptimeValue,
            });
        }
    }

    const sortedKeys = Object.keys(metrics)
        .filter(key => !key.includes('uptime_seconds') && !key.includes('last_updated_utc'))
        .sort();

    for (const rawKey of sortedKeys) {
        const { baseName, labels, labelMap } = parseMetricKey(rawKey);
        if (baseName.endsWith('_created')) {
            continue;
        }

        if (baseName.endsWith('_bucket') || baseName.endsWith('_count') || baseName.endsWith('_sum')) {
            const rootName = baseName.replace(/_(bucket|count|sum)$/, '');
            const isHistogramSeries = baseName.endsWith('_bucket') ||
                Object.keys(metrics).some(k => k.startsWith(`${rootName}_bucket{`));
            if (isHistogramSeries) {
                const nonLeLabels = Object.entries(labelMap)
                    .filter(([k]) => k !== 'le')
                    .map(([k, v]) => `${k}=${v}`)
                    .join(', ');
                const histKey = `${rootName}|${nonLeLabels}`;
                if (!histMap.has(histKey)) {
                    histMap.set(histKey, {
                        category: categorizeMetric(rootName),
                        title: formatMetricKey(rootName),
                        labels: nonLeLabels,
                        count: 0,
                        sum: 0,
                        buckets: [],
                    });
                }
                const entry = histMap.get(histKey);
                if (baseName.endsWith('_bucket')) {
                    entry.buckets.push({ le: labelMap.le || '+Inf', value: metrics[rawKey] });
                } else if (baseName.endsWith('_count')) {
                    entry.count = metrics[rawKey];
                } else if (baseName.endsWith('_sum')) {
                    entry.sum = metrics[rawKey];
                }
                continue;
            }
        }

        const category = categorizeMetric(baseName);
        const title = formatMetricKey(baseName);
        if (!matchesFilter(category, title, labels)) {
            continue;
        }
        entries.push({
            category,
            baseName,
            title,
            labels,
            rawValue: metrics[rawKey],
            formattedValue: formatMetricValue(baseName, metrics[rawKey]),
        });
    }

    const filteredHistograms = [];
    for (const hist of histMap.values()) {
        if (!matchesFilter(hist.category, hist.title, hist.labels)) {
            continue;
        }
        hist.buckets.sort((a, b) => {
            if (a.le === '+Inf') return 1;
            if (b.le === '+Inf') return -1;
            return Number(a.le) - Number(b.le);
        });
        filteredHistograms.push(hist);
    }

    if (metricsCountEl) {
        metricsCountEl.textContent = `${entries.length} metrics · ${filteredHistograms.length} histograms`;
    }

    if (entries.length === 0 && filteredHistograms.length === 0) {
        const empty = document.createElement('p');
        empty.textContent = 'No metrics match the current filter.';
        metricsResultsHost.appendChild(empty);
        return;
    }

    if (entries.length > 0) {
        metricsResultsHost.appendChild(renderMetricsTree(entries));
    }

    const histSection = renderHistogramSection(filteredHistograms);
    if (histSection) {
        metricsResultsHost.appendChild(histSection);
    }
}

function updateMetricsDisplay(metrics) {
    if (!metricsDisplay) {
        return;
    }
    lastMetricsSnapshot = metrics;
    ensureMetricsChrome();
    renderMetricsContent(metrics);

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
