// Helper function to get API base URL
function getApiBaseUrl() {
    const url = document.getElementById('apiBaseUrl').value.trim();
    if (!url) {
        alert('Please enter an API Base URL in the configuration section');
        return null;
    }
    return url.endsWith('/') ? url.slice(0, -1) : url;
}

// Helper function to get auth token
function getAuthToken() {
    return document.getElementById('authToken').value.trim();
}

// Helper function to get headers
function getHeaders() {
    const headers = {
        'Content-Type': 'application/json'
    };
    const token = getAuthToken();
    if (token) {
        headers['X-Authorization'] = token;
    }
    return headers;
}

// Helper function to display response
function displayResponse(elementId, data, isError = false) {
    const element = document.getElementById(elementId);
    element.className = 'response ' + (isError ? 'error' : 'success');
    element.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
}

// Helper function to display loading
function displayLoading(elementId) {
    const element = document.getElementById(elementId);
    element.className = 'response loading';
    element.innerHTML = '<p>Loading...</p>';
}

// 1. Health Check
async function healthCheck() {
    const baseUrl = getApiBaseUrl();
    if (!baseUrl) return;

    displayLoading('health-response');
    try {
        const response = await fetch(`${baseUrl}/health`);
        const data = await response.text();
        displayResponse('health-response', {
            status: response.status,
            statusText: response.statusText,
            body: data
        }, !response.ok);
    } catch (error) {
        displayResponse('health-response', { error: error.message }, true);
    }
}

// 2. Create Artifact
async function createArtifact() {
    const baseUrl = getApiBaseUrl();
    if (!baseUrl) return;

    const artifactType = document.getElementById('create-type').value;
    const url = document.getElementById('create-url').value.trim();

    if (!url) {
        alert('Please enter a URL');
        return;
    }

    displayLoading('create-response');
    try {
        const response = await fetch(`${baseUrl}/artifact/${artifactType}`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ url: url })
        });
        const data = await response.json();
        displayResponse('create-response', {
            status: response.status,
            statusText: response.statusText,
            body: data
        }, !response.ok);
    } catch (error) {
        displayResponse('create-response', { error: error.message }, true);
    }
}

// 3. List Artifacts
async function listArtifacts() {
    const baseUrl = getApiBaseUrl();
    if (!baseUrl) return;

    const queryText = document.getElementById('list-query').value.trim();
    const offset = document.getElementById('list-offset').value.trim();

    let query;
    try {
        query = JSON.parse(queryText);
    } catch (e) {
        alert('Invalid JSON in query field');
        return;
    }

    displayLoading('list-response');
    try {
        let url = `${baseUrl}/artifacts`;
        if (offset) {
            url += `?offset=${encodeURIComponent(offset)}`;
        }

        const response = await fetch(url, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify(query)
        });
        const data = await response.json();
        displayResponse('list-response', {
            status: response.status,
            statusText: response.statusText,
            body: data
        }, !response.ok);
    } catch (error) {
        displayResponse('list-response', { error: error.message }, true);
    }
}

// 4. Get Artifact by Name
async function getArtifactByName() {
    const baseUrl = getApiBaseUrl();
    if (!baseUrl) return;

    const name = document.getElementById('byname-name').value.trim();
    if (!name) {
        alert('Please enter an artifact name');
        return;
    }

    displayLoading('byname-response');
    try {
        const response = await fetch(`${baseUrl}/artifact/byName/${encodeURIComponent(name)}`, {
            headers: getHeaders()
        });
        const data = await response.json();
        displayResponse('byname-response', {
            status: response.status,
            statusText: response.statusText,
            body: data
        }, !response.ok);
    } catch (error) {
        displayResponse('byname-response', { error: error.message }, true);
    }
}

// 5. Get Artifact by ID
async function getArtifactById() {
    const baseUrl = getApiBaseUrl();
    if (!baseUrl) return;

    const artifactType = document.getElementById('byid-type').value;
    const id = document.getElementById('byid-id').value.trim();

    if (!id) {
        alert('Please enter an artifact ID');
        return;
    }

    displayLoading('byid-response');
    try {
        const response = await fetch(`${baseUrl}/artifacts/${artifactType}/${encodeURIComponent(id)}`, {
            headers: getHeaders()
        });
        const data = await response.json();
        displayResponse('byid-response', {
            status: response.status,
            statusText: response.statusText,
            body: data
        }, !response.ok);
    } catch (error) {
        displayResponse('byid-response', { error: error.message }, true);
    }
}

// 6. Rate Artifact
async function rateArtifact() {
    const baseUrl = getApiBaseUrl();
    if (!baseUrl) return;

    const id = document.getElementById('rate-id').value.trim();
    if (!id) {
        alert('Please enter a model ID');
        return;
    }

    displayLoading('rate-response');
    try {
        const response = await fetch(`${baseUrl}/artifact/model/${encodeURIComponent(id)}/rate`, {
            headers: getHeaders()
        });
        const data = await response.json();
        displayResponse('rate-response', {
            status: response.status,
            statusText: response.statusText,
            body: data
        }, !response.ok);
    } catch (error) {
        displayResponse('rate-response', { error: error.message }, true);
    }
}

// 7. Reset Registry
async function resetRegistry() {
    if (!confirm('Are you sure you want to reset the registry? This will delete all artifacts!')) {
        return;
    }

    const baseUrl = getApiBaseUrl();
    if (!baseUrl) return;

    displayLoading('reset-response');
    try {
        const response = await fetch(`${baseUrl}/reset`, {
            method: 'DELETE',
            headers: getHeaders()
        });
        const data = response.status === 200 ? { message: 'Registry reset successfully' } : await response.json();
        displayResponse('reset-response', {
            status: response.status,
            statusText: response.statusText,
            body: data
        }, !response.ok);
    } catch (error) {
        displayResponse('reset-response', { error: error.message }, true);
    }
}

// Load saved configuration on page load
window.addEventListener('DOMContentLoaded', function() {
    const savedUrl = localStorage.getItem('apiBaseUrl');
    const savedToken = localStorage.getItem('authToken');

    if (savedUrl) {
        document.getElementById('apiBaseUrl').value = savedUrl;
    }
    if (savedToken) {
        document.getElementById('authToken').value = savedToken;
    }

    // Save configuration when it changes
    document.getElementById('apiBaseUrl').addEventListener('blur', function() {
        localStorage.setItem('apiBaseUrl', this.value.trim());
    });
    document.getElementById('authToken').addEventListener('blur', function() {
        localStorage.setItem('authToken', this.value.trim());
    });
});

