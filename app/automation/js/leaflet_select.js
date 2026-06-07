({ selector, lat, lng }) => {
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
        const directCandidates = [
            mapElement._leaflet_map,
            mapElement._map,
            window.map,
            window.appMap,
            window.appMap2,
            window.appMap3
        ];
        for (const candidate of directCandidates) {
            if (!candidate) continue;
            if (matchesLeafletMap(candidate)) return candidate;
            if (matchesLeafletMap(candidate.map)) return candidate.map;
        }

        for (const key in window) {
            let value;
            try {
                value = window[key];
            } catch (_error) {
                continue;
            }
            if (!value) continue;
            if (matchesLeafletMap(value)) {
                try {
                    if (value.getContainer() === mapElement) return value;
                } catch (_) {}
            }
            if (value.map && matchesLeafletMap(value.map)) {
                try {
                    if (value.map.getContainer() === mapElement) return value.map;
                } catch (_) {}
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

    const latLngObj = { lat: Number(lat), lng: Number(lng) };
    const latLng = (typeof L !== 'undefined' && typeof L.latLng === 'function') ? L.latLng(lat, lng) : latLngObj;

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
