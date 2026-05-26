# Anti-Detection Automation System

## 🎯 Overview

Complete enterprise-grade anti-detection browser automation system with:

- ✅ **Browser Fingerprint Management** - Realistic, consistent fingerprints
- ✅ **Proxy Rotation** - Health monitoring, latency tracking, intelligent rotation
- ✅ **HTTP Header Building** - Fingerprint-consistent, browser-specific headers
- ✅ **Human Behavior Simulation** - Typing, mouse movement, timing patterns
- ✅ **Stealth Browser** - Playwright stealth with advanced evasion techniques
- ✅ **WAF Bypass** - Cloudflare, Imperva, and custom WAF detection & handling

---

## 📁 Project Structure

```
app/automation/
├── config/
│   └── __init__.py           # Configuration profiles & data classes
├── proxy_rotator.py          # Proxy rotation with health checks
├── header_builder.py         # HTTP header builder
├── stealth.py                # Core stealth scripts
├── stealth_advanced.py       # Advanced WAF bypass
├── human_interaction.py      # Human behavior simulation
├── browser.py                # Browser management
├── browser_pool.py           # Browser pool & session management
├── __init__.py               # Package exports
└── README.md                 # This file
```

---

## 🚀 Quick Start

### Installation

```bash
pip install playwright
playwright install chromium
```

### Basic Usage

```python
import asyncio
from app.automation import (
    BrowserManager,
    apply_stealth_mode,
    human_type,
    click_with_human_movement,
)

async def main():
    # Initialize browser
    browser_manager = BrowserManager()
    await browser_manager.initialize()
    
    # Create context and page
    session_id, context = await browser_manager.create_context()
    page = await browser_manager.new_page(context)
    
    # Apply stealth
    await apply_stealth_mode(page)
    
    # Navigate
    await page.goto("https://example.com")
    
    # Human-like interaction
    await human_type(page, "input[name='username']", "testuser")
    await click_with_human_movement(page, "button[type='submit']")
    
    # Cleanup
    await browser_manager.close_context(session_id)

asyncio.run(main())
```

---

## 📚 Module Documentation

### 1. Configuration Profiles (`config/__init__.py`)

Browser fingerprint profiles and settings:

```python
from app.automation.config import (
    USER_AGENT_PROFILES,  # Realistic user agents
    GPU_PROFILES,         # WebGL fingerprints
    SCREEN_PRESETS,       # Screen resolutions
    TIMEZONE_PROFILES,    # Timezones
    LOCALE_PROFILES,      # Language/locale settings
    BrowserProfile,       # Complete profile dataclass
)

# Use a profile
profile = USER_AGENT_PROFILES[0]
print(f"UA: {profile['user_agent']}")
```

### 2. Proxy Rotator (`proxy_rotator.py`)

Advanced proxy management with health monitoring:

```python
from app.automation import (
    ProxyRotator,
    ProxyInfo,
    get_proxy_rotator,
    test_proxy,
)

# Create rotator
rotator = ProxyRotator(cooldown=5.0, timeout=10.0)

# Load proxies
rotator.load_from_list([
    "http://proxy1.com:8080",
    "socks5://proxy2.com:1080",
])

# Get next proxy (intelligent rotation)
proxy = await rotator.get_next()

# Health check
await rotator.check_all()

# Stats
stats = rotator.get_stats()
print(f"Healthy: {stats['healthy_proxies']}/{stats['total_proxies']}")
```

**Features:**
- ✅ Automatic health checking
- ✅ Latency tracking
- ✅ Success rate monitoring
- ✅ Country/region filtering
- ✅ Cooldown management
- ✅ Persistent state (save/load)

### 3. Header Builder (`header_builder.py`)

Build realistic HTTP headers based on fingerprint:

```python
from app.automation import HeaderBuilder, get_header_builder

builder = get_header_builder()

# Build navigation headers
headers = builder.build(
    user_agent="Chrome/124.0",
    platform="Win32",
    language="en-US",
    referer="",
)

# Build API headers
api_headers = builder.build_api_headers(
    user_agent="Chrome/124.0",
    content_type="application/json",
)

# Validate consistency
warnings = builder.validate_consistency(headers)
```

**Features:**
- ✅ Fingerprint-consistent headers
- ✅ Browser-specific (Chrome, Firefox, Edge, Safari)
- ✅ Sec-* headers for modern browsers
- ✅ Accept header variants
- ✅ Header consistency validation

### 4. Human Interaction (`human_interaction.py`)

Simulate realistic human behavior:

```python
from app.automation import (
    human_type,
    click_with_human_movement,
    wait_like_human,
    TypingProfile,
    HumanTiming,
    HumanTypeConfig,
)

# Human-like typing with delays
await human_type(
    page=page,
    selector="input[name='username']",
    text="testuser",
    config=HumanTypeConfig(profile=TypingProfile.AVERAGE, add_typos=False),
)

# Human-like mouse movement
await click_with_human_movement(
    page=page,
    selector="button.submit",
    wait_for_navigation=True,
)

# Random delay (like human thinking)
await wait_like_human(min_seconds=1.0, max_seconds=3.0)
```

**Features:**
- ✅ Variable typing speeds
- ✅ Punctuation delays
- ✅ Random hesitations
- ✅ Bezier curve mouse movement
- ✅ Action-specific delays

### 5. Stealth Browser (`stealth.py`, `stealth_advanced.py`)

Anti-detection scripts and WAF bypass:

```python
from app.automation import (
    apply_stealth_mode,
    detect_waf,
    handle_cloudflare_challenge,
)

# Apply stealth to page
await apply_stealth_mode(page)

# Detect WAF
waf_type = await detect_waf(page)
print(f"WAF: {waf_type}")

# Handle Cloudflare challenge
if waf_type == "cloudflare":
    success = await handle_cloudflare_challenge(page)
```

**Features:**
- ✅ Remove `navigator.webdriver`
- ✅ WebGL spoofing
- ✅ Canvas noise
- ✅ AudioContext fingerprint noise
- ✅ WAF detection & bypass
- ✅ Cloudflare Turnstile handling

---

## 🎨 Advanced Features

### Browser Pool Management

```python
from app.automation import BrowserPool

# Create pool
pool = BrowserPool(size=5)
await pool.start(browser, context_args={...})

# Get pooled session
session = await pool.get_session()
page = session.page

# Return to pool
await pool.return_session(session)
```

### Custom Fingerprint

```python
from app.automation.config import BrowserProfile, ScreenFingerprint, WebGLFingerprint

# Create custom fingerprint
screen = ScreenFingerprint(width=1920, height=1080, pixel_ratio=1.5)
webgl = WebGLFingerprint(
    vendor="Google Inc. (NVIDIA)",
    renderer="ANGLE (NVIDIA, RTX 3070...)"
)

profile = BrowserProfile(
    name="custom",
    user_agent="Mozilla/5.0...",
    platform="Win32",
    screen=screen,
    webgl=webgl,
    hardware_concurrency=8,
    device_memory=16,
)

# Use profile
fp_hash = profile.fingerprint_hash()
```

### Proxy Persistence

```python
# Save proxy state
rotator.save_to_file("proxies.json")

# Load proxy state
rotator.load_from_file_state("proxies.json")

# Clear failed proxies
rotator.clear_failed()
```

---

## 🧪 Testing

Run integration tests:

```bash
pytest tests/test_anti_detection_integration.py -v
```

Expected output:
```
30 passed in 0.25s
```

---

## 📊 Performance

| Feature | Metric |
|---------|--------|
| Proxy Health Check | ~10 concurrent checks |
| Header Building | <1ms per request |
| Stealth Script Injection | ~5-10ms |
| Human Delay (avg) | 1.5s |
| Browser Startup | ~2-3s |

---

## 🔒 Security Best Practices

1. **Rotate proxies regularly** - Don't use same proxy for too long
2. **Enable health checks** - Monitor proxy quality
3. **Use realistic fingerprints** - Mix user agents, screens, timezones
4. **Add human delays** - Never automate at machine speed
5. **Monitor success rates** - Track and adjust based on detection
6. **Use session cookies** - Maintain consistent sessions
7. **Validate headers** - Check for inconsistencies

---

## 🛠️ Troubleshooting

### Common Issues

**Issue:** "navigator.webdriver detected"
- **Solution:** Ensure `apply_stealth_mode(page)` is called before navigation

**Issue:** Proxies failing health checks
- **Solution:** Verify proxy URLs, check credentials, test manually

**Issue:** Headers inconsistent
- **Solution:** Use `validate_consistency()` to check

**Issue:** Element not found
- **Solution:** Add human delays, check selectors, wait for element

---

## 📈 Roadmap

- [ ] Add Tor support
- [ ] Mobile fingerprints (iOS/Android)
- [ ] TLS fingerprinting (JA3)
- [ ] Machine learning-based detection avoidance
- [ ] Distributed proxy network integration
- [ ] Real-time WAF signature detection

---

## 📝 License

Part of Automation-Barname project.

---

## 🤝 Contributing

Contributions welcome! Please:
1. Follow existing code style
2. Add tests for new features
3. Update documentation
4. Run all tests before PR

---

## 📞 Support

For issues and questions:
- Check existing tests for examples
- Review README sections above
- Examine example code in `/examples/`
