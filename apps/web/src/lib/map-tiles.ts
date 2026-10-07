import type * as Leaflet from 'leaflet';

export const MAP_TILES = {
  osm: { name: 'نقشه خیابان‌ها', url: 'https://tile.openstreetmap.de/{z}/{x}/{y}.png', subdomains: '', maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' },
  osmStandard: { name: 'نقشه استاندارد', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', subdomains: '', maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' },
} as const;

export type MapTheme = keyof typeof MAP_TILES;
export type MapTileStatus = 'loading' | 'ready' | 'unavailable';
export const MAP_TILE_ORDER: MapTheme[] = ['osm', 'osmStandard'];

/** Bounded provider fallback, including connections that stall without tileerror. */
export function createMapTiles(
  L: Pick<typeof Leaflet, 'tileLayer'>,
  map: Leaflet.Map,
  onChange: (theme: MapTheme, status: MapTileStatus) => void,
) {
  let layer: Leaflet.TileLayer | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  let attempted = new Set<MapTheme>();

  const apply = (theme: MapTheme) => {
    if (disposed) return;
    clearTimeout(timer);
    layer?.off();
    layer?.remove();
    attempted.add(theme);
    onChange(theme, 'loading');
    const config = MAP_TILES[theme];
    const nextLayer = L.tileLayer(config.url, { ...config, maxNativeZoom: config.maxZoom, maxZoom: 20 });
    layer = nextLayer;
    let errors = 0;
    const fallback = () => {
      if (disposed || layer !== nextLayer) return;
      clearTimeout(timer);
      const next = MAP_TILE_ORDER.find((candidate) => !attempted.has(candidate));
      if (next) apply(next);
      else onChange(theme, 'unavailable');
    };
    nextLayer.on('tileload', () => {
      if (disposed || layer !== nextLayer) return;
      clearTimeout(timer);
      onChange(theme, 'ready');
    });
    nextLayer.on('tileerror', () => {
      if (++errors >= 3) fallback();
    });
    timer = setTimeout(fallback, 8000);
    nextLayer.addTo(map);
  };

  return {
    select(theme: MapTheme = 'osm') { attempted = new Set(); apply(theme); },
    dispose() { disposed = true; clearTimeout(timer); layer?.off(); layer?.remove(); },
  };
}
