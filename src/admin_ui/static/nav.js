(function () {
    const signOutBtn = document.getElementById('sign-out');
    if (!signOutBtn) {
        return;
    }
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
    signOutBtn.addEventListener('click', async () => {
        signOutBtn.disabled = true;
        try {
            const headers = csrfToken ? { 'X-CSRF-Token': csrfToken } : {};
            const response = await fetch('/logout', {
                method: 'POST',
                headers,
                credentials: 'same-origin',
            });
            if (response.ok) {
                window.location.reload();
                return;
            }
        } catch (_err) {
            // Fall through to re-enable
        }
        signOutBtn.disabled = false;
    });
})();
