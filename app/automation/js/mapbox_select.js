({ selector, lat, lng }) => {
    if (typeof mapboxgl === 'undefined') return false;

    const mapElement =
        document.querySelector(selector) ||
        document.querySelector('.mapboxgl-map') ||
        document.querySelector('#map');
    if (!mapElement) return false;

    const matchesMap = (value) => (
        value &&
        typeof value.setCenter === 'function' &&
        typeof value.getContainer === 'function' &&
        typeof value.fire === 'function'
    );

    const findMap = () => {
        const directCandidates = [mapElement._map, window.map];
        for (const candidate of directCandidates) {
            if (matchesMap(candidate)) return candidate;
        }

        for (const key in window) {
            let value;
            try {
                value = window[key];
            } catch (_error) {
                continue;
            }
            if (!matchesMap(value)) continue;
            try {
                if (value.getContainer() === mapElement) {
                    return value;
                }
            } catch (_error) {
                continue;
            }
        }

        return null;
    };

    const dispatchCenterClick = (element) => {
        const target = element.querySelector('canvas') || element;
        const rect = target.getBoundingClientRect();
        if (!rect.width || !rect.height) return false;
        const clientX = rect.left + (rect.width / 2);
        const clientY = rect.top + (rect.height / 2);
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((type) => {
            const EventCtor = type.startsWith('pointer') && typeof PointerEvent !== 'undefined' ? PointerEvent : MouseEvent;
            target.dispatchEvent(new EventCtor(type, {
                bubbles: true,
                cancelable: true,
                clientX,
                clientY,
                button: 0,
                buttons: 1,
                view: window,
            }));
        });
        return true;
    };

    const map = findMap();
    if (!map) return false;

    map.setCenter([lng, lat]);
    if (typeof map.getZoom === 'function' && typeof map.setZoom === 'function' && map.getZoom() < 15) {
        map.setZoom(15);
    }

    dispatchCenterClick(mapElement);
    map.fire('click', {
        lngLat: { lng, lat },
        point: typeof map.project === 'function' ? map.project([lng, lat]) : null,
    });

    return true;
}
