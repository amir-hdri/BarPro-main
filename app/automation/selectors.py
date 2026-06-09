"""
ثابت‌های انتخابگر برای اتوماسیون
"""


class LocationSelectors:
    """الگوهای انتخابگر مکان برای استفاده در LocationSelector

    نکته مهم: سامانه UTCMS از فیلدهای خاص با نام‌های زیر استفاده می‌کند:
    - استان مبدا: ddStateSource  (Origin → Source)
    - شهر مبدا: ddCitySource
    - منطقه مبدا: ddDistrictSource
    - آدرس مبدا: txtAddressSource
    - استان مقصد: ddStateDest  (Destination → Dest)
    - شهر مقصد: ddCityDest
    - آدرس مقصد: txtAddressDest
    """

    # ─── Province / State ───────────────────────────────────────────
    PROVINCE_TEMPLATES = [
        # فرم‌های اختصاصی UTCMS (اولویت بالا)
        'select[id="ddStateSource"]',          # مبدا - UTCMS اصلی
        'select[name="ddStateSource"]',
        'select[id="ddStateDest"]',            # مقصد - UTCMS اصلی
        'select[name="ddStateDest"]',
        # الگوهای عمومی با prefix
        'select[name="{prefix}Province"]',
        'select[name="{prefix}State"]',
        'select[id="{prefix}Province"]',
        'select[id="{prefix}State"]',
        'select[name="ddState{prefix}"]',
        'select[id="ddState{prefix}"]',
        '[id="{prefix_lower}_province"]',
        '[name*="province" i][name*="{prefix_lower}" i]',
        '[name*="state" i][name*="{prefix_lower}" i]',
        # fallback های عمومی
        'select[name*="Ostan"]',
        'select[name*="استان"]',
        'select[id*="State"][id*="Source"]',
        'select[id*="State"][id*="Dest"]',
    ]

    # ─── City ────────────────────────────────────────────────────────
    CITY_TEMPLATES = [
        # فرم‌های اختصاصی UTCMS (اولویت بالا)
        'select[id="ddCitySource"]',           # مبدا - UTCMS اصلی
        'select[name="ddCitySource"]',
        'select[id="ddCityDest"]',             # مقصد - UTCMS اصلی
        'select[name="ddCityDest"]',
        # الگوهای عمومی با prefix
        'select[name="{prefix}City"]',
        'select[id="{prefix}City"]',
        'select[name="ddCity{prefix}"]',
        'select[id="ddCity{prefix}"]',
        '[id="{prefix_lower}_city"]',
        '[name*="city" i][name*="{prefix_lower}" i]',
        # fallback های عمومی
        'select[name*="Shahr"]',
        'select[name*="شهر"]',
        'select[id*="City"][id*="Source"]',
        'select[id*="City"][id*="Dest"]',
    ]

    # ─── District ────────────────────────────────────────────────────
    _DISTRICT_ID = "{prefix_lower}_district"
    DISTRICT_TEMPLATES = [
        # فرم‌های اختصاصی UTCMS
        'select[id="ddDistrictSource"]',
        'select[name="ddDistrictSource"]',
        'select[id="ddDistrictDest"]',
        'select[name="ddDistrictDest"]',
        # الگوهای عمومی
        'select[name="{prefix}District"]',
        'select[id="{prefix}District"]',
        f"#{_DISTRICT_ID}",
        'select[name*="Mantaghe"]',
        'select[name*="منطقه"]',
        'select[id*="District"][id*="Source"]',
        'select[id*="District"][id*="Dest"]',
    ]

    # ─── Address ─────────────────────────────────────────────────────
    ADDRESS_TEMPLATES = [
        # فرم‌های اختصاصی UTCMS (اولویت بالا)
        'textarea[id="txtAddressSource"]',
        'textarea[name="txtAddressSource"]',
        'input[id="txtAddressSource"]',
        'textarea[id="txtAddressDest"]',
        'textarea[name="txtAddressDest"]',
        'input[id="txtAddressDest"]',
        # read-only map fields
        'input[id="txtAddressSourceFromMap"]',
        'input[id="txtAddressDestFromMap"]',
        # الگوهای عمومی با prefix
        'textarea[name="{prefix}Address"]',
        'textarea[id="{prefix}Address"]',
        'input[name="{prefix}Address"]',
        'textarea[name="txtAddress{prefix}"]',
        'textarea[id="txtAddress{prefix}"]',
        'input[name="{prefix}PostalCode"]',
        'input[id="{prefix}PostalCode"]',
        '[name*="address" i][name*="{prefix_lower}" i]',
        '[name*="آدرس"]',
    ]

    # ─── Text / Search inputs ────────────────────────────────────────
    INPUT_TEMPLATES = [
        # UTCMS map search boxes (اولویت بالا)
        '#AddressSearch',
        '#AddressSearch2',
        '#txtAddressSource',
        '#txtAddressDest',
        # الگوهای عمومی
        'input[name="{prefix}Location"]',
        'input[name="{prefix}Address"]',
        'input[name="AddressSearch{prefix}"]',
        'select[name="AddressSearch{prefix}"]',
        'input[name="txtAddress{prefix}"]',
        'textarea[name="txtAddress{prefix}"]',
        'input[placeholder*="{prefix}" i]',
        '[name*="location" i][name*="{prefix_lower}" i]',
        '.location-search',
        '[class*="location-search"]',
        'input[placeholder*="جستجو"]',
        'input[placeholder*="search"]',
    ]

    # ─── Autocomplete suggestions ────────────────────────────────────
    SUGGESTION_SELECTORS = [
        '.autocomplete-suggestion:first-child',
        '.pac-item:first-child',
        '[class*="suggestion"]:first-child',
        '.ui-autocomplete .ui-menu-item:first-child',
        'li.ui-menu-item:first-child',
        'li:first-child',
    ]

    # ─── Map search ──────────────────────────────────────────────────
    MAP_SEARCH_TEMPLATES = [
        # UTCMS map select2 fields
        '#MapCity',
        '#MapCity2',
        '#AddressSearch',
        '#AddressSearch2',
        # الگوهای عمومی
        'input[name="{prefix}Search"]',
        'select[name="MapCity{prefix}"]',
        'select[id="MapCity{prefix}"]',
        'input[name="AddressSearch{prefix}"]',
        'select[name="AddressSearch{prefix}"]',
        'input[placeholder*="{prefix}" i]',
        '.map-search input',
        '[class*="map-search"] input',
        '[id="map-search"]',
        '[id="MapCity"]',
        '[id="MapCity2"]',
        '[id="AddressSearch"]',
        '[id="AddressSearch2"]',
        'input[placeholder*="جستجو در نقشه"]',
        'input[placeholder*="Search map"]',
    ]

    # ─── UTCMS-specific direct selectors (for fast-path access) ──────
    UTCMS_ORIGIN_SELECTORS = {
        "province": ["#ddStateSource", 'select[name="ddStateSource"]'],
        "city":     ["#ddCitySource",  'select[name="ddCitySource"]'],
        "district": ["#ddDistrictSource", 'select[name="ddDistrictSource"]'],
        "address":  ["#txtAddressSource", 'textarea[name="txtAddressSource"]', 'input[name="txtAddressSource"]'],
        "map_address": ["#txtAddressSourceFromMap"],
        "map_city": ["#MapCity"],
        "map_search": ["#AddressSearch"],
        "search_btn": ["#btnsearchAddressSource"],
    }

    UTCMS_DESTINATION_SELECTORS = {
        "province": ["#ddStateDest",  'select[name="ddStateDest"]'],
        "city":     ["#ddCityDest",   'select[name="ddCityDest"]'],
        "district": ["#ddDistrictDest", 'select[name="ddDistrictDest"]'],
        "address":  ["#txtAddressDest", 'textarea[name="txtAddressDest"]', 'input[name="txtAddressDest"]'],
        "map_address": ["#txtAddressDestFromMap"],
        "map_city": ["#MapCity2"],
        "map_search": ["#AddressSearch2"],
        "search_btn": ["#btnsearchAddressDest"],
    }


class AuthSelectors:
    """انتخابگرهای مربوط به احراز هویت"""

    LOGIN_PATH_CANDIDATES = (
        "/Barname/Account/Login",
        "/Account/Login",
        "/Barname/Login",
        "/Login",
    )
    USERNAME_SELECTORS = (
        # UTCMS uses NationalCode for username (priority first)
        "input[name='NationalCode']",
        "input[id='NationalCode']",
        "input[name*='national' i][type='text']",
        "input[name*='National' i][type='text']",
        # Fallback selectors for other systems
        "input[name='Username']",
        "input[name='username']",
        "input[name='UserName']",
        "input[id='Username']",
        "input[id='username']",
        "input[type='text'][name*='user' i]",
        "input[autocomplete='username']",
    )
    PASSWORD_SELECTORS = (
        "input[name='Password']",
        "input[name='password']",
        "input[id='Password']",
        "input[id='password']",
        "input[type='password']",
    )
    CAPTCHA_SELECTORS = (
        "input[name='CapToken']",
        "input[id='CapToken']",
        "input[name='DNTCaptchaInputText']",
        "input[id='DNTCaptchaInputText']",
        "input[name*='captcha' i][type='text']",
        "input[name*='Captcha' i][type='text']",
        "input[name*='SecurityCode' i]",
        "input[id*='captcha' i][type='text']",
    )
    CAPTCHA_IMAGE_SELECTORS = (
        "img[id*='captcha' i]",
        "img[src*='captcha' i]",
        ".captcha img",
        "img.captcha",
        ".dntCaptcha img",
        "#dntCaptchaImg",
        "img[id*='dnt' i][id*='captcha' i]",
    )
    CAPTCHA_REFRESH_SELECTORS = (
        "button[id*='captcha' i][id*='refresh' i]",
        "button[class*='captcha' i][class*='refresh' i]",
        "a[id*='captcha' i][id*='refresh' i]",
        "a[class*='captcha' i][class*='refresh' i]",
        "button[onclick*='captcha' i][onclick*='refresh' i]",
        "a[onclick*='captcha' i][onclick*='refresh' i]",
        "#btnRefreshCaptcha",
        "#refreshCaptcha",
        ".captcha-refresh",
        "#dntCaptchaRefreshButton",
        "a[id*='dnt' i][id*='refresh' i]",
        "button.refresh-captcha",
    )
    SUBMIT_SELECTORS = (
        "button[id='inter']",
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('ورود')",
        "button:has-text('Login')",
        "button:has-text('Sign in')",
    )
    LOGOUT_SELECTORS = (
        "text=خروج",
        "a:has-text('خروج')",
        "a[href*='logout' i]:has-text('خروج')",
        "button:has-text('خروج')",
    )
    AUTHENTICATED_PAGE_MARKERS = (
        "text=اطلاعیه ها",
        "text=سوالات متداول",
        "text=تغییر کلمه عبور",
        "text=بارنامه حقیقی / حقوقی",
        "text=تاریخچه اسناد حمل",
        "text=حمل بارنامه",
        "text=مشاهده سهمیه سوخت",
    )
    WAYBILL_FORM_MARKERS = (
        "input[name='txtSenderFirstName']",
        "input[name='txtReceiverFirstName']",
        "select[name='ddStateSource']",
        "select[name='ddStateDest']",
        "button#btnGoLVL2",
        "input[name='SenderName']",
        "input[name='ReceiverName']",
        "textarea[name='SenderAddress']",
        "textarea[name='ReceiverAddress']",
        "input[name='SenderPhone']",
        "input[name='ReceiverPhone']",
    )
    LOGIN_ERROR_SELECTORS = (
        ".validation-summary-errors li",
        ".validation-summary-errors",
        ".field-validation-error",
        ".alert-danger",
        ".text-danger",
        ".toast-message",
        ".toast-body",
        ".swal2-html-container",
    )
