
with open("app/automation/location_selector.py") as f:
    content = f.read()

replacement = """(el, rawValue) => {
                    const value = String(rawValue ?? '');
                    if (!el) return false;
                    if ('value' in el) {
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                        if (nativeInputValueSetter) {
                            nativeInputValueSetter.call(el, value);
                        } else {
                            el.value = value;
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }"""

old_payload = """(el, rawValue) => {
                    const value = String(rawValue ?? '');
                    if (!el) return false;
                    if ('value' in el) {
                        el.value = value;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }"""

if old_payload in content:
    content = content.replace(old_payload, replacement)
    with open("app/automation/location_selector.py", "w") as f:
        f.write(content)
    print("Patch applied.")
else:
    print("Old payload not found.")
