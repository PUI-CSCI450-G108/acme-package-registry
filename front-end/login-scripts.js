async function handleLogin(event) {
    event.preventDefault();

    const apiUrlInput = document.getElementById('api-url-input');
    const usernameInput = document.getElementById('username-input');
    const passwordInput = document.getElementById('password-input');
    const errorDiv = document.getElementById('login-error');

    // Clear any previous errors before attempting login.
    errorDiv.style.display = 'none';
    errorDiv.textContent = '';

    const apiUrl = apiUrlInput.value.trim().replace(/\/$/, '');
    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();

    if (!apiUrl || !username || !password) {
        errorDiv.textContent = 'Please provide API URL, username, and password.';
        errorDiv.style.display = 'block';
        return;
    }

    try {
        // Persist API URL and username for reuse across pages.
        localStorage.setItem('apiBaseUrl', apiUrl);
        localStorage.setItem('username', username);

        const response = await fetch(`${apiUrl}/authenticate`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user: { name: username },
                secret: { password }
            })
        });

        const responseText = await response.text();
        if (!response.ok) {
            let errorMessage = `Login failed with status ${response.status}`;
            try {
                const errorData = JSON.parse(responseText);
                errorMessage = errorData.error || errorMessage;
            } catch {
                errorMessage = responseText || errorMessage;
            }
            throw new Error(errorMessage);
        }

        // Normalize the token whether the backend wraps it in JSON or returns raw text.
        let tokenText = responseText;
        try {
            const parsed = JSON.parse(responseText);
            if (typeof parsed === 'string') {
                tokenText = parsed;
            } else if (parsed && typeof parsed.token === 'string') {
                tokenText = parsed.token;
            }
        } catch {
            // Fallback to raw text response when not valid JSON.
        }

        tokenText = tokenText.trim();
        if (tokenText.startsWith('"') && tokenText.endsWith('"')) {
            tokenText = tokenText.slice(1, -1);
        }

        if (!tokenText) {
            throw new Error('Authentication token missing from response.');
        }

        localStorage.setItem('authToken', tokenText);

        // Redirect to main application after successful authentication.
        window.location.href = 'index.html';
    } catch (error) {
        console.error('Login failed:', error);
        errorDiv.textContent = error.message || 'Unable to login.';
        errorDiv.style.display = 'block';
    }
}

// Prefill saved values and focus username for quick login.
document.addEventListener('DOMContentLoaded', function() {
    const savedUrl = localStorage.getItem('apiBaseUrl');
    if (savedUrl) {
        document.getElementById('api-url-input').value = savedUrl;
    }

    const savedUsername = localStorage.getItem('username');
    if (savedUsername) {
        document.getElementById('username-input').value = savedUsername;
    }

    const input = document.getElementById('username-input');
    input.focus();
});
