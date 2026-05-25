({ selector, lat, lng }) => {
    if (typeof ol === 'undefined' || !ol.proj) return false;

    const rootElement =
        document.querySelector(selector) ||
        document.querySelector('.ol-map') ||
        document.querySelector('.ol-viewport') ||
        document.querySelector('#map');
    if (!rootElement) return false;

    const mapElement = rootElement.classList?.contains('ol-viewport')
        ? rootElement.parentElement || rootElement
        : rootElement;

    const matchesMap = (value) => (
        value &&
        typeof value.getView === 'function' &&
        typeof value.getTargetElement === 'function' &&
        typeof value.dispatchEvent === 'function'
    );

    const findMap = () => {
        const directCandidates = [mapElement._map, mapElement.__ol_map__, window.map];
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
                const targetElement = value.getTargetElement();
                if (targetElement === mapElement || mapElement.contains(targetElement) || targetElement?.contains?.(mapElement)) {
                    return value;
                }
            } catch (_error) {
                continue;
            }
        }

        return null;
    };

    const dispatchCenterClick = (element) => {
        const target = element.querySelector('canvas') || element.querySelector('.ol-viewport') || element;
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

    const coordinate = ol.proj.fromLonLat([lng, lat]);
    const view = map.getView();
    view.setCenter(coordinate);
    if (typeof view.getZoom === 'function' && typeof view.setZoom === 'function' && view.getZoom() < 15) {
        view.setZoom(15);
    }

    const pixel = map.getPixelFromCoordinate(coordinate);
    dispatchCenterClick(map.getTargetElement());
    map.dispatchEvent({
        type: 'singleclick',
        coordinate,
        pixel,
    });

    return true;
}
