document.addEventListener('DOMContentLoaded', function() {
    // Keep the queue socket for ticket count/refresh events.
    const socket = io('/queue');

    // Open a separate assistant socket so admins can see this WA as present.
    const assistantSocket = io('/assistant');

    socket.on('connect', function() {
        console.log('Connected to queue namespace (userpage)');
        updateTicketCount();
        console.log('Initial ticket count updated (userpage)');
    });

    socket.on('new_ticket', function(data) {
        console.log('New ticket event (userpage):', data);
        updateTicketCount();
    });

    socket.on('queue_refresh', function(data) {
        console.log('Queue refresh event (userpage)');
        refreshUserPage();
    });

    socket.on('disconnect', function() {
        console.log('Disconnected from queue namespace (userpage)');
    });

    assistantSocket.on('connect', function() {
        console.log('Connected to assistant presence namespace');
    });

    assistantSocket.on('connect_error', function(error) {
        console.log('Assistant presence socket rejected or unavailable:', error.message);
    });

    function refreshUserPage() {
        location.reload();
    }

    function updateTicketCount() {
        console.log('fetching ticket count...');
        fetch('/api/unskippedtickets')
            .then(response => {
            return response.json();
        })
            .then(data => {
                const ticketCountElem = document.getElementById('ticket-count');
                if (ticketCountElem) {
                    ticketCountElem.textContent = data.length;
                    console.log('Ticket count updated to:', data.length);
                }
            })
            .catch(error => console.error('Error fetching ticket count:', error));
    }
});
