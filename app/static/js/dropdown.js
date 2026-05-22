// app/static/js/dropdown.js
// Accessible click/tap dropdown behavior for the shared navigation menu.

document.addEventListener('DOMContentLoaded', function() {
    const dropdowns = document.querySelectorAll('.dropdown');

    function closeDropdown(dropdown) {
        dropdown.classList.remove('is-open');
        const button = dropdown.querySelector('.dropbtn');
        if (button) button.setAttribute('aria-expanded', 'false');
    }

    function closeOtherDropdowns(activeDropdown) {
        dropdowns.forEach(dropdown => {
            if (dropdown !== activeDropdown) closeDropdown(dropdown);
        });
    }

    dropdowns.forEach(dropdown => {
        const button = dropdown.querySelector('.dropbtn');
        if (!button) return;

        button.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation();

            const willOpen = !dropdown.classList.contains('is-open');
            closeOtherDropdowns(dropdown);
            dropdown.classList.toggle('is-open', willOpen);
            button.setAttribute('aria-expanded', String(willOpen));
        });
    });

    document.addEventListener('click', function(event) {
        dropdowns.forEach(dropdown => {
            if (!dropdown.contains(event.target)) closeDropdown(dropdown);
        });
    });

    document.addEventListener('keydown', function(event) {
        if (event.key !== 'Escape') return;
        dropdowns.forEach(closeDropdown);
    });
});
