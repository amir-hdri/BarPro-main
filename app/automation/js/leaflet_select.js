({ selector, lat, lng }) => {
    if (typeof L === 'undefined') return false;

    const mapElement =
        document.querySelector(selector) ||
        document.querySelector('.leaflet-container') ||
        document.querySelector('#map');
    if (!mapElement) return false;

    const matchesLeafletMap = (value) => (
        value &&
        typeof value.setView === 'function' &&
        typeof value.getContainer === 'function' &&
        typeof value.fire === 'function'
    );

    const findMap = () => {
        const directCandidates = [mapElement._leaflet_map, mapElement._map, window.map];
        for (const candidate of directCandidates) {
            if (matchesLeafletMap(candidate)) return candidate;
        }

        for (const key in window) {
            let value;
            try {
                value = window[key];
            } catch (_error) {
                continue;
            }
            if (!matchesLeafletMap(value)) continue;
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
        const target = element.querySelector('.leaflet-pane') || element;
        const rect = target.getBoundingClientRect();
        if (!rect.width || !rect.height) return null;
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
        return { clientX, clientY };
    };

    const map = findMap();
    if (!map) return false;

    const latLng = L.latLng(lat, lng);
    map.setView(latLng, Math.max(15, Number(map.getZoom?.() || 0)));

    const clickPoint = dispatchCenterClick(mapElement);
    const containerPoint = map.latLngToContainerPoint(latLng);
    const layerPoint = map.latLngToLayerPoint(latLng);
    map.fire('click', {
        latlng: latLng,
        layerPoint,
        containerPoint,
        originalEvent: clickPoint,
    });

    return true;
}
