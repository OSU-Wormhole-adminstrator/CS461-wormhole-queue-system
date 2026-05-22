// app/static/js/currentticket.js
// JavaScript for handling ticket resolution actions on the current ticket page.

document.addEventListener('DOMContentLoaded', function() {
    const resolveForm = document.getElementById('resolve-form');
    if (!resolveForm) return;

    resolveForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const formData = new FormData(this);

        try {
            const response = await fetch(this.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            const data = await response.json();

            if (response.ok && data.redirect_url) {
                window.location.href = data.redirect_url;
                return;
            }

            alert(data.error || data.message || 'Failed to resolve ticket');
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred while resolving the ticket');
        }
    });
});
