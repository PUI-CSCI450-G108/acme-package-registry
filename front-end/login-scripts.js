function handleLogin(event) {
    event.preventDefault();

    const username = document.getElementById('username-input').value.trim();

    // Store username in localStorage if provided (for future use)
    if (username) {
        localStorage.setItem('username', username);
    }

    // Redirect to main application
    window.location.href = 'index.html';
}

// Add keyboard shortcut for Enter key
document.addEventListener('DOMContentLoaded', function() {
    const input = document.getElementById('username-input');
    input.focus();
});
