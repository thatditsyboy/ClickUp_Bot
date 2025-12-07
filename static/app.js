// ==================== State ====================
let isLoading = false;

// ==================== DOM Elements ====================
const messagesContainer = document.getElementById('messagesContainer');
const messageInput = document.getElementById('messageInput');
const taskCountEl = document.getElementById('taskCount');

// ==================== Initialization ====================
document.addEventListener('DOMContentLoaded', () => {
    checkDataStatus();
});

async function checkDataStatus() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        updateTaskCount(data.count);
    } catch (error) {
        console.error('Failed to check data status:', error);
    }
}

function updateTaskCount(count) {
    taskCountEl.textContent = count || '--';
}

// ==================== Message Handling ====================
function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message || isLoading) return;

    // Clear welcome message if present
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }

    // Add user message
    addMessage(message, 'user');
    messageInput.value = '';

    // Show loading
    isLoading = true;
    const loadingEl = addLoadingMessage();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });

        const data = await response.json();
        loadingEl.remove();
        handleResponse(data);
    } catch (error) {
        loadingEl.remove();
        addAgentMessage({
            type: 'error',
            message: 'Sorry, something went wrong. Please try again.'
        });
    } finally {
        isLoading = false;
    }
}

function sendSuggestion(element) {
    messageInput.value = element.textContent;
    sendMessage();
}

// ==================== Message Rendering ====================
function addMessage(text, type) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${type}`;

    const avatarIcon = type === 'user'
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>';

    messageEl.innerHTML = `
        <div class="message-avatar">${avatarIcon}</div>
        <div class="message-content">
            <div class="message-text">${escapeHtml(text)}</div>
        </div>
    `;

    messagesContainer.appendChild(messageEl);
    scrollToBottom();
}

function addLoadingMessage() {
    const messageEl = document.createElement('div');
    messageEl.className = 'message agent';
    messageEl.innerHTML = `
        <div class="message-avatar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;
    messagesContainer.appendChild(messageEl);
    scrollToBottom();
    return messageEl;
}

function addAgentMessage(data) {
    const messageEl = document.createElement('div');
    messageEl.className = 'message agent';

    let content = '';

    switch (data.type) {
        case 'table':
            content = renderTable(data);
            break;
        case 'summary':
            content = renderSummary(data);
            break;
        case 'export':
            content = renderExport(data);
            break;
        case 'help':
            content = renderHelp(data);
            break;
        case 'error':
            content = `<div class="message-text" style="color: var(--danger);">❌ ${escapeHtml(data.message)}</div>`;
            break;
        default:
            content = `<div class="message-text">${escapeHtml(data.message || 'Done!')}</div>`;
    }

    messageEl.innerHTML = `
        <div class="message-avatar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
        </div>
        <div class="message-content">${content}</div>
    `;

    messagesContainer.appendChild(messageEl);
    scrollToBottom();
}

function handleResponse(data) {
    addAgentMessage(data);
}

// ==================== Content Renderers ====================
function renderTable(data) {
    if (!data.data || data.data.length === 0) {
        return `
            <div class="message-title">${data.title}</div>
            <div class="message-text">No data found.</div>
        `;
    }

    const columns = Object.keys(data.data[0]);
    const maxRows = 15;
    const displayData = data.data.slice(0, maxRows);

    let html = `<div class="message-title">${data.title}</div>`;
    html += '<table class="data-table"><thead><tr>';
    columns.forEach(col => {
        html += `<th>${escapeHtml(col)}</th>`;
    });
    html += '</tr></thead><tbody>';

    displayData.forEach(row => {
        html += '<tr>';
        columns.forEach(col => {
            const value = row[col] !== null && row[col] !== undefined ? row[col] : '-';
            html += `<td>${escapeHtml(String(value))}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table>';

    if (data.summary) {
        html += `<div class="message-summary">${escapeHtml(data.summary)}</div>`;
    }

    if (data.data.length > maxRows) {
        html += `<div class="message-summary">Showing ${maxRows} of ${data.data.length} rows. Export for complete data.</div>`;
    }

    return html;
}

function renderSummary(data) {
    let html = `<div class="message-title">${data.title}</div>`;
    html += '<div class="stats-grid">';

    for (const [key, value] of Object.entries(data.stats)) {
        if (typeof value === 'object') {
            html += `<div class="stat-card" style="grid-column: span 2;">`;
            html += `<div class="stat-label">${escapeHtml(key)}</div>`;
            html += '<div style="margin-top: 8px;">';
            for (const [subKey, subValue] of Object.entries(value)) {
                html += `<div style="display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.85rem;">
                    <span style="color: var(--text-secondary);">${escapeHtml(subKey || 'Unset')}</span>
                    <span style="font-weight: 600;">${subValue}</span>
                </div>`;
            }
            html += '</div></div>';
        } else {
            html += `<div class="stat-card">
                <div class="stat-value">${value}</div>
                <div class="stat-label">${escapeHtml(key)}</div>
            </div>`;
        }
    }

    html += '</div>';
    return html;
}

function renderExport(data) {
    const format = data.format || 'csv';
    return `
        <div class="message-title">📥 Export Ready</div>
        <div class="message-text">${escapeHtml(data.message)}</div>
        <div style="margin-top: 16px;">
            <button class="primary-btn" onclick="exportData('${format}')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                </svg>
                Download ${format.toUpperCase()}
            </button>
        </div>
    `;
}

function renderHelp(data) {
    let html = `<div class="message-text">${escapeHtml(data.message)}</div>`;
    html += '<ul class="suggestions-list">';
    data.suggestions.forEach(s => {
        html += `<li onclick="messageInput.value='${escapeHtml(s)}'; sendMessage();">${escapeHtml(s)}</li>`;
    });
    html += '</ul>';
    return html;
}

// ==================== Actions ====================
async function refreshData() {
    if (isLoading) return;

    // Clear welcome message if present
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }

    isLoading = true;
    const loadingEl = addLoadingMessage();

    try {
        const response = await fetch('/api/refresh');
        const data = await response.json();
        loadingEl.remove();

        if (data.success) {
            updateTaskCount(data.count);
            addAgentMessage({
                type: 'success',
                message: data.message
            });
        } else {
            addAgentMessage({
                type: 'error',
                message: data.message
            });
        }
    } catch (error) {
        loadingEl.remove();
        addAgentMessage({
            type: 'error',
            message: 'Failed to refresh data. Please check your connection.'
        });
    } finally {
        isLoading = false;
    }
}

function exportData(format) {
    window.location.href = `/api/export/${format}`;
}

// ==================== Utilities ====================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}
