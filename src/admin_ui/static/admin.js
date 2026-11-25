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

const CATEGORY_RULES = [
    ['Security & Auth', ['login', 'auth', 'security', 'operational']],
    ['Defense & Blocklist', ['tarpit', 'captcha', 'blocklist', 'community', 'reputation']],
    ['Detection & ML', ['heuristic', 'frequency', 'rf_model', 'llm', 'anomaly']],
    ['Traffic & Cache', ['http_', 'request', 'cache_', 'performance_']],
];

function parseMetricKey(rawKey) {
    const braceIdx = rawKey.indexOf('{');
    if (braceIdx === -1) {
        return { baseName: rawKey, labels: '', labelMap: new Map() };
    }
    const baseName = rawKey.slice(0, braceIdx);
    const rawLabels = rawKey.slice(braceIdx + 1, rawKey.endsWith('}') ? -1 : undefined);
    const labelMap = new Map();
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
        labelMap.set(k, v);
        parts.push(`${k}=${v}`);
    }
    return { baseName, labels: parts.join(', '), labelMap };
}

function categorizeMetric(baseName) {
    for (const [category, tokens] of CATEGORY_RULES) {
        if (tokens.some(token => baseName.includes(token))) {
            return category;
        }
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

function formatUptime(value) {
    const totalSeconds = Math.floor(value);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const parts = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0 || days > 0) parts.push(`${hours}h`);
    if (minutes > 0 || hours > 0 || days > 0) parts.push(`${minutes}m`);
    parts.push(`${seconds}s`);
    return parts.join(' ');
}

function formatBytes(value) {
    if (value >= 1048576) return `${(value / 1048576).toFixed(2)} MB`;
    if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${Math.round(value).toLocaleString()} B`;
}

function formatNumber(value) {
    return Number.isInteger(value)
        ? value.toLocaleString()
        : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function formatMetricValue(key, value) {
    if (key.includes('uptime_seconds')) return formatUptime(value);
    if (key.includes('last_updated_utc')) {
        try { return new Date(value).toLocaleString(); } catch (_e) { return value; }
    }
    if (typeof value !== 'number') return value;
    if (key.includes('duration_seconds_sum')) return `${(value * 1000).toFixed(2)} ms`;
    if (key.endsWith('_bytes')) return formatBytes(value);
    return formatNumber(value);
}

function clearElement(element) {
    while (element.firstChild) {
        element.removeChild(element.firstChild);
    }
}

function detectHistogramUnit(rootName) {
    if (rootName.includes('seconds') || rootName.includes('duration') || rootName.includes('latency')) {
        return 'seconds';
    }
    if (rootName.endsWith('_bytes') || rootName.includes('_bytes_')) {
        return 'bytes';
    }
    return 'count';
}

function formatBucketBoundary(le, unit = 'seconds') {
    if (le === '+Inf') return '+Inf';
    const num = Number(le);
    if (Number.isNaN(num)) return le;
    if (unit === 'seconds') {
        return num < 1 ? `≤ ${Math.round(num * 1000)} ms` : `≤ ${num} s`;
    }
    if (unit === 'bytes') {
        return `≤ ${formatBytes(num)}`;
    }
    return `≤ ${formatNumber(num)}`;
}

function formatHistogramStats(hist) {
    const avg = hist.count > 0 ? hist.sum / hist.count : 0;
    const countText = `count: ${hist.count.toLocaleString()}`;
    if (hist.unit === 'seconds') {
        return `${countText} · avg: ${(avg * 1000).toFixed(2)} ms · total: ${(hist.sum * 1000).toFixed(2)} ms`;
    }
    if (hist.unit === 'bytes') {
        return `${countText} · avg: ${formatBytes(avg)} · total: ${formatBytes(hist.sum)}`;
    }
    return `${countText} · avg: ${formatNumber(avg)} · total: ${formatNumber(hist.sum)}`;
}

function buildCategorySelect() {
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
        if (lastMetricsSnapshot) renderMetricsContent(lastMetricsSnapshot);
    });
    return catSelect;
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
        if (lastMetricsSnapshot) renderMetricsContent(lastMetricsSnapshot);
    });

    filterGroup.appendChild(searchInput);
    filterGroup.appendChild(buildCategorySelect());
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
    if (!metricsFilterText) return true;
    return `${category} ${title} ${labels}`.toLowerCase().includes(metricsFilterText);
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

function svgEl(tag, attrs, text) {
    const svgNs = 'http:' + '//www.w3.org/2000/svg';
    const el = document.createElementNS(svgNs, tag);
    for (const [k, v] of Object.entries(attrs)) {
        el.setAttribute(k, String(v));
    }
    if (text !== undefined) el.textContent = text;
    return el;
}

function appendSvgBar(svg, bucket, idx, geom) {
    const barH = bucket.count === 0 ? 2 : Math.max(4, (bucket.count / geom.maxBucket) * geom.plotH);
    const x = geom.padLeft + idx * geom.step + (geom.step - geom.barW) / 2;
    const y = geom.padTop + geom.plotH - barH;
    const rect = svgEl('rect', {
        x: x.toFixed(1),
        y: y.toFixed(1),
        width: geom.barW.toFixed(1),
        height: barH.toFixed(1),
        rx: 4,
        fill: bucket.count > 0 ? '#8d2a1e' : 'rgba(29,34,24,0.12)',
    });
    const boundary = formatBucketBoundary(bucket.le, geom.unit);
    rect.appendChild(svgEl('title', {}, `${boundary}: ${bucket.count} (cumulative ${bucket.cumulative})`));
    svg.appendChild(rect);
    if (bucket.count > 0) {
        svg.appendChild(svgEl('text', {
            x: (x + geom.barW / 2).toFixed(1),
            y: (y - 4).toFixed(1),
            'text-anchor': 'middle',
            class: 'hist-svg-val',
        }, String(bucket.count)));
    }
    svg.appendChild(svgEl('text', {
        x: (x + geom.barW / 2).toFixed(1),
        y: geom.padTop + geom.plotH + 14,
        'text-anchor': 'middle',
        class: 'hist-svg-lbl',
    }, boundary.replace('≤ ', '')));
}

function buildHistogramChartSvg(hist) {
    const diffBuckets = hist.buckets.map((b, idx) => {
        const prev = idx === 0 ? 0 : hist.buckets[idx - 1].value;
        return { le: b.le, count: Math.max(0, b.value - prev), cumulative: b.value };
    });
    const width = Math.max(360, diffBuckets.length * 46);
    const geom = {
        padLeft: 28,
        padTop: 18,
        plotH: 96,
        step: (width - 38) / Math.max(diffBuckets.length, 1),
        maxBucket: Math.max(...diffBuckets.map(b => b.count), 1),
        unit: hist.unit,
    };
    geom.barW = Math.max(12, Math.min(28, geom.step * 0.62));

    const svg = svgEl('svg', {
        viewBox: `0 0 ${width} 148`,
        class: 'hist-svg',
        role: 'img',
        'aria-label': `${hist.title} distribution`,
    });
    svg.appendChild(svgEl('line', {
        x1: geom.padLeft,
        y1: geom.padTop + geom.plotH,
        x2: width - 10,
        y2: geom.padTop + geom.plotH,
        stroke: 'rgba(29,34,24,0.22)',
        'stroke-width': 1,
    }));
    diffBuckets.forEach((b, i) => appendSvgBar(svg, b, i, geom));
    return svg;
}

function buildHistogramBucketTable(hist) {
    const table = document.createElement('table');
    table.className = 'bucket-table';
    const tbody = document.createElement('tbody');
    const maxCount = Math.max(hist.count, 1);

    for (const bucket of hist.buckets) {
        const tr = document.createElement('tr');
        const leTd = document.createElement('td');
        leTd.className = 'bucket-le';
        leTd.textContent = formatBucketBoundary(bucket.le, hist.unit);

        const barTd = document.createElement('td');
        barTd.className = 'bucket-bar-cell';
        const bar = document.createElement('div');
        bar.className = 'bucket-bar';
        bar.style.width = `${Math.round((bucket.value / maxCount) * 100)}%`;
        barTd.appendChild(bar);

        const valTd = document.createElement('td');
        valTd.className = 'metric-value-cell';
        valTd.textContent = bucket.value.toLocaleString();

        tr.append(leTd, barTd, valTd);
        tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    return table;
}

function buildViewSwitcher() {
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
            if (lastMetricsSnapshot) renderMetricsContent(lastMetricsSnapshot);
        });
        switcher.appendChild(btn);
    }
    return switcher;
}

function buildHistogramNode(hist) {
    const details = makeStatefulDetails(`hist:${hist.title}:${hist.labels}`, 'histogram-node', histogramViewMode === 'chart');
    const summary = document.createElement('summary');
    const titleSpan = document.createElement('span');
    titleSpan.className = 'hist-title';
    titleSpan.textContent = hist.title;

    const scopeSpan = document.createElement('span');
    scopeSpan.className = 'hist-scope';
    scopeSpan.textContent = hist.labels || 'all';

    const statsSpan = document.createElement('span');
    statsSpan.className = 'hist-stats';
    statsSpan.textContent = formatHistogramStats(hist);

    summary.append(titleSpan, scopeSpan, statsSpan);
    details.appendChild(summary);

    if (histogramViewMode === 'chart') {
        const chartWrap = document.createElement('div');
        chartWrap.className = 'hist-chart-wrap';
        chartWrap.appendChild(buildHistogramChartSvg(hist));
        details.appendChild(chartWrap);
    } else {
        details.appendChild(buildHistogramBucketTable(hist));
    }
    return details;
}

function renderHistogramSection(histograms) {
    if (histograms.length === 0) return null;
    const wrapper = document.createElement('div');
    wrapper.className = 'histogram-tree';

    const headerBar = document.createElement('div');
    headerBar.className = 'histogram-header-bar';
    headerBar.appendChild(buildViewSwitcher());
    wrapper.appendChild(headerBar);

    for (const hist of histograms) {
        wrapper.appendChild(buildHistogramNode(hist));
    }
    return wrapper;
}

function buildLeafRow(item, includeName) {
    const tr = document.createElement('tr');
    if (includeName) {
        const nameTd = document.createElement('td');
        nameTd.className = 'metric-name-cell';
        nameTd.textContent = item.title;
        tr.appendChild(nameTd);
    }
    const scopeTd = document.createElement('td');
    scopeTd.className = 'metric-key-cell';
    scopeTd.textContent = item.labels || '—';
    const valTd = document.createElement('td');
    valTd.className = 'metric-value-cell';
    valTd.textContent = String(item.formattedValue);
    tr.append(scopeTd, valTd);
    return tr;
}

function buildSeriesNode(category, title, series) {
    const subDetails = makeStatefulDetails(`series:${category}:${title}`, 'metric-series-node', Boolean(metricsFilterText));
    const subSummary = document.createElement('summary');
    const subTitle = document.createElement('span');
    subTitle.className = 'metric-name-cell';
    subTitle.textContent = title;

    const subMeta = document.createElement('span');
    subMeta.className = 'hist-stats';
    const allNumeric = series.every(s => typeof s.rawValue === 'number');
    if (allNumeric) {
        const total = series.reduce((acc, s) => acc + s.rawValue, 0);
        subMeta.textContent = `${series.length} scopes · total: ${formatMetricValue(series[0].baseName, total)}`;
    } else {
        subMeta.textContent = `${series.length} scopes`;
    }
    subSummary.append(subTitle, subMeta);
    subDetails.appendChild(subSummary);

    const subTable = document.createElement('table');
    subTable.className = 'metrics-sheet tree-leaf-table';
    const subBody = document.createElement('tbody');
    series.forEach(s => subBody.appendChild(buildLeafRow(s, false)));
    subTable.appendChild(subBody);
    subDetails.appendChild(subTable);
    return subDetails;
}

function buildCategoryGroup(category, items) {
    const catDetails = makeStatefulDetails(`cat:${category}`, 'metric-tree-group', Boolean(metricsFilterText));
    const catSummary = document.createElement('summary');
    const catTitle = document.createElement('span');
    catTitle.className = 'tree-cat-title';
    catTitle.textContent = category;
    const catMeta = document.createElement('span');
    catMeta.className = 'tree-cat-meta';
    catMeta.textContent = `${items.length} series`;
    catSummary.append(catTitle, catMeta);
    catDetails.appendChild(catSummary);

    const byTitle = new Map();
    for (const item of items) {
        if (!byTitle.has(item.title)) byTitle.set(item.title, []);
        byTitle.get(item.title).push(item);
    }

    const tbody = document.createElement('tbody');
    for (const [title, series] of byTitle.entries()) {
        if (series.length === 1) {
            tbody.appendChild(buildLeafRow(series[0], true));
        } else {
            catDetails.appendChild(buildSeriesNode(category, title, series));
        }
    }
    if (tbody.hasChildNodes()) {
        const table = document.createElement('table');
        table.className = 'metrics-sheet tree-leaf-table';
        table.appendChild(tbody);
        catDetails.appendChild(table);
    }
    return catDetails;
}

function renderMetricsTree(entries) {
    const treeRoot = document.createElement('div');
    treeRoot.className = 'metrics-tree';
    const byCategory = new Map();
    for (const item of entries) {
        if (!byCategory.has(item.category)) byCategory.set(item.category, []);
        byCategory.get(item.category).push(item);
    }
    for (const [category, items] of byCategory.entries()) {
        treeRoot.appendChild(buildCategoryGroup(category, items));
    }
    return treeRoot;
}

function recordHistogramSample(histMap, metricKeys, rawValue, parsed) {
    const { baseName, labelMap } = parsed;
    if (!/_(bucket|count|sum)$/.test(baseName)) return false;
    const rootName = baseName.replace(/_(bucket|count|sum)$/, '');
    const hasBuckets = baseName.endsWith('_bucket') || metricKeys.some(k => k.startsWith(`${rootName}_bucket{`));
    if (!hasBuckets) return false;

    const nonLeLabels = [...labelMap.entries()]
        .filter(([k]) => k !== 'le')
        .map(([k, v]) => `${k}=${v}`)
        .join(', ');
    const histKey = `${rootName}|${nonLeLabels}`;
    if (!histMap.has(histKey)) {
        histMap.set(histKey, {
            category: categorizeMetric(rootName),
            unit: detectHistogramUnit(rootName),
            title: formatMetricKey(rootName),
            labels: nonLeLabels,
            count: 0,
            sum: 0,
            buckets: [],
        });
    }
    const entry = histMap.get(histKey);
    if (baseName.endsWith('_bucket')) entry.buckets.push({ le: labelMap.get('le') || '+Inf', value: rawValue });
    else if (baseName.endsWith('_count')) entry.count = rawValue;
    else entry.sum = rawValue;
    return true;
}

function collectMetricsAndHistograms(metrics) {
    const entries = [];
    const histMap = new Map();
    const metricEntries = new Map(Object.entries(metrics));
    const metricKeys = [...metricEntries.keys()];
    if (metrics.service_uptime_seconds !== undefined && matchesFilter('System', 'Service Uptime', '')) {
        entries.push({
            category: 'System',
            baseName: 'service_uptime_seconds',
            title: 'Service Uptime',
            labels: '',
            rawValue: metrics.service_uptime_seconds,
            formattedValue: formatUptime(metrics.service_uptime_seconds),
        });
    }
    const keys = metricKeys.filter(k => !k.includes('uptime_seconds') && !k.includes('last_updated_utc')).sort();
    for (const rawKey of keys) {
        const rawValue = metricEntries.get(rawKey);
        const parsed = parseMetricKey(rawKey);
        if (parsed.baseName.endsWith('_created')) continue;
        if (recordHistogramSample(histMap, metricKeys, rawValue, parsed)) continue;
        const category = categorizeMetric(parsed.baseName);
        const title = formatMetricKey(parsed.baseName);
        if (!matchesFilter(category, title, parsed.labels)) continue;
        entries.push({
            category,
            baseName: parsed.baseName,
            title,
            labels: parsed.labels,
            rawValue,
            formattedValue: formatMetricValue(parsed.baseName, rawValue),
        });
    }
    const histograms = [...histMap.values()].filter(h => matchesFilter(h.category, h.title, h.labels));
    histograms.forEach(h => h.buckets.sort((a, b) => (a.le === '+Inf' ? 1 : b.le === '+Inf' ? -1 : Number(a.le) - Number(b.le))));
    return { entries, histograms };
}

function renderMetricsContent(metrics) {
    clearElement(metricsResultsHost);
    const { entries, histograms } = collectMetricsAndHistograms(metrics);
    if (metricsCountEl) {
        metricsCountEl.textContent = `${entries.length} metrics · ${histograms.length} histograms`;
    }
    if (entries.length === 0 && histograms.length === 0) {
        const empty = document.createElement('p');
        empty.textContent = 'No metrics match the current filter.';
        metricsResultsHost.appendChild(empty);
        return;
    }
    if (entries.length > 0) metricsResultsHost.appendChild(renderMetricsTree(entries));
    const histSection = renderHistogramSection(histograms);
    if (histSection) metricsResultsHost.appendChild(histSection);
}

function updateMetricsDisplay(metrics) {
    if (!metricsDisplay) return;
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

// Error bodies are either {"error": "text"}, {"detail": "text"} or {"error": {"message": "text"}, "detail": "text"}; never print an object.
function errorText(payload, fallback) {
    const pick = (v) => (typeof v === 'string' && v ? v : (v && typeof v.message === 'string' && v.message ? v.message : ''));
    return pick(payload && payload.detail) || pick(payload && payload.error) || fallback;
}

async function fetchBlocklist() {
    try {
        const response = await fetch('/blocklist', { credentials: 'same-origin' });
        const payload = await response.json();
        if (!response.ok) throw new Error(errorText(payload, 'The blocklist could not be loaded.'));
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
        throw new Error(errorText(payload, `Request failed (${response.status}).`));
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
