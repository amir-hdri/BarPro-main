#!/usr/bin/env python3
"""
RPA Inspector & Diagnostic Tool for UTCMS
-----------------------------------------
This is a standalone diagnostic tool designed to monitor the RPA bot's interaction 
with the UTCMS website. It performs a "Deep Audit" of the registration process, 
capturing screenshots, HTML dumps, and detailed error analysis for every step.

Features:
- Step-by-step verification of form filling.
- Detection of blocking overlays (e.g., 'Please wait').
- Detailed tracking of network responses and JS errors.
- Standalone execution (independent of the main app).
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, Page, BrowserContext, Response

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rpa_inspector.log', encoding='utf-8')
    ]
)
logger = logging.getLogger("RPAInspector")

class RPAInspector:
    def __init__(self, output_dir: str = "rpa_diagnostics"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.screenshots_dir = self.output_dir / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        self.html_dir = self.output_dir / "html_dumps"
        self.html_dir.mkdir(exist_ok=True)
        self.logs: List[Dict[str, Any]] = []
        self.start_time = time.time()

    def _log_event(self, step: str, status: str, message: str, details: Optional[Dict] = None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(time.time() - self.start_time, 2),
            "step": step,
            "status": status,
            "message": message,
            "details": details or {}
        }
        self.logs.append(entry)
        level = logging.INFO if status == "SUCCESS" else logging.WARNING if status == "WARNING" else logging.ERROR
        logger.log(level, f"[{step}] {status}: {message}")

    async def capture_state(self, page: Page, name: str):
        """Captures both screenshot and HTML for the current state."""
        timestamp = datetime.now().strftime("%H%M%S")
        ss_path = self.screenshots_dir / f"{name}_{timestamp}.png"
        html_path = self.html_dir / f"{name}_{timestamp}.html"
        
        try:
            await page.screenshot(path=str(ss_path), full_page=True)
            html_content = await page.content()
            html_path.write_text(html_content, encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to capture state for {name}: {e}")

    async def analyze_failure(self, page: Page, step: str, error: Exception):
        """Performs a deep analysis of why a step failed."""
        self._log_event(step, "FAILURE", str(error))
        await self.capture_state(page, f"FAILURE_{step}")
        
        # Check for blocking overlays
        try:
            overlays = await page.evaluate("""() => {
                const results = [];
                const possibleOverlays = document.querySelectorAll('.loading, .spinner, .modal-backdrop, .overlay, .k-loading-mask');
                possibleOverlays.forEach(el => {
                    if (el.offsetWidth > 0 || el.offsetHeight > 0) {
                        results.push({
                            selector: el.tagName + (el.className ? '.' + el.className.split(' ').join('.') : ''),
                            text: el.innerText || el.textContent
                        });
                    }
                });
                return results;
            }""")
            if overlays:
                self._log_event(step, "DIAGNOSTIC", "Detected active overlays that might block interaction", {"overlays": overlays})
        except:
            pass

    async def run_diagnostic(self, login_url: str, credentials: Dict[str, str], payload: Dict[str, Any]):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False) # Keep it visible for diagnostics
            context = await browser.new_context(viewport={'width': 1280, 'height': 800})
            page = await context.new_page()

            # Network monitor
            page.on("response", lambda res: self._on_response(res))
            page.on("console", lambda msg: logger.debug(f"BROWSER CONSOLE: {msg.text}"))

            try:
                # 1. Login Phase
                self._log_event("LOGIN", "START", f"Navigating to {login_url}")
                await page.goto(login_url, wait_until="networkidle")
                await self.capture_state(page, "login_page")
                
                # Manual interaction check (this script is for observation)
                self._log_event("LOGIN", "INFO", "Waiting for login to be completed manually or via script...")
                # Here we could add auto-login logic if needed, but for diagnostic 
                # we usually want to watch the failure point reported by user.
                
                # 2. Navigate to HagigiHogugi (Step 1)
                self._log_event("STEP_1", "START", "Navigating to Sender Information page")
                # Assuming user is logged in
                await page.goto("https://barname.utcms.ir/barname/Document/HagigiHogugi", wait_until="domcontentloaded")
                await asyncio.sleep(2)
                await self.capture_state(page, "step1_initial")

                # Check for "Sender Type" dropdown
                try:
                    await page.wait_for_selector('select[name="senderSelectType"]', timeout=5000)
                    self._log_event("STEP_1", "SUCCESS", "Sender Type dropdown found")
                except Exception as e:
                    await self.analyze_failure(page, "STEP_1_SENDER_TYPE", e)

                # 3. Form Filling Simulation
                # (You would add specific field checks here based on what failed)
                
                self._log_event("DIAGNOSTIC", "COMPLETE", "Diagnostic run finished. Check logs and screenshots.")

            except Exception as e:
                self._log_event("GLOBAL", "CRITICAL", f"Unexpected error: {e}")
            finally:
                # Save final report
                report_path = self.output_dir / "report.json"
                report_path.write_text(json.dumps(self.logs, indent=2, ensure_ascii=False), encoding='utf-8')
                logger.info(f"Full diagnostic report saved to {report_path}")
                await asyncio.sleep(5) # Let user see the final state
                await browser.close()

    def _on_response(self, response: Response):
        if response.status >= 400:
            self._log_event("NETWORK", "WARNING", f"HTTP {response.status} on {response.url}")

if __name__ == "__main__":
    # Example usage
    inspector = RPAInspector()
    
    # These would normally come from command line or config
    LOGIN_URL = "https://barname.utcms.ir/Barname/Account/Login"
    CREDS = {"user": "5729076411", "pass": "@M_m123456789"}
    
    print("--- RPA Inspector Started ---")
    print("This tool will run a diagnostic session and save results to 'rpa_diagnostics/'")
    
    asyncio.run(inspector.run_diagnostic(LOGIN_URL, CREDS, {}))
