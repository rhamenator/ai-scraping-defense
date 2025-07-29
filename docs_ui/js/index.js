<script>
document.addEventListener('DOMContentLoaded', () => {

    const archData = {
        'nginx': {
            title: 'NGINX Reverse Proxy',
            description: 'The public-facing entry point. It receives all incoming traffic, serves static assets, and uses Lua scripting to perform initial checks and forward requests to the AI Service for analysis.',
            details: { 'Technology': 'NGINX, Lua', 'Port': '80/443 (Public)', 'Role': 'Gateway & Initial Filtering' }
        },
        'ai-service': {
            title: 'AI Service',
            description: 'The core decision-making engine. It receives requests from NGINX, applies various detection models (AI, behavioral, anomaly), and returns a decision: allow, block, tarpit, or challenge.',
            details: { 'Technology': 'Python (Flask)', 'Role': 'Threat Analysis & Decision Making' }
        },
        'website': {
            title: 'Your Protected Website',
            description: 'This is the actual web application (e.g., WordPress, a custom app) that is being protected. NGINX forwards only legitimate, analyzed traffic to this upstream service.',
            details: { 'Role': 'Upstream Application' }
        },
        'admin-ui': {
            title: 'Admin UI',
            description: 'A web-based dashboard for monitoring the system, viewing logs, managing settings, and analyzing threat data. It provides a human-friendly interface to the system\'s operations.',
            details: { 'Technology': 'Python (Flask), HTML, JS', 'Port': '8081 (Internal)', 'Role': 'Monitoring & Management' }
        },
        'escalation-engine': {
            title: 'Escalation Engine',
            description: 'Handles more complex or suspicious cases flagged by the AI Service. It performs deeper analysis, such as sequence anomaly detection and fingerprinting, to make a final determination.',
            details: { 'Technology': 'Python', 'Role': 'Advanced Threat Analysis' }
        },
        'tarpit-api': {
            title: 'Tarpit API',
            description: 'Generates intentionally slow or confusing responses to trap and waste the resources of malicious bots. This includes large, slow-loading files and labyrinthine APIs.',
            details: { 'Technology': 'Python (Flask)', 'Role': 'Bot Deception & Neutralization' }
        },
        'postgres': {
            title: 'PostgreSQL Database',
            description: 'The primary data store for the system. It holds configuration settings, logs, threat intelligence data, and decisions made by the AI service.',
            details: { 'Technology': 'PostgreSQL', 'Role': 'Persistent Data Storage' }
        },
        'redis': {
            title: 'Redis Cache',
            description: 'An in-memory data store used for high-speed caching of decisions, session data, and rate-limiting counters. This reduces latency and load on the PostgreSQL database.',
            details: { 'Technology': 'Redis', 'Role': 'Caching & Session Management' }
        }
    };

    const defenseLayersData = {
        'ai-detection': {
            title: 'AI & Heuristic Detection',
            content: 'The primary defense layer. The AI Service uses a combination of pre-trained models and heuristic rules to analyze request headers, user agents, and other signatures. It calculates a risk score to determine if a request is from a known bot, a suspicious script, or a legitimate user. This layer is fast and effective against common scraping tools.'
        },
        'behavioral-analysis': {
            title: 'Behavioral Analysis & Honeypots',
            content: 'This layer focuses on how a client interacts with the site over time. It tracks navigation patterns, request frequency, and mouse movements (via front-end scripts). The system also deploys invisible "honeypot" links that are irresistible to bots but invisible to humans. Accessing a honeypot immediately flags the visitor as malicious.'
        },
        'tarpitting': {
            title: 'Tarpitting & Deception',
            content: 'Instead of just blocking a bot, the system can send it to a "tarpit." This involves serving extremely slow, large, or nonsensical data (like generated text or zip bombs) to waste the bot\'s time and resources. This can deter attackers and make scraping your site economically unviable.'
        },
        'rate-limiting': {
            title: 'Adaptive Rate Limiting',
            content: 'The system monitors the request rate from individual IP addresses. Unlike simple rate limiting, it\'s adaptive: it allows short bursts of traffic but will throttle or block clients that maintain an unusually high request rate over time, a common sign of aggressive scraping.'
        },
        'reputation-blocking': {
            title: 'IP Reputation & Blocklists',
            content: 'The system maintains a local blocklist and can integrate with community-driven threat intelligence feeds. IPs with a known history of malicious activity can be blocked preemptively, providing a baseline level of protection against known bad actors.'
        },
        'captcha-challenge': {
            title: 'CAPTCHA Challenges',
            content: 'For requests that are suspicious but not definitively malicious, the system can issue a CAPTCHA challenge. This requires the user to solve a puzzle, proving they are human. The project includes its own internal CAPTCHA service to avoid reliance on third parties.'
        }
    };

    const configData = [
        { key: 'LOG_LEVEL', description: 'Sets the verbosity of application logs (e.g., INFO, DEBUG, WARNING).' },
        { key: 'UPSTREAM_HOST', description: 'The hostname or IP address of the website you want to protect.' },
        { key: 'UPSTREAM_PORT', description: 'The port on which your website is listening.' },
        { key: 'DOMAIN_NAME', description: 'Your public domain name, used for obtaining SSL certificates.' },
        { key: 'CERTBOT_EMAIL', description: 'Email address for Let\'s Encrypt SSL certificate notifications.' },
        { key: 'POSTGRES_USER', description: 'Username for the PostgreSQL database.' },
        { key: 'POSTGRES_PASSWORD', description: 'Password for the PostgreSQL database.' },
        { key: 'REDIS_PASSWORD', description: 'Password for the Redis cache.' },
        { key: 'SECRET_KEY', description: 'A secret key used for signing sessions and tokens.' },
        { key: 'AI_SERVICE_URL', description: 'Internal URL for the AI Service, used by NGINX.' },
        { key: 'TARPIT_URL', description: 'Internal URL for the Tarpit API.' },
        { key: 'ENABLE_HONEYPOT', description: 'Set to "true" to enable the behavioral honeypot feature.' },
        { key: 'RATE_LIMIT_THRESHOLD', description: 'The number of requests per minute before rate limiting kicks in.' },
        { key: 'BLOCK_THRESHOLD', description: 'The AI risk score above which a request is automatically blocked.' },
        { key: 'CHALLENGE_THRESHOLD', description: 'The AI risk score above which a CAPTCHA challenge is issued.' }
    ];

    function renderArchitecture() {
        const container = document.getElementById('arch-diagram');
        container.innerHTML = `
            <div id="arch-nginx" class="arch-card bg-amber-100 text-amber-800 p-4 rounded-lg shadow-md text-center w-48 md:col-start-2">
                <h4 class="font-bold">NGINX Proxy</h4><p class="text-xs">Public Gateway</p>
            </div>
            <div id="arch-ai-service" class="arch-card bg-sky-100 text-sky-800 p-4 rounded-lg shadow-md text-center w-48 md:col-start-1 md:row-start-2">
                <h4 class="font-bold">AI Service</h4><p class="text-xs">Decision Engine</p>
            </div>
            <div id="arch-website" class="arch-card bg-green-100 text-green-800 p-4 rounded-lg shadow-md text-center w-48 md:col-start-3 md:row-start-2">
                <h4 class="font-bold">Your Website</h4><p class="text-xs">Upstream App</p>
            </div>
            <div id="arch-escalation-engine" class="arch-card bg-sky-100 text-sky-800 p-4 rounded-lg shadow-md text-center w-48 md:col-start-1 md:row-start-3">
                <h4 class="font-bold">Escalation Engine</h4><p class="text-xs">Deep Analysis</p>
            </div>
            <div id="arch-tarpit-api" class="arch-card bg-rose-100 text-rose-800 p-4 rounded-lg shadow-md text-center w-48 md:col-start-1 md:row-start-4">
                <h4 class="font-bold">Tarpit API</h4><p class="text-xs">Deception</p>
            </div>
            <div id="arch-admin-ui" class="arch-card bg-slate-100 text-slate-800 p-4 rounded-lg shadow-md text-center w-48 md:col-start-3 md:row-start-3">
                <h4 class="font-bold">Admin UI</h4><p class="text-xs">Monitoring</p>
            </div>
            <div id="arch-postgres" class="arch-card bg-gray-200 text-gray-800 p-4 rounded-lg shadow-md text-center w-48 md:col-start-2 md:row-start-5">
                <h4 class="font-bold">PostgreSQL</h4><p class="text-xs">Data Store</p>
            </div>
            <div id="arch-redis" class="arch-card bg-red-200 text-red-800 p-4 rounded-lg shadow-md text-center w-48 md:col-start-3 md:row-start-5">
                <h4 class="font-bold">Redis</h4><p class="text-xs">Cache</p>
            </div>`;

        Object.keys(archData).forEach(key => {
            const el = document.getElementById(`arch-${key}`);
            if (el) {
                el.addEventListener('click', () => showModal(key));
            }
        });
        
        requestAnimationFrame(drawArchitectureLines);
    }

    function drawArchitectureLines() {
        const canvas = document.getElementById('arch-canvas');
        const container = document.getElementById('arch-diagram-container');
        if (!canvas || !container) return;
        const ctx = canvas.getContext('2d');
        
        canvas.width = container.offsetWidth;
        canvas.height = container.offsetHeight;
        
        const connections = [
            { from: 'nginx', to: 'ai-service', color: '#9CA3AF' },
            { from: 'nginx', to: 'website', color: '#10B981' },
            { from: 'ai-service', to: 'escalation-engine', color: '#9CA3AF' },
            { from: 'ai-service', to: 'tarpit-api', color: '#9CA3AF' },
            { from: 'ai-service', to: 'postgres', color: '#9CA3AF' },
            { from: 'ai-service', to: 'redis', color: '#9CA3AF' },
            { from: 'admin-ui', to: 'postgres', color: '#9CA3AF' },
            { from: 'escalation-engine', to: 'postgres', color: '#9CA3AF' },
        ];

        ctx.lineWidth = 2;
        const containerRect = container.getBoundingClientRect();

        connections.forEach(({ from, to, color }) => {
            const fromEl = document.getElementById(`arch-${from}`);
            const toEl = document.getElementById(`arch-${to}`);
            if (!fromEl || !toEl) return;

            const fromRect = fromEl.getBoundingClientRect();
            const toRect = toEl.getBoundingClientRect();

            const startX = fromRect.left + fromRect.width / 2 - containerRect.left;
            const startY = fromRect.top + fromRect.height / 2 - containerRect.top;
            
            let endX = toRect.left + toRect.width / 2 - containerRect.left;
            let endY = toRect.top + toRect.height / 2 - containerRect.top;

            const dx = endX - startX;
            const dy = endY - startY;
            const angle = Math.atan2(dy, dx);
            
            const padding = 10;
            const halfW = toRect.width / 2 + padding;
            const halfH = toRect.height / 2 + padding;
            
            const cos = Math.cos(angle);
            const sin = Math.sin(angle);

            let intersectX, intersectY;
            if (Math.abs(dx / (toRect.width + padding)) > Math.abs(dy / (toRect.height + padding))) {
                intersectX = endX - (halfW * Math.sign(cos));
                intersectY = endY - (halfW * Math.tan(angle) * Math.sign(cos));
            } else {
                intersectX = endX - (halfH / Math.tan(angle) * Math.sign(sin));
                intersectY = endY - (halfH * Math.sign(sin));
            }
            
            drawArrow(ctx, startX, startY, intersectX, intersectY, color);
        });
    }

    function drawArrow(ctx, fromx, fromy, tox, toy, color) {
        const headlen = 10;
        const dx = tox - fromx;
        const dy = toy - fromy;
        const angle = Math.atan2(dy, dx);

        ctx.strokeStyle = color;
        ctx.fillStyle = color;

        ctx.beginPath();
        ctx.moveTo(fromx, fromy);
        ctx.lineTo(tox, toy);
        ctx.stroke();

        ctx.save();
        ctx.translate(tox, toy);
        ctx.rotate(angle);
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(-headlen, -headlen / 2);
        ctx.lineTo(-headlen, headlen / 2);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    }

    function showModal(key) {
        const data = archData[key];
        document.getElementById('modal-title').textContent = data.title;
        document.getElementById('modal-description').textContent = data.description;
        const detailsContainer = document.getElementById('modal-details');
        detailsContainer.innerHTML = Object.entries(data.details)
            .map(([k, v]) => `<p><strong class="font-semibold text-gray-700">${k}:</strong> ${v}</p>`)
            .join('');
        const modal = document.getElementById('modal');
        modal.classList.remove('hidden');
        setTimeout(() => modal.classList.remove('opacity-0'), 10);
        setTimeout(() => modal.querySelector('.modal-content').classList.remove('scale-95'), 10);
    }

    function hideModal() {
        const modal = document.getElementById('modal');
        modal.classList.add('opacity-0');
        modal.querySelector('.modal-content').classList.add('scale-95');
        setTimeout(() => modal.classList.add('hidden'), 300);
    }

    document.getElementById('modal-close').addEventListener('click', hideModal);
    document.getElementById('modal').addEventListener('click', (e) => {
        if (e.target.id === 'modal') {
            hideModal();
        }
    });

    function renderDefenseLayers() {
        const tabsContainer = document.getElementById('tabs-container');
        const contentContainer = document.getElementById('tab-content-container');
        
        tabsContainer.innerHTML = Object.keys(defenseLayersData).map((key, index) => `
            <button class="tab-btn text-left w-full px-4 py-3 rounded-lg transition-colors ${index === 0 ? 'active' : ''}" data-tab="${key}">
                ${defenseLayersData[key].title}
            </button>
        `).join('');

        function switchTab(key) {
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tab === key);
            });
            contentContainer.innerHTML = `<h3 class="text-2xl font-bold text-gray-800 mb-4">${defenseLayersData[key].title}</h3><p class="text-gray-600 leading-relaxed">${defenseLayersData[key].content}</p>`;
        }

        tabsContainer.addEventListener('click', (e) => {
            if (e.target.matches('.tab-btn')) {
                switchTab(e.target.dataset.tab);
            }
        });
        
        switchTab(Object.keys(defenseLayersData)[0]);
    }

    function renderConfig() {
        const listContainer = document.getElementById('config-list');
        const searchInput = document.getElementById('config-search');
        
        function filterAndRender() {
            const query = searchInput.value.toLowerCase();
            const filteredData = configData.filter(item => item.key.toLowerCase().includes(query) || item.description.toLowerCase().includes(query));
            
            if (filteredData.length === 0) {
                listContainer.innerHTML = `<p class="text-gray-500 text-center">No settings found.</p>`;
                return;
            }

            listContainer.innerHTML = filteredData.map(item => `
                <div class="border-b border-gray-200 pb-3">
                    <p class="font-mono bg-gray-100 text-amber-700 px-2 py-1 rounded-md inline-block mb-1">${item.key}</p>
                    <p class="text-sm text-gray-600">${item.description}</p>
                </div>
            `).join('');
        }

        searchInput.addEventListener('input', filterAndRender);
        filterAndRender();
    }
    
    function initAdminUIMockup() {
        const trafficChartCtx = document.getElementById('trafficChart').getContext('2d');
        const labels = Array.from({ length: 24 }, (_, i) => {
            const d = new Date();
            d.setHours(d.getHours() - (23 - i));
            return d;
        });

        const trafficChart = new Chart(trafficChartCtx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Allowed Requests',
                    data: [],
                    borderColor: 'rgba(22, 163, 74, 0.8)',
                    backgroundColor: 'rgba(22, 163, 74, 0.1)',
                    fill: true,
                    tension: 0.4
                }, {
                    label: 'Blocked Threats',
                    data: [],
                    borderColor: 'rgba(220, 38, 38, 0.8)',
                    backgroundColor: 'rgba(220, 38, 38, 0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'hour',
                            tooltipFormat: 'MMM d, h:mm a',
                            displayFormats: {
                                hour: 'h a'
                            }
                        },
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                if (value >= 1000) {
                                    return (value / 1000) + 'k';
                                }
                                return value;
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    }
                },
                interaction: {
                    mode: 'index',
                    intersect: false
                }
            }
        });

        const eventsLog = document.getElementById('events-log');
        const topThreatsEl = document.getElementById('top-threats');
        const kpiTotal = document.getElementById('kpi-total-requests');
        const kpiBlocked = document.getElementById('kpi-threats-blocked');

        let totalRequests = 85000;
        let threatsBlocked = 4000;
        const threatIPs = {};

        function updateMockup() {
            const allowedData = trafficChart.data.datasets[0].data;
            const blockedData = trafficChart.data.datasets[1].data;

            if(allowedData.length >= 24) {
                const removedAllowed = allowedData.shift();
                const removedBlocked = blockedData.shift();
                trafficChart.data.labels.shift();
                totalRequests -= removedAllowed;
                threatsBlocked -= removedBlocked;
            }
            
            const newAllowed = Math.floor(Math.random() * 1500) + 3000;
            const newBlocked = Math.floor(Math.random() * (newAllowed * 0.1));
            totalRequests += newAllowed;
            threatsBlocked += newBlocked;

            const newLabel = new Date();
            trafficChart.data.labels.push(newLabel);
            allowedData.push(newAllowed);
            blockedData.push(newBlocked);
            trafficChart.update('none');

            kpiTotal.textContent = totalRequests.toLocaleString();
            kpiBlocked.textContent = threatsBlocked.toLocaleString();
            
            const newEventTime = newLabel.toLocaleTimeString();
            const randomIP = `${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}`;
            let newEvent;
            if (Math.random() > 0.1) {
                 newEvent = `<p><span class="text-gray-400">${newEventTime}</span> <span class="text-green-400">[ALLOW]</span> REQ from ${randomIP}</p>`;
            } else {
                threatIPs[randomIP] = (threatIPs[randomIP] || 0) + 1;
                const reasons = ["SQL Injection", "XSS Attempt", "Scraper UA", "High Frequency"];
                const reason = reasons[Math.floor(Math.random() * reasons.length)];
                newEvent = `<p><span class="text-gray-400">${newEventTime}</span> <span class="text-red-400">[BLOCK]</span> REQ from ${randomIP} (${reason})</p>`;
            }
            eventsLog.innerHTML = newEvent + eventsLog.innerHTML;
            if (eventsLog.children.length > 50) {
                eventsLog.removeChild(eventsLog.lastChild);
            }

            const sortedThreats = Object.entries(threatIPs).sort((a, b) => b[1] - a[1]).slice(0, 5);
            topThreatsEl.innerHTML = sortedThreats.map(([ip, count]) => `
                <div class="flex justify-between items-center bg-slate-50 p-2 rounded-md">
                    <p class="font-mono text-sm text-gray-700">${ip}</p>
                    <span class="text-sm font-bold text-red-600 bg-red-100 px-2 py-1 rounded-full">${count.toLocaleString()}</span>
                </div>
            `).join('');
        }
        
        for(let i=0; i < 24; i++) {
             const newAllowed = Math.floor(Math.random() * 1500) + 3000;
             const newBlocked = Math.floor(Math.random() * (newAllowed * 0.1));
             trafficChart.data.datasets[0].data.push(newAllowed);
             trafficChart.data.datasets[1].data.push(newBlocked);
             totalRequests += newAllowed;
             threatsBlocked += newBlocked;
        }
        trafficChart.update();
        kpiTotal.textContent = totalRequests.toLocaleString();
        kpiBlocked.textContent = threatsBlocked.toLocaleString();

        setInterval(updateMockup, 3000);
    }

    const navLinks = document.querySelectorAll('.nav-link');
    const sections = document.querySelectorAll('section');

    window.addEventListener('scroll', () => {
        let current = '';
        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            if (pageYOffset >= sectionTop - 60) {
                current = section.getAttribute('id');
            }
        });

        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === `#${current}`) {
                link.classList.add('active');
            }
        });
    });
    
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            requestAnimationFrame(drawArchitectureLines);
        }, 100);
    });
    
    document.querySelectorAll('.copy-btn').forEach(button => {
        button.addEventListener('click', () => {
            const code = button.previousElementSibling.querySelector('code').innerText;
            const textarea = document.createElement('textarea');
            textarea.value = code;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            button.innerText = 'Copied!';
            setTimeout(() => {
                button.innerText = 'Copy';
            }, 2000);
        });
    });

    renderArchitecture();
    renderDefenseLayers();
    renderConfig();
    initAdminUIMockup();
});
</script>
