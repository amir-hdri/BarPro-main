"""
Critical CDP (Chrome DevTools Protocol) leak patches.
These patches close advanced detection vectors that basic stealth misses.
"""

CDP_LEAK_PATCH_SCRIPT = """
(() => {
    // 1. Patch CDP Runtime.enable leak
    if (window.chrome && window.chrome.runtime) {
        const originalSendMessage = window.chrome.runtime.sendMessage;
        window.chrome.runtime.sendMessage = function(...args) {
            // Block CDP detection messages
            if (args[0] && typeof args[0] === 'object') {
                if (args[0].method === 'Runtime.enable' || 
                    args[0].method === 'Debugger.enable' ||
                    args[0].method === 'Network.enable') {
                    return Promise.resolve({});
                }
            }
            return originalSendMessage.apply(this, args);
        };
    }

    const originalDebug = console.debug;
    console.debug = function(...args) {
        const stack = new Error().stack;
        if (stack && (stack.includes('playwright') || stack.includes('puppeteer'))) {
            return;
        }
        return originalDebug.apply(this, args);
    };

    // 3. Patch Error.stack CDP leak
    const OriginalError = Error;
    Error = function(...args) {
        const err = new OriginalError(...args);
        const originalStack = err.stack;
        Object.defineProperty(err, 'stack', {
            get: function() {
                return originalStack
                    .replace(/playwright/gi, 'chrome')
                    .replace(/puppeteer/gi, 'chrome')
                    .replace(/__pw/gi, '__ch')
                    .replace(/cdp/gi, 'api');
            }
        });
        return err;
    };
    Error.prototype = OriginalError.prototype;

    // 4. Patch Function.toString CDP leak (advanced)
    const nativeToStringFunctionString = Error.toString.toString();
    const nativeToString = Function.prototype.toString;
    
    Function.prototype.toString = function() {
        if (this === Function.prototype.toString) {
            return nativeToStringFunctionString;
        }
        if (this === navigator.permissions.query) {
            return 'function query() { [native code] }';
        }
        if (this === navigator.geolocation.getCurrentPosition) {
            return 'function getCurrentPosition() { [native code] }';
        }
        const result = nativeToString.call(this);
        return result.replace(/playwright|puppeteer|__pw|cdp/gi, '');
    };

    // 5. Patch iframe contentWindow CDP leak
    const originalCreateElement = document.createElement;
    document.createElement = function(tagName) {
        const element = originalCreateElement.call(document, tagName);
        if (tagName.toLowerCase() === 'iframe') {
            const originalContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
            Object.defineProperty(element, 'contentWindow', {
                get: function() {
                    const win = originalContentWindow.get.call(this);
                    if (win) {
                        try {
                            delete win.navigator.__playwright__;
                            delete win.__playwright__;
                            Object.defineProperty(win.navigator, 'webdriver', {
                                get: () => undefined
                            });
                        } catch(e) {}
                    }
                    return win;
                }
            });
        }
        return element;
    };

    // 6. Patch Worker CDP leak
    const OriginalWorker = Worker;
    Worker = function(scriptURL, options) {
        const worker = new OriginalWorker(scriptURL, options);
        try {
            worker.postMessage({
                type: '__stealth_init__',
                script: `
                    delete self.navigator.__playwright__;
                    delete self.__playwright__;
                    Object.defineProperty(self.navigator, 'webdriver', {
                        get: () => undefined
                    });
                `
            });
        } catch(e) {}
        return worker;
    };
    Worker.prototype = OriginalWorker.prototype;

    // 7. Patch Notification.permission CDP leak
    try {
        const originalPermission = Object.getOwnPropertyDescriptor(Notification, 'permission');
        Object.defineProperty(Notification, 'permission', {
            get: function() {
                return 'default';
            }
        });
    } catch(e) {}

    // 8. Patch navigator.mediaDevices CDP leak
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        const originalEnumerate = navigator.mediaDevices.enumerateDevices;
        navigator.mediaDevices.enumerateDevices = async function() {
            const devices = await originalEnumerate.call(this);
            // Return realistic device list
            return devices.length > 0 ? devices : [
                { deviceId: 'default', kind: 'audioinput', label: '', groupId: 'default' },
                { deviceId: 'default', kind: 'audiooutput', label: '', groupId: 'default' },
                { deviceId: 'default', kind: 'videoinput', label: '', groupId: 'default' }
            ];
        };
    }

    // 9. Patch Battery API CDP leak
    if (navigator.getBattery) {
        const originalGetBattery = navigator.getBattery;
        navigator.getBattery = async function() {
            const battery = await originalGetBattery.call(this);
            return {
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1.0,
                addEventListener: () => {},
                removeEventListener: () => {},
                dispatchEvent: () => true
            };
        };
    }

    // 10. Patch performance.memory CDP leak
    if (performance.memory) {
        Object.defineProperty(performance, 'memory', {
            get: function() {
                return {
                    jsHeapSizeLimit: 2172649472,
                    totalJSHeapSize: 10000000 + Math.random() * 10000000,
                    usedJSHeapSize: 10000000 + Math.random() * 5000000
                };
            }
        });
    }
})();
"""


TLS_FINGERPRINT_PATCH = """
(() => {
    // Patch TLS fingerprint leaks via Fetch API
    const originalFetch = window.fetch;
    window.fetch = function(resource, init) {
        // Ensure realistic headers
        if (init && init.headers) {
            const headers = new Headers(init.headers);
            if (!headers.has('sec-ch-ua')) {
                headers.set('sec-ch-ua', '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"');
            }
            if (!headers.has('sec-ch-ua-mobile')) {
                headers.set('sec-ch-ua-mobile', '?0');
            }
            if (!headers.has('sec-ch-ua-platform')) {
                headers.set('sec-ch-ua-platform', '"Windows"');
            }
            init.headers = headers;
        }
        return originalFetch.call(this, resource, init);
    };

    // Patch XMLHttpRequest TLS leak
    const OriginalXHR = XMLHttpRequest;
    XMLHttpRequest = function() {
        const xhr = new OriginalXHR();
        const originalOpen = xhr.open;
        xhr.open = function(method, url, ...args) {
            originalOpen.call(this, method, url, ...args);
            // Add realistic headers
            this.setRequestHeader('sec-ch-ua', '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"');
            this.setRequestHeader('sec-ch-ua-mobile', '?0');
            this.setRequestHeader('sec-ch-ua-platform', '"Windows"');
        };
        return xhr;
    };
    XMLHttpRequest.prototype = OriginalXHR.prototype;
})();
"""


ADVANCED_TIMING_PATCH = """
(() => {
    // Patch performance.now() to add realistic jitter
    const originalNow = performance.now;
    let offset = Math.random() * 0.1;
    performance.now = function() {
        offset += (Math.random() - 0.5) * 0.01;
        return originalNow.call(this) + offset;
    };

    // Patch Date.now() for consistency
    const originalDateNow = Date.now;
    Date.now = function() {
        return originalDateNow() + Math.floor(offset);
    };

    // Patch setTimeout/setInterval timing
    const originalSetTimeout = window.setTimeout;
    window.setTimeout = function(fn, delay, ...args) {
        const jitter = delay > 100 ? Math.random() * 5 : 0;
        return originalSetTimeout(fn, delay + jitter, ...args);
    };
})();
"""
