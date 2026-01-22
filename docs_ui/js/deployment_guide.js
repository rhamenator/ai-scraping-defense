    <script>
        const delay = (ms, callback) => {
            const start = performance.now();
            const tick = (now) => {
                if (now - start >= ms) {
                    callback();
                    return;
                }
                requestAnimationFrame(tick);
            };
            requestAnimationFrame(tick);
        };

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
                delay(2000, () => {
                    button.innerText = 'Copy';
                });
            });
        });
    </script>
