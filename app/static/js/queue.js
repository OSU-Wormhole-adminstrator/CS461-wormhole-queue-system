// app/static/js/queue.js
// Real-time queue dashboard updates using Socket.IO without forced page reloads.

document.addEventListener('DOMContentLoaded', function() {
    const socket = io('/queue');
    const openTicketsList = document.getElementById('open-tickets-list');
    const currentTicketsList = document.getElementById('current-tickets-list');
    const queueUpdateStatus = document.getElementById('queue-update-status');

    socket.on('connect', function() {
        console.log('Connected to queue updates');
        updateQueueDashboard();
    });

    socket.on('new_ticket', function(data) {
        console.log('Ticket update received:', data);
        updateQueueDashboard();
    });

    socket.on('queue_refresh', function() {
        console.log('Queue refresh signal received');
        updateQueueDashboard();
    });

    socket.on('disconnect', function() {
        console.log('Disconnected from queue updates');
    });

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function ticketUrl(template, ticketId) {
        if (!template) return '#';
        return template.replace(/\/0(?=([/?#]|$))/, `/${encodeURIComponent(ticketId)}`);
    }

    function renderOpenTickets(tickets) {
        if (!openTicketsList) return;

        const template = openTicketsList.dataset.ticketUrlTemplate || '';
        const openTickets = tickets.filter(ticket => ticket.status === 'live');

        if (openTickets.length === 0) {
            openTicketsList.innerHTML = '<li>No open tickets.</li>';
            return;
        }

        openTicketsList.innerHTML = openTickets.map(ticket => `
            <li>
                <a href="${ticketUrl(template, ticket.id)}">
                    ${escapeHtml(ticket.student_name)} — ${escapeHtml(ticket.physics_course)}
                    (Table ${escapeHtml(ticket.table)})
                </a>
            </li>
        `).join('');
    }

    function renderCurrentTickets(tickets) {
        if (!currentTicketsList) return;

        const template = currentTicketsList.dataset.ticketUrlTemplate || '';
        const currentTickets = tickets.filter(ticket => ticket.status === 'in_progress');

        if (currentTickets.length === 0) {
            currentTicketsList.innerHTML = '<li>No tickets currently in progress.</li>';
            return;
        }

        currentTicketsList.innerHTML = currentTickets.map(ticket => `
            <li>
                <a href="${ticketUrl(template, ticket.id)}">
                    ${escapeHtml(ticket.student_name)} (Table ${escapeHtml(ticket.table)}) - In progress
                </a>
            </li>
        `).join('');
    }

    function updateQueueDashboard() {
        if (!openTicketsList && !currentTicketsList) return;

        fetch('/api/livequeuetickets', { headers: { 'Accept': 'application/json' } })
            .then(response => {
                if (!response.ok) throw new Error(`Queue API returned ${response.status}`);
                return response.json();
            })
            .then(tickets => {
                renderOpenTickets(tickets);
                renderCurrentTickets(tickets);
                if (queueUpdateStatus) {
                    queueUpdateStatus.textContent = `Updated ${new Date().toLocaleTimeString()}`;
                }
            })
            .catch(error => {
                console.error('Error updating queue dashboard:', error);
                if (queueUpdateStatus) {
                    queueUpdateStatus.textContent = 'Unable to refresh queue data automatically.';
                }
            });
    }
});
