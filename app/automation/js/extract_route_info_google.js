() => {
    // تلاش برای یافتن رندرکننده مسیرها
    const directions = document.querySelector('[jsan*="directions"]');
    if (directions) {
        const distanceEl = directions.querySelector('[jstcache*="distance"]');
        const durationEl = directions.querySelector('[jstcache*="duration"]');

        return {
            distance: distanceEl ? distanceEl.textContent : null,
            duration: durationEl ? durationEl.textContent : null
        };
    }

    // تلاش برای استخراج از URL یا ویژگی‌های داده
    const mapData = document.querySelector('[data-route]');
    if (mapData) {
        return JSON.parse(mapData.dataset.route || '{}');
    }

    return {};
}
