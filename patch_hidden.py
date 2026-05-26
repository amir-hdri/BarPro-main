import re

with open("app/automation/location_selector.py") as f:
    content = f.read()

replacement = """    async def _fill_coordinate_hidden_fields(self, lat: float, lng: float, prefix: str) -> bool:
        \"\"\"
        تلاش برای یافتن و پر کردن hidden fields مربوط به مختصات
        \"\"\"
        hidden_selectors = [
            f'input[name="{prefix}Lat"]',
            f'input[name="{prefix}Lng"]',
            f'input[name="{prefix}Latitude"]',
            f'input[name="{prefix}Longitude"]',
            f'input[id="{prefix.lower()}_lat"]',
            f'input[id="{prefix.lower()}_lng"]',
            f'input[name*="Coordinate"][name*="{prefix.lower()}"]',
            'input[name*="lat"]',
            'input[name*="lng"]',
            'input[id*="lat"]',
            'input[id*="lng"]',
        ]"""

old_pattern = r"""    async def _fill_coordinate_hidden_fields\(self, lat: float, lng: float, prefix: str\) -> bool:
        \"\"\"
        تلاش برای یافتن و پر کردن hidden fields مربوط به مختصات
        \"\"\"
        hidden_selectors = \[
            f'input\[name="\{prefix\}Lat"\]',
            f'input\[name="\{prefix\}Lng"\]',
            f'input\[name="\{prefix\}Latitude"\]',
            f'input\[name="\{prefix\}Longitude"\]',
            f'input\[id="\{prefix.lower\(\)\}_lat"\]',
            f'input\[id="\{prefix.lower\(\)\}_lng"\]',
            f'input\[name\*="Coordinate"\]\[name\*="\{prefix.lower\(\)\}"\]',
        \]"""

match = re.search(old_pattern, content, re.MULTILINE)
if match:
    new_content = content[:match.start()] + replacement + content[match.end():]
    with open("app/automation/location_selector.py", "w") as f:
        f.write(new_content)
    print("Patch applied.")
else:
    print("Pattern not found!")
