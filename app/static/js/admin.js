document.addEventListener('DOMContentLoaded', function() {
    const rosterContainer = document.getElementById('live-roster');
    const idleLogTable = document.getElementById('idle-log');
    let idleLogBody = document.querySelector('#idle-log tbody');

    // Defensive fallback: the template should include a tbody, but creating one
    // here prevents a silent empty log if the markup regresses later.
    if (!idleLogBody && idleLogTable) {
        idleLogBody = document.createElement('tbody');
        idleLogTable.appendChild(idleLogBody);
    }

    if (rosterContainer) {
        const socket = io('/admin');

        fetch('/api/admin/roster')
            .then(response => response.json())
            .then(renderRoster)
            .catch(error => console.error('Error loading roster:', error));

        socket.on('roster_update', renderRoster);

        socket.on('critical_alert', data => {
            showToast(data.message, 'danger');
            loadIdleLog();
        });
    }

    if (idleLogBody) {
        loadIdleLog();
    }

    function renderRoster(roster) {
        if (!rosterContainer) return;

        if (!Array.isArray(roster) || roster.length === 0) {
            rosterContainer.innerHTML = '<p class="monitoring-empty">No active assistants found.</p>';
            return;
        }

        rosterContainer.innerHTML = roster.map(assistant => `
            <div class="roster-row">
                <span class="status-dot ${assistant.status}" title="${assistant.status}"></span>
                <span class="assistant-name">${escapeHtml(assistant.name)}</span>
                <span class="assistant-status">${formatStatus(assistant.status)}</span>
            </div>
        `).join('');
    }

    function loadIdleLog() {
        if (!idleLogBody) return;

        fetch('/api/admin/idle-log')
            .then(response => response.json())
            .then(renderIdleLog)
            .catch(error => console.error('Error loading idle log:', error));
    }

    function renderIdleLog(payload) {
        const emptyState = document.getElementById('idle-log-empty');
        const events = payload && Array.isArray(payload.events) ? payload.events : [];

        idleLogBody.innerHTML = events.map(event => `
            <tr>
                <td>${escapeHtml(event.assistant)}</td>
                <td>${escapeHtml(event.triggered_at_local)}</td>
                <td>${event.open_ticket_count}</td>
                <td>${event.oldest_ticket_wait_minutes ?? 'N/A'}</td>
            </tr>
        `).join('');

        if (emptyState) {
            emptyState.hidden = events.length > 0;
        }
    }

    function showToast(message, type) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => toast.classList.add('toast-exit'), 7600);
        setTimeout(() => toast.remove(), 8200);
    }

    function formatStatus(status) {
        if (status === 'active') return 'Active';
        if (status === 'idle') return 'Idle';
        return 'Offline';
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
});
