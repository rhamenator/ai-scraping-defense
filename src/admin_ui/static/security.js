// Security page: regenerate backup codes (shown once) and sign out (#1952).
const csrfToken = () => {
    // The CSRF cookie is HttpOnly, so the server also renders the token into the page.
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
};
const errorBox = document.getElementById('security-error');
const codesSection = document.getElementById('new-codes');
const codesList = document.getElementById('new-codes-list');
const backupSummary = document.getElementById('sec-backup');

function showError(message) {
    errorBox.textContent = message || '';
    errorBox.hidden = !message;
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
    // Remove the codes from the page as soon as the admin says they are saved, or when leaving it.
    codesList.textContent = '';
    codesSection.hidden = true;
}

async function post(path) {
    const response = await fetch(path, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'X-CSRF-Token': csrfToken() }
    });
    let payload = {};
    try { payload = await response.json(); } catch (e) { /* non-JSON error body */ }
    if (!response.ok) {
        throw new Error(payload.detail || payload.error || `Request failed (${response.status}).`);
    }
    return payload;
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

document.getElementById('sign-out').addEventListener('click', async () => {
    showError('');
    try {
        await post('/logout');
        window.location.assign('/');
    } catch (err) {
        showError(err.message);
    }
});
