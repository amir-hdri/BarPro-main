"""
Common Stealth Utilities
========================
Shared stealth scripts and utilities used by both stealth.py and stealth_advanced.py
to avoid code duplication.
"""


# ============================================================================
# CORE STEALTH SCRIPT TEMPLATES
# ============================================================================

def build_core_stealth_script(
    webgl_vendor: str,
    webgl_renderer: str,
    hw_concurrency: int,
    device_memory: int,
) -> str:
    """
    Build core stealth script with common evasion techniques.
    This is shared between basic and advanced stealth.

    Args:
        webgl_vendor: WebGL vendor string
        webgl_renderer: WebGL renderer string
        hw_concurrency: Hardware concurrency value
        device_memory: Device memory value

    Returns:
        JavaScript stealth script
    """
    return f"""
(() => {{
    // 1. Remove webdriver flag
    try {{ Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }}); }} catch(_) {{}}

    // 2. Remove Playwright CDP leak properties
    ['__playwright','__pw_manual__','__PW_inspect__','__playwright__',
     '_playwrightWorkerIndex','_playwrightWorkerCount','__cdp',
     'cdc_adoQpoasnfa76pfcZLmcfl_Array','cdc_adoQpoasnfa76pfcZLmcfl_Promise',
     'cdc_adoQpoasnfa76pfcZLmcfl_Symbol'
    ].forEach(p => {{ try {{ delete window[p]; delete navigator[p]; }} catch(_) {{}} }});

    // 3. Full chrome runtime mock
    try {{
        window.chrome = {{
            app: {{ isInstalled: false }},
            runtime: {{
                id: undefined,
                connect: function() {{}},
                sendMessage: function() {{}},
                onMessage: {{ addListener: function() {{}}, removeListener: function() {{}}, hasListener: () => false }},
                onConnect: {{ addListener: function() {{}}, removeListener: function() {{}}, hasListener: () => false }},
                PlatformOs: {{ MAC:'mac', WIN:'win', ANDROID:'android', CROS:'cros', LINUX:'linux', OPENBSD:'openbsd' }},
                PlatformArch: {{ ARM:'arm', X86_32:'x86-32', X86_64:'x86-64' }},
                RequestUpdateCheckStatus: {{ THROTTLED:'throttled', NO_UPDATE:'no_update', UPDATE_AVAILABLE:'update_available' }},
                OnInstalledReason: {{ INSTALL:'install', UPDATE:'update', CHROME_UPDATE:'chrome_update', SHARED_MODULE_UPDATE:'shared_module_update' }},
            }},
            csi: () => ({{ startE: Date.now(), onloadT: Date.now() + Math.random()*200, pageT: 1000+Math.random()*500, tran: 15 }}),
            loadTimes: () => ({{
                requestTime: performance.timing.navigationStart/1000,
                startLoadTime: performance.timing.navigationStart/1000,
                commitLoadTime: performance.timing.responseStart/1000,
                finishDocumentLoadTime: performance.timing.domContentLoadedEventEnd/1000,
                finishLoadTime: performance.timing.loadEventEnd/1000,
                firstPaintTime: (performance.timing.navigationStart+200+Math.random()*100)/1000,
                firstPaintAfterLoadTime: 0,
                navigationType: 'Other',
                wasFetchedViaSpdy: true,
                wasNpnNegotiated: true,
                npnNegotiatedProtocol: 'h2',
                wasAlternateProtocolAvailable: false,
                connectionInfo: 'h2',
            }}),
        }};
    }} catch(_) {{}}

    // 4. Permissions — prevent notification fingerprinting
    const _origPerms = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (params) =>
        params.name === 'notifications'
            ? Promise.resolve({{ state: Notification.permission, onchange: null }})
            : _origPerms(params);

    // 5. WebGL vendor/renderer spoof (WebGL1 + WebGL2)
    const _patchWebGL = (ctx) => {{
        if (!ctx) return;
        const _orig = ctx.prototype.getParameter;
        ctx.prototype.getParameter = function(p) {{
            if (p === 37445) return '{webgl_vendor}';
            if (p === 37446) return '{webgl_renderer}';
            return _orig.call(this, p);
        }};
    }};
    try {{ _patchWebGL(WebGLRenderingContext); }} catch(_) {{}}
    try {{ _patchWebGL(WebGL2RenderingContext); }} catch(_) {{}}

    // 6. Canvas noise — subtle per-session pixel shift defeats fingerprinting
    const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
        const ctx = this.getContext('2d');
        if (ctx) {{ const d = ctx.getImageData(0,0,1,1); d.data[0]^=1; ctx.putImageData(d,0,0); }}
        return _origToDataURL.call(this, type, quality);
    }};
    const _origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function(x,y,w,h) {{
        const d = _origGetImageData.call(this,x,y,w,h);
        d.data[0]^=1;
        return d;
    }};

    // 7. AudioContext fingerprint noise
    try {{
        const _origGetChannelData = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function(ch) {{
            const arr = _origGetChannelData.call(this, ch);
            for (let i=0; i<Math.min(arr.length,20); i++) arr[i] += Math.random()*0.0000001;
            return arr;
        }};
    }} catch(_) {{}}

    // 8. Hardware / memory
    try {{ Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hw_concurrency} }}); }} catch(_) {{}}
    try {{ Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {device_memory} }}); }} catch(_) {{}}

    // 9. Realistic plugin list
    try {{
        Object.defineProperty(navigator, 'plugins', {{ get: () => [
            {{ name:'PDF Viewer', filename:'internal-pdf-viewer', description:'Portable Document Format' }},
            {{ name:'Chrome PDF Viewer', filename:'internal-pdf-viewer', description:'' }},
            {{ name:'Chromium PDF Viewer', filename:'internal-pdf-viewer', description:'' }},
        ]}});
        Object.defineProperty(navigator, 'mimeTypes', {{ get: () => [
            {{ type:'application/pdf' }}, {{ type:'text/pdf' }}
        ]}});
    }} catch(_) {{}}

    // 10. Languages (should be set by config)
    // Languages are typically set via config, not here

    // 11. Network info
    try {{
        Object.defineProperty(navigator, 'connection', {{
            get: () => ({{ downlink:10, effectiveType:'4g', rtt:50, saveData:false, onchange:null }})
        }});
    }} catch(_) {{}}

    // 12. toString() cloaking — prevent native-function detection
    const _nativeToString = Function.prototype.toString;
    Function.prototype.toString = function() {{
        if (this === Function.prototype.toString) return 'function toString() {{ [native code] }}';
        if (this === navigator.permissions.query) return 'function query() {{ [native code] }}';
        return _nativeToString.call(this);
    }};
}})();
"""


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def pick_random_fingerprint() -> dict:
    """
    Pick a random fingerprint configuration.

    Returns:
        Dictionary with fingerprint values
    """
    # This function will use the shared configuration
    # In production, it would import from config
    return {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "viewport": {"width": 1920, "height": 1080},
        "webgl": {
            "vendor": "Google Inc. (NVIDIA)",
            "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0)",
        },
        "hw_concurrency": 8,
        "device_memory": 8,
    }


def add_random_delay(_page, min_seconds: float = 0.5, max_seconds: float = 2.0) -> None:
    """Add random delay for human-like behavior."""
    import asyncio
    import random
    asyncio.get_event_loop().run_until_complete(
        asyncio.sleep(random.uniform(min_seconds, max_seconds))
    )
