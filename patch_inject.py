import re

with open("app/automation/location_selector.py") as f:
    content = f.read()

replacement = """        injection_script = f\"\"\"
        () => {{
            const lat = {lat};
            const lng = {lng};
            const prefix = "{prefix.lower()}";

            // جستجو برای input های hidden
            const inputs = document.querySelectorAll('input[type="hidden"]');
            let found = false;

            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;

            inputs.forEach(input => {{
                const name = (input.name || '').toLowerCase();
                const id = (input.id || '').toLowerCase();

                if ((name.includes('lat') || id.includes('lat')) &&
                    (name.includes(prefix) || id.includes(prefix) ||
                     name.includes('origin') || name.includes('source') ||
                     name.includes('dest') || name.includes('magsad'))) {{
                    if (nativeInputValueSetter) {{
                        nativeInputValueSetter.call(input, lat);
                    }} else {{
                        input.value = lat;
                    }}
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    found = true;
                }}
                if ((name.includes('lng') || name.includes('lon') ||
                     id.includes('lng') || id.includes('lon')) &&
                    (name.includes(prefix) || id.includes(prefix) ||
                     name.includes('origin') || name.includes('source') ||
                     name.includes('dest') || name.includes('magsad'))) {{
                    if (nativeInputValueSetter) {{
                        nativeInputValueSetter.call(input, lng);
                    }} else {{
                        input.value = lng;
                    }}
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    found = true;
                }}
            }});

            return found;
        }}
        \"\"\""""

old_pattern = r"""        injection_script = f\"\"\"
        \(\) => \{\{
            const lat = \{lat\};
            const lng = \{lng\};
            const prefix = "\{prefix\.lower\(\)\}";

            // جستجو برای input های hidden
            const inputs = document\.querySelectorAll\('input\[type="hidden"\]'\);
            let found = false;

            inputs\.forEach\(input => \{\{
                const name = \(input\.name \|\| ''\)\.toLowerCase\(\);
                const id = \(input\.id \|\| ''\)\.toLowerCase\(\);

                if \(\(name\.includes\('lat'\) \|\| id\.includes\('lat'\)\) &&
                    \(name\.includes\(\{?prefix\}?\) \|\| id\.includes\(\{?prefix\}?\) \|\|
                     name\.includes\('origin'\) \|\| name\.includes\('source'\) \|\|
                     name\.includes\('dest'\) \|\| name\.includes\('magsad'\)\)\) \{\{
                    input\.value = lat;
                    input\.dispatchEvent\(new Event\('change', \{\{ bubbles: true \}\}\)\);
                    found = true;
                \}\}
                if \(\(name\.includes\('lng'\) \|\| name\.includes\('lon'\) \|\|
                     id\.includes\('lng'\) \|\| id\.includes\('lon'\)\) &&
                    \(name\.includes\(\{?prefix\}?\) \|\| id\.includes\(\{?prefix\}?\) \|\|
                     name\.includes\('origin'\) \|\| name\.includes\('source'\) \|\|
                     name\.includes\('dest'\) \|\| name\.includes\('magsad'\)\)\) \{\{
                    input\.value = lng;
                    input\.dispatchEvent\(new Event\('change', \{\{ bubbles: true \}\}\)\);
                    found = true;
                \}\}
            \}\}\);

            return found;
        \}\}
        \"\"\""""

match = re.search(old_pattern, content, re.MULTILINE)
if match:
    new_content = content[:match.start()] + replacement + content[match.end():]
    with open("app/automation/location_selector.py", "w") as f:
        f.write(new_content)
    print("Patch applied.")
else:
    print("Pattern not found, trying exact string match...")
