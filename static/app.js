/* TrolleySnipe - minimal JS for HTMX enhancements */
document.addEventListener('DOMContentLoaded', function() {
    // Focus search input on load
    const searchInput = document.querySelector('input[name="q"]');
    if (searchInput && !searchInput.value) {
        searchInput.focus();
    }
});
