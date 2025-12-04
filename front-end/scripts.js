// Global state
let currentPage = 0;
let currentSearchQuery = null;
const ITEMS_PER_PAGE = 12;

// ============================================
// Security Utilities
// ============================================

function isValidUrl(url) {
    if (!url || url === '#') return true;

    try {
        const parsed = new URL(url);
        // Only allow http and https protocols
        return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch (e) {
        return false;
    }
}

function sanitizeUrl(url) {
    if (!url || url === '#') return '#';

    if (isValidUrl(url)) {
        return url;
    }

    // If invalid, return a safe placeholder
    return '#';
}

function decodeJwtPayload(tokenText) {
    if (!tokenText) return null;

    const normalized = tokenText.trim().toLowerCase().startsWith('bearer ')
        ? tokenText.trim().slice(7)
        : tokenText.trim();

    const parts = normalized.split('.');
    if (parts.length < 2) return null;

    try {
        const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
        const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
        const json = atob(padded);
        return JSON.parse(json);
    } catch (error) {
        console.error('Failed to decode token payload', error);
        return null;
    }
}

function getCurrentUserPermissions() {
    const payload = decodeJwtPayload(getAuthToken());
    return {
        is_admin: Boolean(payload?.is_admin),
        can_upload: Boolean(payload?.can_upload),
        can_search: Boolean(payload?.can_search),
        can_download: Boolean(payload?.can_download)
    };
}

function isCurrentUserAdmin() {
    return getCurrentUserPermissions().is_admin;
}

// ============================================
// Configuration Management
// ============================================

function getApiBaseUrl() {
    return localStorage.getItem('apiBaseUrl') || '';
}

function getAuthToken() {
    return localStorage.getItem('authToken') || '';
}

function getHeaders() {
    const headers = {
        'Content-Type': 'application/json'
    };
    const token = getAuthToken();
    if (token) {
        headers['X-Authorization'] = token;

        headers['Authorization'] = token;
    }
    return headers;
}

// Navigate to health dashboard
function goToHealthDashboard() {
    // Navigate to health-dashboard/index.html
    window.location.href = 'health-dashboard/index.html';
}

// Log out by revoking the token on the API and clearing local storage.
async function logout() {
    const baseUrl = getApiBaseUrl();
    const token = getAuthToken();

    // If we have no token saved, just redirect to the login page.
    if (!token) {
        localStorage.removeItem('authToken');
        window.location.href = 'login.html';
        return;
    }

    try {
        if (baseUrl) {
            await fetch(`${baseUrl}/auth/logout`, {
                method: 'POST',
                headers: getHeaders()
            });
        }
    } catch (error) {
        console.error('Logout request failed:', error);
    } finally {
        localStorage.removeItem('authToken');
        window.location.href = 'login.html';
    }
}

function saveConfiguration() {
    const apiUrl = document.getElementById('config-api-url').value.trim();
    const authToken = document.getElementById('config-auth-token').value.trim();

    if (!apiUrl) {
        alert('Please enter an API Base URL');
        return;
    }

    localStorage.setItem('apiBaseUrl', apiUrl.endsWith('/') ? apiUrl.slice(0, -1) : apiUrl);
    localStorage.setItem('authToken', authToken);

    document.getElementById('config-modal').style.display = 'none';
    loadArtifacts();
}

function checkConfiguration() {
    if (!getApiBaseUrl()) {
        document.getElementById('config-modal').style.display = 'flex';
        return false;
    }
    return true;
}

// ============================================
// UI State Management
// ============================================

function showLoading() {
    document.getElementById('loading').style.display = 'block';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('artifacts-grid').innerHTML = '';
    document.getElementById('pagination').style.display = 'none';
}

function showError(message) {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('error-state').style.display = 'block';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('error-message').textContent = message;
    document.getElementById('artifacts-grid').innerHTML = '';
    document.getElementById('pagination').style.display = 'none';
}

function showEmpty() {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'block';
    document.getElementById('artifacts-grid').innerHTML = '';
    document.getElementById('pagination').style.display = 'none';
}

function showArtifacts() {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
}

// ============================================
// Artifact Loading and Display
// ============================================

async function loadArtifacts() {
    if (!checkConfiguration()) return;

    showLoading();

    try {
        const baseUrl = getApiBaseUrl();
        const offset = currentPage * ITEMS_PER_PAGE;

        const response = await fetch(`${baseUrl}/artifacts/detailed?offset=${offset}`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify([{ name: '*' }])
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const artifacts = await response.json();

        if (!artifacts || artifacts.length === 0) {
            if (currentPage === 0) {
                showEmpty();
            } else {
                // No more pages, go back to previous page
                currentPage = Math.max(0, currentPage - 1);
                updatePaginationButtons();
            }
            return;
        }

        displayArtifacts(artifacts);
        updatePaginationButtons();
    } catch (error) {
        console.error('Error loading artifacts:', error);
        showError(`Failed to load artifacts: ${error.message}`);
    }
}

function displayArtifacts(artifacts) {
    showArtifacts();

    const grid = document.getElementById('artifacts-grid');
    grid.innerHTML = '';

    artifacts.forEach(artifact => {
        const card = createArtifactCard(artifact);
        grid.appendChild(card);
    });

    document.getElementById('pagination').style.display = 'flex';
}

function createArtifactCard(artifact) {
    const card = document.createElement('div');
    card.className = 'artifact-card';
    card.onclick = () => showArtifactDetail(artifact);

    const metadata = artifact.metadata || {};
    const data = artifact.data || {};
    const name = metadata.name || 'Unknown';
    const type = metadata.type || 'model';
    const id = metadata.id || 'N/A';
    const netScore = data.net_score !== undefined ? data.net_score : null;

    card.innerHTML = `
        <div class="artifact-card-header">
            <div class="artifact-name">${escapeHtml(name)}</div>
            <span class="badge ${type}">${type}</span>
        </div>
        <div class="artifact-info">ID: ${escapeHtml(String(id))}</div>
        ${netScore !== null ? `
            <div class="score-container">
                <div class="score-bar">
                    <div class="score-fill" style="width: ${netScore * 100}%"></div>
                </div>
                <span class="score-text">${(netScore * 100).toFixed(0)}%</span>
            </div>
        ` : '<div class="artifact-info">No score available</div>'}
    `;

    return card;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// Pagination
// ============================================

function updatePaginationButtons(totalArtifacts) {
    document.getElementById('prev-btn').disabled = currentPage === 0;
    // Disable next button if on last page
    const isLastPage = ((currentPage + 1) * ITEMS_PER_PAGE) >= totalArtifacts;
    document.getElementById('next-btn').disabled = isLastPage;
    document.getElementById('page-info').textContent = `Page ${currentPage + 1}`;
}

function loadPage(direction) {
    if (direction === 'prev' && currentPage > 0) {
        currentPage--;
    } else if (direction === 'next') {
        currentPage++;
    }

    if (currentSearchQuery) {
        searchArtifacts();
    } else {
        loadArtifacts();
    }
}

// ============================================
// Search Functionality
// ============================================

async function searchArtifacts() {
    if (!checkConfiguration()) return;

    const searchInput = document.getElementById('search-input').value.trim();

    // If search is empty, just load all artifacts
    if (!searchInput) {
        currentSearchQuery = null;
        currentPage = 0;
        loadArtifacts();
        return;
    }

    showLoading();

    try {
        const baseUrl = getApiBaseUrl();

        // Build search query - search by name or ID
        const searchBody = {
            name: searchInput
        };

        currentSearchQuery = searchBody;

        const response = await fetch(`${baseUrl}/artifact/search`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify(searchBody)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const artifacts = await response.json();

        if (!artifacts || artifacts.length === 0) {
            showEmpty();
            return;
        }

        // Handle pagination for search results
        const startIdx = currentPage * ITEMS_PER_PAGE;
        const endIdx = startIdx + ITEMS_PER_PAGE;
        const paginatedArtifacts = artifacts.slice(startIdx, endIdx);

        if (paginatedArtifacts.length === 0 && currentPage > 0) {
            currentPage = Math.max(0, currentPage - 1);
            searchArtifacts();
            return;
        }

        displayArtifacts(paginatedArtifacts);

        // Update next button based on whether there are more results
        document.getElementById('next-btn').disabled = endIdx >= artifacts.length;
    } catch (error) {
        console.error('Error searching artifacts:', error);
        showError(`Failed to search artifacts: ${error.message}`);
    }
}


// ============================================
// Add Artifact Modal
// ============================================

function showAddArtifactModal() {
    if (!checkConfiguration()) return;

    document.getElementById('add-modal').style.display = 'flex';
    document.getElementById('artifact-url').value = '';
    document.getElementById('artifact-type').value = 'model';
    document.getElementById('add-error').style.display = 'none';
    document.getElementById('add-success').style.display = 'none';
}

function closeAddModal() {
    document.getElementById('add-modal').style.display = 'none';
}

async function createArtifact() {
    const type = document.getElementById('artifact-type').value;
    const url = document.getElementById('artifact-url').value.trim();

    if (!url) {
        showModalError('Please enter a URL');
        return;
    }

    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Adding...';
    document.getElementById('add-error').style.display = 'none';
    document.getElementById('add-success').style.display = 'none';

    try {
        const baseUrl = getApiBaseUrl();
        const response = await fetch(`${baseUrl}/artifact/${type}`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ url: url })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}: ${response.statusText}`);
        }

        showModalSuccess('Artifact added successfully!');

        // Refresh the artifacts list after a short delay
        setTimeout(() => {
            closeAddModal();
            currentPage = 0;
            currentSearchQuery = null;
            loadArtifacts();
        }, 1500);
    } catch (error) {
        console.error('Error creating artifact:', error);
        showModalError(`Failed to add artifact: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Add Artifact';
    }
}

function showModalError(message) {
    const errorDiv = document.getElementById('add-error');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    document.getElementById('add-success').style.display = 'none';
}

function showModalSuccess(message) {
    const successDiv = document.getElementById('add-success');
    successDiv.textContent = message;
    successDiv.style.display = 'block';
    document.getElementById('add-error').style.display = 'none';
}

// ============================================
// Register User Modal
// ============================================

function toggleAdminFeatures() {
    const registerBtn = document.getElementById('register-user-btn');
    if (!registerBtn) return;

    if (isCurrentUserAdmin()) {
        registerBtn.style.display = 'inline-flex';
    } else {
        registerBtn.style.display = 'none';
        closeRegisterModal();
    }
}

function resetRegisterForm() {
    document.getElementById('register-username').value = '';
    document.getElementById('register-password').value = '';
    document.getElementById('register-confirm-password').value = '';
    document.getElementById('register-can-upload').checked = false;
    document.getElementById('register-can-search').checked = false;
    document.getElementById('register-can-download').checked = false;
    document.getElementById('register-is-admin').checked = false;
    document.getElementById('register-error').style.display = 'none';
    document.getElementById('register-success').style.display = 'none';
}

function showRegisterModal() {
    if (!checkConfiguration()) return;
    if (!isCurrentUserAdmin()) {
        alert('Admin privileges are required to register users.');
        return;
    }

    resetRegisterForm();
    document.getElementById('register-modal').style.display = 'flex';
}

function closeRegisterModal() {
    const modal = document.getElementById('register-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function submitUserRegistration() {
    const errorDiv = document.getElementById('register-error');
    const successDiv = document.getElementById('register-success');
    const submitBtn = document.getElementById('register-submit-btn');

    errorDiv.style.display = 'none';
    successDiv.style.display = 'none';

    if (!isCurrentUserAdmin()) {
        errorDiv.textContent = 'Only admins can register new users.';
        errorDiv.style.display = 'block';
        return;
    }

    const username = document.getElementById('register-username').value.trim();
    const password = document.getElementById('register-password').value;
    const confirmPassword = document.getElementById('register-confirm-password').value;
    const isAdmin = document.getElementById('register-is-admin').checked;
    const canUpload = isAdmin || document.getElementById('register-can-upload').checked;
    const canSearch = isAdmin || document.getElementById('register-can-search').checked;
    const canDownload = isAdmin || document.getElementById('register-can-download').checked;

    if (!username) {
        errorDiv.textContent = 'Please enter a username.';
        errorDiv.style.display = 'block';
        return;
    }

    if (!password || password.length < 8) {
        errorDiv.textContent = 'Password must be at least 8 characters long.';
        errorDiv.style.display = 'block';
        return;
    }

    if (password !== confirmPassword) {
        errorDiv.textContent = 'Passwords do not match.';
        errorDiv.style.display = 'block';
        return;
    }

    const baseUrl = getApiBaseUrl();
    if (!baseUrl) {
        errorDiv.textContent = 'API base URL is missing. Please configure it first.';
        errorDiv.style.display = 'block';
        return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Registering...';

    try {
        const response = await fetch(`${baseUrl}/auth/register`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({
                user: { name: username, is_admin: isAdmin },
                permissions: {
                    can_upload: canUpload,
                    can_search: canSearch,
                    can_download: canDownload
                },
                secret: { password }
            })
        });

        let data = null;
        if (response.ok) {
            data = await response.json();
        } else {
            // Try to parse error message as JSON, but fall back to status if not JSON
            try {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            } catch (e) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
        }
        document.getElementById('register-username').value = '';
        document.getElementById('register-password').value = '';
        document.getElementById('register-confirm-password').value = '';
        document.getElementById('register-can-upload').checked = false;
        document.getElementById('register-can-search').checked = false;
        document.getElementById('register-can-download').checked = false;
        document.getElementById('register-is-admin').checked = false;

        successDiv.textContent = `User ${escapeHtml(data.username)} registered successfully.`;
        successDiv.style.display = 'block';
        errorDiv.style.display = 'none';
    } catch (error) {
        console.error('Error registering user:', error);
        errorDiv.textContent = error.message || 'Failed to register user.';
        errorDiv.style.display = 'block';
        successDiv.style.display = 'none';
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Register User';
    }
}

// ============================================
// Artifact Detail Modal
// ============================================

function showArtifactDetail(artifact) {
    const metadata = artifact.metadata || {};
    const data = artifact.data || {};

    document.getElementById('detail-name').textContent = metadata.name || 'Unknown';
    document.getElementById('detail-type').textContent = metadata.type || 'model';
    document.getElementById('detail-type').className = `badge ${metadata.type || 'model'}`;
    document.getElementById('detail-id').textContent = metadata.id || 'N/A';

    const url = data.url || '#';
    const urlElement = document.getElementById('detail-url');
    urlElement.textContent = url;
    urlElement.href = sanitizeUrl(url);

    const netScore = data.net_score !== undefined ? data.net_score : 0;
    document.getElementById('detail-score-fill').style.width = `${netScore * 100}%`;
    document.getElementById('detail-score-text').textContent = `${(netScore * 100).toFixed(1)}%`;

    document.getElementById('detail-modal').style.display = 'flex';
}

function closeDetailModal() {
    document.getElementById('detail-modal').style.display = 'none';
}

// ============================================
// Initialization
// ============================================

window.addEventListener('DOMContentLoaded', function() {
    // Load saved configuration
    const savedUrl = getApiBaseUrl();
    const savedToken = getAuthToken();

    if (savedUrl) {
        document.getElementById('config-api-url').value = savedUrl;
    }
    if (savedToken) {
        document.getElementById('config-auth-token').value = savedToken;
    }

    toggleAdminFeatures();

    // Handle Enter key in search input
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                currentPage = 0;
                searchArtifacts();
            }
        });
    }

    // Load artifacts on page load
    if (checkConfiguration()) {
        loadArtifacts();
    }

    // Close modals when clicking outside
    window.onclick = function(event) {
        const addModal = document.getElementById('add-modal');
        const detailModal = document.getElementById('detail-modal');
        const configModal = document.getElementById('config-modal');
        const registerModal = document.getElementById('register-modal');

        if (event.target === addModal) {
            closeAddModal();
        } else if (event.target === detailModal) {
            closeDetailModal();
        } else if (event.target === registerModal) {
            closeRegisterModal();
        } else if (event.target === configModal && getApiBaseUrl()) {
            // Only allow closing config modal if API URL is set
            configModal.style.display = 'none';
        }
    };
});
