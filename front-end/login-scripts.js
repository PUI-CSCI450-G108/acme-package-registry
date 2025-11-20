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

        // Lambda returns the token as a plain string (e.g., "bearer <jwt>").
        const tokenText = responseText.trim();
        localStorage.setItem('authToken', tokenText);

        // Persist admin flag when present in the token payload so UI controls can be
        // adjusted without additional API calls.
        const payload = decodeTokenPayload(tokenText);
        if (payload && typeof payload.is_admin !== 'undefined') {
            localStorage.setItem('isAdmin', payload.is_admin ? 'true' : 'false');
        } else {
            localStorage.removeItem('isAdmin');
        }

        // Redirect to main application after successful authentication.
        window.location.href = 'index.html';
    } catch (error) {
        console.error('Login failed:', error);
        errorDiv.textContent = error.message || 'Unable to login.';
        errorDiv.style.display = 'block';
    }
}

function decodeTokenPayload(tokenText) {
    try {
        const normalized = tokenText.toLowerCase().startsWith('bearer ')
            ? tokenText.slice(7)
            : tokenText;
        const payloadSegment = normalized.split('.')[1];
        if (!payloadSegment) {
            return null;
        }
        const decoded = atob(payloadSegment.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - payloadSegment.length % 4) % 4));
        return JSON.parse(decoded);
    } catch (error) {
        console.warn('Unable to decode token payload for admin detection', error);
        return null;
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
