document.addEventListener('DOMContentLoaded', function() {
    // Connect to the queue namespace
    const socket = io('/queue');

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
                    const previousCount = ticketCountElem.textContent.trim();
                    const nextCount = String(data.length);

                    ticketCountElem.textContent = nextCount;

                    if (previousCount !== nextCount) {
                        ticketCountElem.classList.remove('motion-safe:animate-flash');
                        void ticketCountElem.offsetWidth;
                        ticketCountElem.classList.add('motion-safe:animate-flash');
                    }

                    console.log('Ticket count updated to:', data.length);
                }
            })
            .catch(error => console.error('Error fetching ticket count:', error));
    }
});
