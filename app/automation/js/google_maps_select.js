({ selector, lat, lng }) => {
    if (typeof google === 'undefined' || !google.maps) return false;

    const candidateSelectors = [selector, '.gm-style', '#map', '.map', '[data-map]'].filter(Boolean);
    const containers = [];
    candidateSelectors.forEach((item) => {
        const element = document.querySelector(item);
        if (element && !containers.includes(element)) {
            containers.push(element.closest('.gm-style') || element.querySelector('.gm-style') || element);
        }
    });
    if (!containers.length) {
        const fallback = document.querySelector('.gm-style');
        if (fallback) containers.push(fallback);
    }

    const dispatchCenterClick = (element) => {
        const target = element.querySelector('canvas') || element;
        const rect = target.getBoundingClientRect();
        if (!rect.width || !rect.height) return false;
        const clientX = rect.left + (rect.width / 2);
        const clientY = rect.top + (rect.height / 2);
        const eventInit = {
            bubbles: true,
            cancelable: true,
            clientX,
            clientY,
            button: 0,
            buttons: 1,
            view: window,
        };

        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((type) => {
            const EventCtor = type.startsWith('pointer') && typeof PointerEvent !== 'undefined' ? PointerEvent : MouseEvent;
            target.dispatchEvent(new EventCtor(type, eventInit));
        });
        return { clientX, clientY };
    };

    const matchesMap = (value) => (
        value &&
        typeof value.setCenter === 'function' &&
        typeof value.getDiv === 'function'
    );

    const findMapInstance = (container) => {
        const directCandidates = [container, container.parentElement, container.closest('[id*="map"], [class*="map"]')];
        for (const candidate of directCandidates) {
            if (!candidate) continue;
            for (const key of Object.keys(candidate)) {
                try {
                    const value = candidate[key];
                    if (matchesMap(value)) return value;
                } catch (_error) {
                    continue;
                }
            }
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
                const div = value.getDiv();
                if (div === container || container.contains(div) || div?.contains?.(container)) {
                    return value;
                }
            } catch (_error) {
                continue;
            }
        }

        return null;
    };

    return new Promise((resolve) => {
        const container = containers[0];
        if (!container) {
            resolve(false);
            return;
        }

        const map = findMapInstance(container);
        const latLng = new google.maps.LatLng(lat, lng);

        if (map) {
            try {
                map.setCenter(latLng);
                if (typeof map.getZoom === 'function' && typeof map.setZoom === 'function' && map.getZoom() < 15) {
                    map.setZoom(15);
                }
            } catch (_error) {
                // ادامه با کلیک DOM
            }
        }

        setTimeout(() => {
            const clickResult = dispatchCenterClick(container);
            if (map && google.maps.event) {
                try {
                    google.maps.event.trigger(map, 'click', { latLng });
                } catch (_error) {
                    // فقط کلیک DOM کافی است
                }
            }
            resolve(Boolean(clickResult));
        }, 180);
    });
}
