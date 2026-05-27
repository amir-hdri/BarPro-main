#!/usr/bin/env python3
"""Extract live UTCMS waybill form fields after authenticated login.

This script logs in to UTCMS, navigates to waybill pages, and stores:
- Page metadata (URL/title)
- All input/select/textarea/button fields
- Best-effort CSS-like locator per field

Output files (default):
- docs/waybill_field_snapshot.json
- docs/waybill_field_snapshot.html
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.automation.auth import UTCMSAuthenticator
from app.core.config import utcms_config


def _build_candidate_waybill_urls() -> list[str]:
    base_url = utcms_config.BASE_URL.rstrip("/")
    candidates = [
        utcms_config.WAYBILL_URL,
        f"{base_url}/barname/Document/HagigiHogugi",
        f"{base_url}/Barname/Document/HagigiHogugi",
        f"{base_url}/Barname/Waybill/Create",
    ]
    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


async def _extract_fields(page) -> list[dict[str, Any]]:
    js = """
    () => {
      const controls = Array.from(document.querySelectorAll('input, select, textarea, button'));
      const out = [];
      for (const element of controls) {
        const tag = element.tagName.toLowerCase();
        const type = (element.getAttribute('type') || '').trim();
        const id = (element.getAttribute('id') || '').trim();
        const name = (element.getAttribute('name') || '').trim();
        const placeholder = (element.getAttribute('placeholder') || '').trim();
        const required = element.hasAttribute('required');
        const disabled = element.hasAttribute('disabled');
        const readonly = element.hasAttribute('readonly');
        const value = (element.value || '').trim();
        const text = ((element.innerText || element.textContent || '') || '').trim().slice(0, 140);
        const classes = (element.getAttribute('class') || '').trim();
        const visible = !!(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
        let label = '';
        if (id) {
          const byFor = document.querySelector(`label[for="${id.replace(/"/g, '\\\\"')}"]`);
          if (byFor) label = (byFor.innerText || byFor.textContent || '').trim();
        }
        if (!label) {
          const nearest = element.closest('label');
          if (nearest) label = (nearest.innerText || nearest.textContent || '').trim();
        }

        let selector = '';
        if (id) selector = `${tag}#${id}`;
        else if (name) selector = `${tag}[name="${name}"]`;
        else if (classes) selector = `${tag}.${classes.split(/\\s+/).filter(Boolean).slice(0, 2).join('.')}`;
        else selector = tag;

        const options = tag === 'select'
          ? Array.from(element.querySelectorAll('option')).map(o => ({
              value: (o.value || '').trim(),
              text: (o.innerText || o.textContent || '').trim(),
              selected: o.selected
            }))
          : [];

        out.push({
          tag, type, id, name, placeholder, required, disabled, readonly,
          value, text, classes, visible, label, selector, options
        });
      }
      return out;
    }
    """
    return await page.evaluate(js)


async def run_snapshot(username: str, password: str, headless: bool, output_json: Path, output_html: Path) -> int:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_html.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        authenticator = UTCMSAuthenticator(page, context)
        login_ok = await authenticator.login(username, password)

        snapshot: dict[str, Any] = {
            "login_url": utcms_config.LOGIN_URL,
            "waybill_url_candidates": _build_candidate_waybill_urls(),
            "login_success": login_ok,
            "auth_error": authenticator.last_error,
            "pages": [],
        }

        if not login_ok:
            snapshot["note"] = "Login failed; waybill fields cannot be fully captured without valid authenticated access."
            output_json.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            output_html.write_text(await page.content(), encoding="utf-8")
            await context.close()
            await browser.close()
            return 1

        for url in _build_candidate_waybill_urls():
            page_item: dict[str, Any] = {"url": url}
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(1.2)
                page_item["final_url"] = page.url
                page_item["title"] = await page.title()
                page_item["fields"] = await _extract_fields(page)
            except Exception as error:
                page_item["error"] = str(error)
            snapshot["pages"].append(page_item)

        output_json.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        output_html.write_text(await page.content(), encoding="utf-8")

        await context.close()
        await browser.close()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture live UTCMS waybill form fields after login")
    parser.add_argument("--username", default="", help="UTCMS username/national code")
    parser.add_argument("--password", default="", help="UTCMS password")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--output-json", default="docs/waybill_field_snapshot.json", help="Path to output JSON")
    parser.add_argument("--output-html", default="docs/waybill_field_snapshot.html", help="Path to output HTML")
    args = parser.parse_args()

    if not args.username or not args.password:
        print("ERROR: username/password are required (use --username/--password explicitly).")
        return 2

    return asyncio.run(
        run_snapshot(
            username=args.username,
            password=args.password,
            headless=args.headless,
            output_json=Path(args.output_json),
            output_html=Path(args.output_html),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
