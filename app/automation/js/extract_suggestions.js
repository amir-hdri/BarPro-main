() => {
    const suggestions = [];
    const items = document.querySelectorAll(
        '.pac-item, .suggestion, [class*="suggestion"], ' +
        '.autocomplete-item, [role="option"]'
    );

    items.forEach(item => {
        const text = item.textContent.trim();
        const lat = item.dataset.lat || item.getAttribute('data-lat');
        const lng = item.dataset.lng || item.getAttribute('data-lng');

        if (text) {
            suggestions.push({
                text: text,
                lat: lat ? parseFloat(lat) : null,
                lng: lng ? parseFloat(lng) : null,
                element: item
            });
        }
    });

    return suggestions;
}
