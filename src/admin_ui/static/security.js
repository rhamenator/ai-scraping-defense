// Security page: TOTP QR enrollment, Passkey enrollment, backup codes, and password change.
const csrfToken = () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
};
const errorBox = document.getElementById('security-error');
const statusBox = document.getElementById('security-status');
const codesSection = document.getElementById('new-codes');
const codesList = document.getElementById('new-codes-list');
const backupSummary = document.getElementById('sec-backup');

function showError(message) {
    errorBox.textContent = message || '';
    errorBox.hidden = !message;
    if (message && statusBox) statusBox.hidden = true;
}

function showStatus(message) {
    if (!statusBox) return;
    statusBox.textContent = message || '';
    statusBox.hidden = !message;
    if (message) errorBox.hidden = true;
}

function confirmAction(title, message) {
    const dialog = document.getElementById('confirm-dialog');
    if (typeof dialog.showModal !== 'function') {
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

function hideCodes() {
    codesList.textContent = '';
    codesSection.hidden = true;
}

function resolveEndpoint(path) {
    switch (path) {
        case '/mfa/backup-codes': return '/mfa/backup-codes';
        case '/mfa/totp/setup': return '/mfa/totp/setup';
        case '/mfa/totp/verify': return '/mfa/totp/verify';
        case '/webauthn/register/begin': return '/webauthn/register/begin';
        case '/webauthn/register/complete': return '/webauthn/register/complete';
        case '/account/password': return '/account/password';
        default: throw new Error('Unsupported endpoint.');
    }
}

async function post(path, body) {
    const endpoint = resolveEndpoint(path);
    const headers = { 'X-CSRF-Token': csrfToken() };
    const init = {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers,
    };
    if (body !== undefined) {
        headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
    }
    const response = await fetch(endpoint, init);
    let payload = {};
    try { payload = await response.json(); } catch (_e) { /* non-JSON error body */ }
    if (!response.ok) {
        throw new Error(payload.detail || payload.error || `Request failed (${response.status}).`);
    }
    return payload;
}

function renderQrMatrixSvg(matrix) {
    const svgNs = 'http:' + '//www.w3.org/2000/svg';
    const size = matrix.length;
    const svg = document.createElementNS(svgNs, 'svg');
    svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
    svg.setAttribute('width', '180');
    svg.setAttribute('height', '180');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Authenticator QR code');
    svg.style.background = '#ffffff';
    svg.style.padding = '8px';
    svg.style.borderRadius = '12px';
    svg.style.border = '1px solid rgba(29,34,24,0.14)';

    matrix.forEach((row, r) => {
        row.forEach((dark, c) => {
            if (!dark) return;
            const rect = document.createElementNS(svgNs, 'rect');
            rect.setAttribute('x', String(c));
            rect.setAttribute('y', String(r));
            rect.setAttribute('width', '1');
            rect.setAttribute('height', '1');
            rect.setAttribute('fill', '#1d2218');
            svg.appendChild(rect);
        });
    });
    return svg;
}

function b64UrlToBytes(b64url) {
    const pad = '='.repeat((4 - (b64url.length % 4)) % 4);
    const base64 = (b64url + pad).replace(/-/g, '+').replace(/_/g, '/');
    const raw = window.atob(base64);
    return Uint8Array.from(raw, ch => ch.charCodeAt(0));
}

function bytesToB64Url(buffer) {
    const bytes = new Uint8Array(buffer);
    let bin = '';
    bytes.forEach(b => { bin += String.fromCharCode(b); });
    return window.btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

const setupTotpBtn = document.getElementById('setup-totp');
if (setupTotpBtn) {
    setupTotpBtn.addEventListener('click', async () => {
        showError('');
        try {
            const data = await post('/mfa/totp/setup');
            const host = document.getElementById('totp-qr-host');
            while (host.firstChild) host.removeChild(host.firstChild);
            if (Array.isArray(data.qr_matrix)) host.appendChild(renderQrMatrixSvg(data.qr_matrix));
            document.getElementById('totp-secret-text').textContent = data.secret || '';
            document.getElementById('totp-enroll-box').hidden = false;
        } catch (err) {
            showError(err.message);
        }
    });
}

const totpVerifyForm = document.getElementById('totp-verify-form');
if (totpVerifyForm) {
    totpVerifyForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        showError('');
        const code = document.getElementById('totp-verify-code').value.trim();
        try {
            await post('/mfa/totp/verify', { code });
            document.getElementById('sec-totp').textContent = 'Set up for this deployment';
            document.getElementById('totp-enroll-box').hidden = true;
            totpVerifyForm.reset();
            showStatus('Authenticator app enrolled.');
        } catch (err) {
            showError(err.message);
        }
    });
}

const enrollPasskeyBtn = document.getElementById('enroll-passkey');
if (enrollPasskeyBtn) {
    enrollPasskeyBtn.addEventListener('click', async () => {
        showError('');
        if (!window.PublicKeyCredential || !navigator.credentials) {
            showError('Passkeys require a WebAuthn-capable browser over HTTPS or localhost.');
            return;
        }
        try {
            const opts = await post('/webauthn/register/begin');
            opts.challenge = b64UrlToBytes(opts.challenge);
            opts.user.id = b64UrlToBytes(opts.user.id);
            if (Array.isArray(opts.excludeCredentials)) {
                opts.excludeCredentials = opts.excludeCredentials.map(c => ({ ...c, id: b64UrlToBytes(c.id) }));
            }
            const cred = await navigator.credentials.create({ publicKey: opts });
            if (!cred) throw new Error('Passkey creation was cancelled.');
            const payload = {
                credential: {
                    id: cred.id,
                    rawId: bytesToB64Url(cred.rawId),
                    type: cred.type,
                    response: {
                        attestationObject: bytesToB64Url(cred.response.attestationObject),
                        clientDataJSON: bytesToB64Url(cred.response.clientDataJSON),
                    },
                },
            };
            await post('/webauthn/register/complete', payload);
            document.getElementById('sec-passkey').textContent = 'Enrolled';
            showStatus('Passkey enrolled.');
        } catch (err) {
            showError(err.message);
        }
    });
}

const changePwForm = document.getElementById('change-password-form');
if (changePwForm) {
    changePwForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        showError('');
        const current_password = document.getElementById('current-password').value;
        const new_password = document.getElementById('new-password').value;
        const confirm_password = document.getElementById('confirm-password').value;
        try {
            await post('/account/password', { current_password, new_password, confirm_password });
            changePwForm.reset();
            showStatus('Password updated.');
        } catch (err) {
            showError(err.message);
        }
    });
}

document.getElementById('regenerate-codes').addEventListener('click', async () => {
    showError('');
    const proceed = await confirmAction(
        'Regenerate backup codes?',
        'Every existing backup code stops working immediately. The new codes are shown once.');
    if (!proceed) return;
    try {
        const payload = await post('/mfa/backup-codes');
        const codes = payload.backup_codes || [];
        codesList.textContent = codes.join('\n');
        codesSection.hidden = false;
        backupSummary.textContent = `${codes.length} of ${codes.length} remaining (just generated)`;
    } catch (err) {
        showError(err.message);
    }
});

document.getElementById('dismiss-codes').addEventListener('click', hideCodes);
window.addEventListener('pagehide', hideCodes);
