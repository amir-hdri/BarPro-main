() => {
    const readGoogle = () => {
        if (typeof google === 'undefined' || !google.maps) return null;
        for (const key in window) {
            let value;
            try {
                value = window[key];
            } catch (_error) {
                continue;
            }
            if (!value || typeof value.getCenter !== 'function' || typeof value.getDiv !== 'function') continue;
            try {
                const center = value.getCenter();
                if (center && typeof center.lat === 'function' && typeof center.lng === 'function') {
                    return { lat: center.lat(), lng: center.lng() };
                }
            } catch (_error) {
                continue;
            }
        }
        return null;
    };

    const readLeaflet = () => {
        if (typeof L === 'undefined') return null;
        const container = document.querySelector('.leaflet-container');
        const map = container?._leaflet_map || container?._map || window.map;
        if (map && typeof map.getCenter === 'function') {
            const center = map.getCenter();
            return { lat: center.lat, lng: center.lng };
        }
        return null;
    };

    const readMapbox = () => {
        const map = document.querySelector('.mapboxgl-map')?._map || window.map;
        if (map && typeof map.getCenter === 'function') {
            const center = map.getCenter();
            return { lat: center.lat, lng: center.lng };
        }
        return null;
    };

    const readOpenLayers = () => {
        if (typeof ol === 'undefined' || !ol.proj) return null;
        const root = document.querySelector('.ol-map') || document.querySelector('.ol-viewport')?.parentElement;
        const map = root?._map || root?.__ol_map__ || window.map;
        if (map && typeof map.getView === 'function') {
            const center = map.getView().getCenter();
            if (center) {
                const [lng, lat] = ol.proj.toLonLat(center);
                return { lat, lng };
            }
        }
        return null;
    };

    return readGoogle() || readLeaflet() || readMapbox() || readOpenLayers();
}
