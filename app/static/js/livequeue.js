document.addEventListener('DOMContentLoaded', function () {
    const socket = io('/queue');
    const ticketTableBody = document.querySelector('#tickets tbody');
    const refreshTime = document.getElementById('refresh-time');
    const refreshStatus = document.getElementById('refresh-status');
    const refreshSpinner = document.getElementById('refresh-spinner');

    socket.on('connect', function () {
        console.log('Connected to queue namespace');
        updateTicketTable();
    });

    socket.on('new_ticket', function (data) {
        console.log('New ticket created:', data);
        updateTicketTable();
    });

    socket.on('queue_refresh', function (data) {
        console.log('Queue refresh event received:', data);
        refreshLiveQueue();
    });

    socket.on('disconnect', function () {
        console.log('Disconnected from queue namespace');
        setRefreshStatus('Disconnected', false);
    });

    function refreshLiveQueue() {
        location.reload();
    }

    function setRefreshStatus(message, isLoading) {
        if (!refreshStatus) {
            return;
        }

        if (refreshSpinner) {
            refreshSpinner.classList.toggle('hidden', !isLoading);
        }

        const textNode = Array.from(refreshStatus.childNodes).find(
            node => node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 0,
        );

        if (textNode) {
            textNode.textContent = ` ${message}`;
        } else {
            refreshStatus.append(` ${message}`);
        }
    }

    function updateRefreshTime() {
        if (!refreshTime) {
            return;
        }

        refreshTime.style.transition = 'opacity 0.2s ease';
        refreshTime.style.opacity = '0';

        window.setTimeout(() => {
            refreshTime.textContent = new Date().toLocaleTimeString();
            refreshTime.style.opacity = '1';
        }, 160);
    }

    function renderEmptyState() {
        if (!ticketTableBody) {
            return;
        }

        const emptyRow = document.createElement('tr');
        emptyRow.className = 'motion-safe:animate-in motion-safe:fade-in-0 motion-safe:zoom-in-95 motion-safe:duration-300';
        emptyRow.innerHTML = `
            <td colspan="4" class="px-6 py-12 text-center">
                <div class="mx-auto max-w-sm motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-3 motion-safe:duration-300">
                    <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                        <svg class="h-6 w-6" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3M4 11h16M5 21h14a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1Z"/>
                        </svg>
                    </div>
                    <p class="text-sm font-semibold text-gray-900 dark:text-gray-100">No one is currently waiting</p>
                    <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">New help requests will appear here automatically.</p>
                </div>
            </td>
        `;
        ticketTableBody.appendChild(emptyRow);
    }

    function renderErrorState() {
        if (!ticketTableBody) {
            return;
        }

        ticketTableBody.innerHTML = `
            <tr>
                <td colspan="4" class="px-6 py-10 text-center text-sm text-red-700 dark:text-red-300">
                    Unable to refresh the live queue. Please refresh the page or check the connection.
                </td>
            </tr>
        `;
    }

    function renderTickets(tickets) {
        if (!ticketTableBody) {
            return;
        }

        ticketTableBody.innerHTML = '';

        if (tickets.length === 0) {
            renderEmptyState();
            return;
        }

        tickets.forEach((ticket, index) => {
            const row = document.createElement('tr');
            row.id = `ticket-${ticket.id}`;
            row.className = 'interactive-table-row motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-right-3 motion-safe:duration-300 hover:bg-orange-50/60 dark:hover:bg-osu-navy-dark/30';
            row.style.animationDelay = `${index * 55}ms`;

            const positionCell = document.createElement('td');
            positionCell.className = 'px-6 py-4 align-middle';

            const positionBadge = document.createElement('span');

            if (ticket.status === 'in_progress') {
                positionBadge.className =
                    'inline-flex min-w-28 items-center justify-center rounded-full bg-purple-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-purple-800 ring-1 ring-purple-200 motion-safe:animate-flash dark:bg-osu-lavender/20 dark:text-osu-lavender-dark dark:ring-osu-lavender-dark/30';
                positionBadge.textContent = 'In progress';
            } else {
                positionBadge.className =
                    'inline-flex h-9 min-w-12 items-center justify-center rounded-lg bg-osu-navy px-3 text-sm font-bold tabular-nums text-white shadow-sm ring-1 ring-osu-navy/30 dark:bg-osu-navy-dark dark:ring-osu-blue-light/20';
                positionBadge.textContent = `#${index + 1}`;
            }

            positionCell.appendChild(positionBadge);

            const nameCell = document.createElement('td');
            nameCell.className = 'px-6 py-4 align-middle font-medium text-gray-900 dark:text-gray-100';
            nameCell.textContent = ticket.student_name || 'Unknown student';

            const tableCell = document.createElement('td');
            tableCell.className = 'px-6 py-4 align-middle text-gray-700 dark:text-gray-200';

            const tableBadge = document.createElement('span');
            tableBadge.className =
                'inline-flex min-w-10 items-center justify-center rounded-lg bg-gray-100 px-2.5 py-1 text-sm font-semibold tabular-nums text-gray-800 ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:ring-osu-blue-light/20';
            tableBadge.textContent = ticket.table || '—';

            tableCell.appendChild(tableBadge);

            const courseCell = document.createElement('td');
            courseCell.className = 'px-6 py-4 align-middle text-gray-700 dark:text-gray-200';
            courseCell.textContent = ticket.physics_course || '—';

            row.appendChild(positionCell);
            row.appendChild(nameCell);
            row.appendChild(tableCell);
            row.appendChild(courseCell);

            ticketTableBody.appendChild(row);
        });
    }

    function updateTicketTable() {
        setRefreshStatus('Refreshing queue', true);

        fetch('/api/livequeuetickets')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Queue API returned ${response.status}`);
                }
                return response.json();
            })
            .then(tickets => {
                console.log('API tickets:', tickets);
                renderTickets(tickets);
                updateRefreshTime();
                setRefreshStatus('Updated', false);
            })
            .catch(error => {
                console.error('Failed to refresh live queue:', error);
                renderErrorState();
                setRefreshStatus('Refresh failed', false);
            });
    }
});
