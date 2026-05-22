document.addEventListener('DOMContentLoaded', function() {
    // Connect to the queue namespace
    const socket = io('/queue');

    socket.on('connect', function() {
        console.log('Connected to queue namespace');
        updateTicketTable();
        console.log('Initial ticket table loaded');
    });

    socket.on('new_ticket', function(data) {
        console.log('Ticket update received:', data);
        updateTicketTable();
    });

    socket.on('queue_refresh', function() {
        console.log('Queue refresh event received');
        updateTicketTable();
    });

    socket.on('disconnect', function() {
        console.log('Disconnected from queue namespace');
    });

    function setCellText(row, value) {
        const cell = document.createElement('td');
        cell.textContent = value ?? '';
        row.appendChild(cell);
    }

    function updateTicketTable() {
        fetch('/api/livequeuetickets', { headers: { 'Accept': 'application/json' } })
            .then(response => {
                console.log('Response status', response.status);
                if (!response.ok) throw new Error(`Live queue API returned ${response.status}`);
                return response.json();
            })
            .then(tickets => {
                console.log('API tickets:', tickets);

                const ticketTableBody = document.querySelector('#tickets tbody');
                if (!ticketTableBody) return;
                ticketTableBody.innerHTML = '';

                tickets.forEach((ticket, index) => {
                    const row = document.createElement('tr');
                    row.id = `ticket-${ticket.id}`;

                    const positionOrStatus = ticket.status === 'in_progress'
                        ? 'IN PROGRESS'
                        : index + 1;

                    setCellText(row, positionOrStatus);
                    setCellText(row, ticket.student_name);
                    setCellText(row, ticket.table);
                    setCellText(row, ticket.physics_course);

                    ticketTableBody.appendChild(row);
                });

                const refreshTime = document.getElementById('refresh-time');
                if (refreshTime) {
                    refreshTime.textContent = new Date().toLocaleTimeString();
                }
            })
            .catch(error => console.error('Error fetching tickets:', error));
    }
});
