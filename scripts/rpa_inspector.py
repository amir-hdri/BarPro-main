#!/usr/bin/env python3
"""
RPA Inspector & Diagnostic Tool for UTCMS
-----------------------------------------
This is a comprehensive diagnostic and analysis tool designed to monitor 
and profile the RPA bot's interaction with the UTCMS website. It captures screenshots, 
HTML page dumps, console logs, uncaught JS errors, network requests/responses, latencies, 
and blocking DOM overlays.

Modes:
  --run      Run a single live browser diagnostic session (navigating, elements verification).
  --daemon   Run as a background daemon monitoring both logs and active site health.
  --analyze  Load a previous JSON report and print a complete performance and error audit.
"""

import asyncio
import json
import logging
import os
import sys
import time
import argparse
import signal
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, Page, BrowserContext, Response, Request

# Setup Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rpa_inspector.log', encoding='utf-8')
    ]
)
logger = logging.getLogger("RPAInspector")

# Project directories setup relative to the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "rpa_diagnostics"

class RPAInspector:
    def __init__(self, output_dir: Path = DEFAULT_OUTPUT_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir = self.output_dir / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.html_dir = self.output_dir / "html_dumps"
        self.html_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory session tracking
        self.logs: List[Dict[str, Any]] = []
        self.network_logs: List[Dict[str, Any]] = []
        self.console_logs: List[Dict[str, Any]] = []
        self.js_errors: List[Dict[str, Any]] = []
        self.step_timings: Dict[str, float] = {}
        
        self.start_time = time.time()
        self.request_start_times: Dict[Request, float] = {}
        self.shutdown_event = asyncio.Event()

    def _log_event(self, step: str, status: str, message: str, details: Optional[Dict] = None):
        """Logs an event both to file/stdout and the structured diagnostic output."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(time.time() - self.start_time, 2),
            "step": step,
            "status": status,
            "message": message,
            "details": details or {}
        }
        self.logs.append(entry)
        level = logging.INFO if status in ("SUCCESS", "START", "INFO") else logging.WARNING if status == "WARNING" else logging.ERROR if status == "FAILURE" else logging.DEBUG
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
            self._log_event("DIAGNOSTIC", "INFO", f"Captured state snapshot to {ss_path.name}")
        except Exception as e:
            logger.error(f"Failed to capture state for {name}: {e}")

    async def check_for_overlays(self, page: Page, step: str):
        """Checks if there are any overlays covering the page blocking inputs."""
        try:
            overlays = await page.evaluate("""() => {
                const results = [];
                const selectors = ['.loading', '.spinner', '#loading-mask', '.k-loading-mask', '.modal-backdrop', '.please-wait', '.overlay'];
                selectors.forEach(sel => {
                    const elements = document.querySelectorAll(sel);
                    elements.forEach(el => {
                        const style = window.getComputedStyle(el);
                        const isVisible = el.offsetWidth > 0 && el.offsetHeight > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                        if (isVisible) {
                            results.push({
                                selector: sel,
                                tag: el.tagName,
                                className: el.className,
                                zIndex: style.zIndex,
                                opacity: style.opacity
                            });
                        }
                    });
                });
                return results;
            }""")
            if overlays:
                self._log_event(step, "OVERLAY_DETECTED", "Detected active overlay elements blocking inputs", {"overlays": overlays})
                return overlays
        except Exception as e:
            logger.debug(f"Failed to scan for overlays: {e}")
        return []

    async def diagnose_element(self, page: Page, selector: str, step: str):
        """Deep analysis of an element if Playwright is unable to interact with it."""
        try:
            details = await page.evaluate("""(sel) => {
                const el = document.querySelector(sel);
                if (!el) return { present: false };
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                
                // Check if covered by another element
                let coveredBy = null;
                if (rect.width > 0 && rect.height > 0) {
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    const topEl = document.elementFromPoint(x, y);
                    if (topEl && topEl !== el && !el.contains(topEl)) {
                        coveredBy = topEl.tagName + (topEl.className ? '.' + topEl.className.split(' ').join('.') : '');
                    }
                }

                return {
                    present: true,
                    visible: rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden',
                    disabled: el.disabled || el.getAttribute('disabled') !== null,
                    rect: { x: rect.left, y: rect.top, width: rect.width, height: rect.height },
                    style: {
                        display: style.display,
                        visibility: style.visibility,
                        opacity: style.opacity,
                        zIndex: style.zIndex,
                        pointerEvents: style.pointerEvents
                    },
                    coveredBy: coveredBy,
                    html: el.outerHTML.substring(0, 500)
                };
            }""", selector)
            self._log_event(step, "ELEMENT_DIAGNOSIS", f"Diagnostic report for '{selector}'", {"element": details})
            return details
        except Exception as e:
            self._log_event(step, "ELEMENT_DIAGNOSIS_FAILED", f"Could not audit element '{selector}': {e}")
            return {"error": str(e)}

    async def analyze_failure(self, page: Page, step: str, error: Exception):
        """Performs a deep audit on why an automation step has failed."""
        self._log_event(step, "FAILURE", f"Automation error occurred: {error}")
        await self.capture_state(page, f"FAILURE_{step}")
        await self.check_for_overlays(page, step)

    # Listeners for Network events
    def _on_request(self, request: Request):
        self.request_start_times[request] = time.time()

    async def _on_response(self, response: Response):
        request = response.request
        start_time = self.request_start_times.get(request)
        latency_ms = None
        if start_time:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            del self.request_start_times[request]
        
        # Try capturing response preview
        response_body = ""
        if response.status < 400:
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                try:
                    body_text = await response.text()
                    response_body = body_text[:1200] + "..." if len(body_text) > 1200 else body_text
                except Exception:
                    response_body = "<binary or closed stream>"
        else:
            self._log_event("NETWORK", "WARNING", f"HTTP {response.status} {response.status_text} on {response.url}")
            try:
                response_body = await response.text()
            except Exception:
                response_body = "<failed to read error response text>"

        self.network_logs.append({
            "timestamp": datetime.now().isoformat(),
            "url": response.url,
            "method": request.method,
            "status": response.status,
            "status_text": response.status_text,
            "headers": response.headers,
            "latency_ms": latency_ms,
            "content_length": len(response_body),
            "response_body_sample": response_body
        })

    def _on_console(self, msg: Any):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": msg.type,
            "text": msg.text,
            "location": msg.location
        }
        self.console_logs.append(log_entry)
        if msg.type == "error":
            self._log_event("BROWSER_CONSOLE", "ERROR", f"Browser console error: {msg.text} @ {msg.location}")
        else:
            logger.debug(f"BROWSER CONSOLE: [{msg.type}] {msg.text}")

    def _on_page_error(self, err: Any):
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "message": str(err),
            "stack": getattr(err, "stack", "No stack trace available")
        }
        self.js_errors.append(error_entry)
        self._log_event("PAGE_EXCEPTION", "FAILURE", f"Uncaught Javascript error: {err}")

    # Signal Handling
    def setup_signal_handlers(self):
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
            logger.info("Signal handlers for SIGINT and SIGTERM registered successfully.")
        except NotImplementedError:
            pass

    async def shutdown(self):
        logger.info("Shutdown signal received. Terminating diagnostic loop...")
        self.shutdown_event.set()

    # Log Monitoring (Passive)
    async def _monitor_backend_log(self, file_path: Path):
        """Monitors backend.log for any errors or failures during runtime."""
        logger.info(f"Log monitor thread started targeting: {file_path}")
        position = 0
        if file_path.exists():
            position = file_path.stat().st_size

        while not self.shutdown_event.is_set():
            if not file_path.exists():
                await asyncio.sleep(2)
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(position)
                    lines = f.readlines()
                    position = f.tell()

                    for line in lines:
                        if any(marker in line for marker in ["LocationSelectionError", "WaybillError", "ERROR", "CRITICAL", "failure_bundle"]):
                            self._log_event("BACKEND_LOG", "WARNING", f"Detected backend log warning: {line.strip()[:250]}")
            except Exception as e:
                logger.debug(f"Error reading backend.log: {e}")

            await asyncio.sleep(2)

    # Save final structured report
    def _save_final_report(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"report_{timestamp}.json"
        report_path = self.output_dir / report_filename

        report_data = {
            "execution_summary": {
                "date": datetime.now().isoformat(),
                "total_duration_seconds": round(time.time() - self.start_time, 2),
                "timings_per_phase": self.step_timings
            },
            "events": self.logs,
            "network_requests": self.network_logs,
            "browser_console": self.console_logs,
            "javascript_errors": self.js_errors
        }
        
        report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding='utf-8')
        
        # Save a duplicate at a static endpoint 'latest_report.json'
        latest_path = self.output_dir / "latest_report.json"
        latest_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding='utf-8')
        
        logger.info("="*80)
        logger.info(f"RPA Inspector report compiled successfully.")
        logger.info(f"Structured report file:  {report_path}")
        logger.info(f"Latest report link:      {latest_path}")
        logger.info("="*80)

    # 1. Navigation & elements check
    async def run_diagnostic(self, login_url: str, credentials: Dict[str, str], proxy: Optional[str] = None, headless: bool = False):
        self._log_event("GLOBAL", "START", "Starting Single Diagnostic Run")
        self.start_time = time.time()
        
        async with async_playwright() as p:
            launch_args = {}
            if proxy and proxy != "":
                launch_args["proxy"] = {"server": proxy}
            
            browser = await p.chromium.launch(headless=headless, **launch_args)
            context = await browser.new_context(viewport={'width': 1280, 'height': 800}, ignore_https_errors=True)
            page = await context.new_page()

            # Attach listeners
            page.on("request", self._on_request)
            page.on("response", self._on_response)
            page.on("console", self._on_console)
            page.on("pageerror", self._on_page_error)

            try:
                # 1. Navigation
                phase = "NAVIGATION"
                self.step_timings[phase] = time.time()
                self._log_event(phase, "START", f"Navigating to {login_url}")
                await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
                self.step_timings[phase] = time.time() - self.step_timings[phase]
                self._log_event(phase, "SUCCESS", "Initial login page loaded")
                await self.capture_state(page, "login_page_loaded")

                # 2. Elements verification
                phase = "LOGIN_ELEMENTS"
                self.step_timings[phase] = time.time()
                self._log_event(phase, "START", "Verifying login form elements exist")
                username_selector = "input[name='username'], input[name='Username'], #Username"
                try:
                    await page.wait_for_selector(username_selector, timeout=5000)
                    self._log_event(phase, "SUCCESS", "Username input found in DOM")
                except Exception as e:
                    await self.diagnose_element(page, "input", phase)
                    await self.analyze_failure(page, phase, e)

                if credentials.get("user") and credentials.get("pass"):
                    try:
                        self._log_event(phase, "INFO", "Attempting credentials autofill")
                        await page.fill(username_selector, credentials["user"])
                        password_selector = "input[name='password'], input[name='Password'], #Password"
                        await page.fill(password_selector, credentials["pass"])
                        self._log_event(phase, "SUCCESS", "Credentials typed")
                    except Exception as e:
                        self._log_event(phase, "WARNING", f"Autofill failed: {e}")
                
                self.step_timings[phase] = time.time() - self.step_timings[phase]

                # 3. Observation
                phase = "OBSERVATION"
                self.step_timings[phase] = time.time()
                self._log_event(phase, "START", "Waiting 10 seconds to collect console logs and network traffic...")
                await asyncio.sleep(10)
                self.step_timings[phase] = time.time() - self.step_timings[phase]

                # 4. Form check
                phase = "FORM_PAGES"
                self.step_timings[phase] = time.time()
                self._log_event(phase, "START", "Auditing Waybill form endpoint redirection")
                await page.goto("https://barname.utcms.ir/barname/Document/HagigiHogugi", wait_until="domcontentloaded")
                await asyncio.sleep(2)
                await self.check_for_overlays(page, phase)
                await self.capture_state(page, "form_page_hagigihogugi")
                self.step_timings[phase] = time.time() - self.step_timings[phase]
                
                self._log_event("GLOBAL", "SUCCESS", "Single diagnostic run completed successfully.")
            except Exception as e:
                self._log_event("GLOBAL", "CRITICAL", f"Fatal exception during diagnostic: {e}")
            finally:
                self._save_final_report()
                await browser.close()

    # 2. Daemon mode execution
    async def run_daemon_mode(self, login_url: str, credentials: Dict[str, str], proxy: Optional[str] = None, headless: bool = True, interval_seconds: int = 60):
        self._log_event("GLOBAL", "START", "Starting Continuous RPA Monitoring Daemon")
        self.start_time = time.time()
        self.setup_signal_handlers()

        # Monitor backend.log dynamically
        backend_log_path = PROJECT_ROOT / "backend.log"
        log_monitor_task = asyncio.create_task(self._monitor_backend_log(backend_log_path))

        async with async_playwright() as p:
            launch_args = {}
            if proxy and proxy != "":
                launch_args["proxy"] = {"server": proxy}
            
            browser = None
            try:
                browser = await p.chromium.launch(headless=headless, **launch_args)
            except Exception as e:
                self._log_event("GLOBAL", "CRITICAL", f"Browser launch failed for daemon: {e}")

            iteration = 0
            while not self.shutdown_event.is_set():
                iteration += 1
                self._log_event("DAEMON", "INFO", f"Active health check loop iteration #{iteration}")
                
                if browser:
                    context = None
                    try:
                        context = await browser.new_context(viewport={'width': 1280, 'height': 800}, ignore_https_errors=True)
                        page = await context.new_page()

                        # Attach listeners
                        page.on("request", self._on_request)
                        page.on("response", self._on_response)
                        page.on("console", self._on_console)
                        page.on("pageerror", self._on_page_error)

                        # Check navigation
                        start_time = time.time()
                        await page.goto(login_url, wait_until="domcontentloaded", timeout=25000)
                        latency = time.time() - start_time
                        
                        self._log_event("DAEMON_NAV", "SUCCESS", f"Active navigation ping succeeded in {latency:.2f}s")
                    except Exception as e:
                        self._log_event("DAEMON_NAV", "WARNING", f"Active navigation ping failed: {e}")
                    finally:
                        if context:
                            try:
                                await context.close()
                            except Exception:
                                pass
                
                # Sleep in 1-second chunks to react immediately to termination signals
                for _ in range(interval_seconds):
                    if self.shutdown_event.is_set():
                        break
                    await asyncio.sleep(1)

            # Cleanup browser
            if browser:
                await browser.close()
            
            # Cancel log tailer
            log_monitor_task.cancel()
            try:
                await log_monitor_task
            except asyncio.CancelledError:
                pass

            self._save_final_report()


def analyze_report(report_path: str):
    """Parses a diagnostic report.json file and outputs a formatted performance audit."""
    path = Path(report_path)
    if not path.exists():
        print(f"Error: Report file {report_path} not found.")
        sys.exit(1)

    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        sys.exit(1)

    summary = data.get("execution_summary", {})
    events = data.get("events", [])
    network = data.get("network_requests", [])
    console = data.get("browser_console", [])
    js_errors = data.get("javascript_errors", [])

    print("\n" + "="*80)
    print("                    UTCMS RPA BOT DIAGNOSTIC AUDIT REPORT")
    print("="*80)
    print(f"Report Date:      {summary.get('date', 'Unknown')}")
    print(f"Total Duration:   {summary.get('total_duration_seconds', 0)} seconds")
    print("-"*80)

    # 1. Timing Profiles
    print("\n⏱️  Timing Profile per Phase:")
    timings = summary.get("timings_per_phase", {})
    if timings:
        for phase, duration in timings.items():
            print(f"  - {phase:<18}: {duration:.2f} seconds")
    else:
        print("  No timing profiles recorded.")

    # 2. Critical Failures / Warnings
    failures = [e for e in events if e.get("status") in ("FAILURE", "CRITICAL")]
    warnings = [e for e in events if e.get("status") == "WARNING"]
    overlays = [e for e in events if e.get("status") == "OVERLAY_DETECTED"]
    
    print(f"\n⚠️  Automation Event Metrics:")
    print(f"  - Critical Failures / Crashes: {len(failures)}")
    print(f"  - Event Warnings:             {len(warnings)}")
    print(f"  - Blocking Overlays Detected: {len(overlays)}")

    if failures:
        print("\n❌ Critical Failure Log:")
        for idx, f in enumerate(failures, 1):
            print(f"  {idx}. [{f.get('step')}] {f.get('message')}")
            if f.get("details"):
                print(f"     Details: {json.dumps(f.get('details'))}")

    if overlays:
        print("\n⛔ Overlay Interventions:")
        for idx, o in enumerate(overlays, 1):
            print(f"  {idx}. [{o.get('step')}] elements present: {o.get('details', {}).get('overlays')}")

    # 3. Network Audit
    print("\n🌐 Network Request Audit:")
    print(f"  - Total Network Responses:     {len(network)}")
    
    failed_requests = [n for n in network if n.get("status", 0) >= 400]
    slow_requests = sorted([n for n in network if n.get("latency_ms") is not None], 
                           key=lambda x: x["latency_ms"], reverse=True)[:5]

    print(f"  - Failed HTTP Requests (>=400): {len(failed_requests)}")
    if failed_requests:
        for idx, fr in enumerate(failed_requests, 1):
            print(f"    {idx}. {fr.get('method')} {fr.get('status')} {fr.get('url')}")
            if fr.get("response_body_sample"):
                print(f"       Response Body: {fr.get('response_body_sample')[:150]}")

    print("\n⚡ Top 5 Slowest Network Requests:")
    for idx, sr in enumerate(slow_requests, 1):
        print(f"  {idx}. {sr.get('method')} {sr.get('url')} - {sr.get('latency_ms'):.0f}ms (HTTP {sr.get('status')})")

    # 4. Javascript Console and Exceptions
    print("\n💻 Browser Exceptions & Console Errors:")
    print(f"  - Uncaught page exceptions:  {len(js_errors)}")
    print(f"  - Console error messages:    {len([c for c in console if c.get('type') == 'error'])}")

    if js_errors:
        print("\n🚨 Uncaught Page Javascript Stacktraces:")
        for idx, je in enumerate(js_errors, 1):
            print(f"  {idx}. Exception: {je.get('message')}")
            print(f"     Stack: {je.get('stack')}")

    print("="*80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UTCMS RPA Diagnostic Inspector & Analyzer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true", help="Execute a single live browser diagnostic session")
    group.add_argument("--daemon", action="store_true", help="Run as a continuous monitoring daemon in the background")
    group.add_argument("--analyze", type=str, nargs='?', const=str(DEFAULT_OUTPUT_DIR / "latest_report.json"), 
                       help="Analyze an existing report JSON output file (defaults to latest_report.json)")
    
    parser.add_argument("--user", type=str, default="5729076411", help="UTCMS username")
    parser.add_argument("--password", type=str, default="@M_m123456789", help="UTCMS password")
    parser.add_argument("--proxy", type=str, default=None, help="Proxy address (e.g. http://127.0.0.1:8080)")
    parser.add_argument("--headless", action="store_true", help="Launch Playwright in headless mode")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Diagnostic logs output path")
    parser.add_argument("--interval", type=int, default=60, help="Interval seconds between active daemon health checks")

    args = parser.parse_args()

    if args.run:
        print("--- RPA Inspector: Single Run Started ---")
        inspector = RPAInspector(output_dir=args.output_dir)
        LOGIN_URL = "https://barname.utcms.ir/Barname/Account/Login"
        CREDS = {"user": args.user, "pass": args.password}
        
        asyncio.run(inspector.run_diagnostic(
            login_url=LOGIN_URL,
            credentials=CREDS,
            proxy=args.proxy,
            headless=args.headless
        ))
    elif args.daemon:
        print("--- RPA Inspector: Daemon Mode Started ---")
        inspector = RPAInspector(output_dir=args.output_dir)
        LOGIN_URL = "https://barname.utcms.ir/Barname/Account/Login"
        CREDS = {"user": args.user, "pass": args.password}
        
        try:
            asyncio.run(inspector.run_daemon_mode(
                login_url=LOGIN_URL,
                credentials=CREDS,
                proxy=args.proxy,
                headless=args.headless,
                interval_seconds=args.interval
            ))
        except (KeyboardInterrupt, SystemExit):
            print("Daemon stopped by user request.")
    else:
        # User specified --analyze (either with a custom path or as a flag)
        report_file = args.analyze if args.analyze else str(DEFAULT_OUTPUT_DIR / "latest_report.json")
        analyze_report(report_file)
