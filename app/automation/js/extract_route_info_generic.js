() => {
    // جستجو برای عناصر مسافت/زمان
    const distanceEl = document.querySelector(
        '.distance, [class*="distance"], [id*="distance"], ' +
        '[class*="مسافت"], [id*="مسافت"]'
    );
    const durationEl = document.querySelector(
        '.duration, [class*="duration"], [id*="duration"], ' +
        '[class*="زمان"], [id*="زمان"]'
    );

    return {
        distance: distanceEl ? distanceEl.textContent.trim() : null,
        duration: durationEl ? durationEl.textContent.trim() : null
    };
}
