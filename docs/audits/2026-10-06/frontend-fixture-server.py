"""Disposable synthetic API + reverse proxy for CUA UI checks; no production I/O.

NEXT_PUBLIC_API_URL=/api production build must be served at localhost:3126.
This fixture listens at :3127, returns only invented identities, and forwards
non-API requests only to that local Next server. Stop after verification.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from time import sleep
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

GEOCODE_SCENARIO = Path(__file__).with_name("frontend-geocode-scenario.json")
GEOCODE_LOCK = Lock()


class Fixture(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        path = urlsplit(self.path).path
        params = {key: value[0] for key, value in parse_qs(urlsplit(self.path).query).items()}
        if not path.startswith("/api/") and not path.startswith("/shipping/"):
            request = Request("http://127.0.0.1:3126" + self.path, data=body if body else None,
                              headers={k: v for k, v in self.headers.items() if k.lower() not in {"host", "connection", "accept-encoding"}}, method=self.command)
            try:
                response = urlopen(request, timeout=15)
            except HTTPError as error:
                response = error
            content = response.read()
            self.send_response(response.status)
            for key, value in response.headers.items():
                if key.lower() not in {"connection", "transfer-encoding", "content-length", "content-encoding"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        account = cookies["audit_account"].value if "audit_account" in cookies else "A"
        data = {}
        response_cookies = []
        if path.endswith("/auth/login"):
            account = "B" if json.loads(body).get("email", "").startswith("b") else "A"
            response_cookies = ["utcms_auth_token=audit-fixture; Path=/; HttpOnly; SameSite=Lax", f"audit_account={account}; Path=/; HttpOnly; SameSite=Lax"]
            data = {"client": {"id": 101 if account == "A" else 202, "name": "Audit Tenant " + account, "email": account.lower() + "@example.test", "client_code": "audit-" + account}}
        elif path.endswith("/auth/logout"):
            response_cookies = ["utcms_auth_token=; Max-Age=0; Path=/; HttpOnly"]
            data = {"success": True}
        elif path.endswith("/drivers"):
            data = [{"id": 101 if account == "A" else 202, "client_id": 101 if account == "A" else 202, "driver_national_code": "1234567891", "full_name": "Audit Driver " + account, "phone": "09120000000", "license_number": None, "utcms_username": "fixture", "status": "active", "created_at": "2026-10-06T00:00:00Z", "updated_at": "2026-10-06T00:00:00Z"}]
            if account == "B":
                data.append({**data[0], "id": 303, "driver_national_code": "9876543210"})
        elif path.endswith("/fuel-inquiries") or path.endswith("/waybill-jobs"):
            driver_id = 101 if account == "A" else 202
            records = []
            for index in range(25):
                timestamp = "2026-10-05T20:29:59Z" if index == 24 else "2026-10-06T08:00:00Z"
                records.append({"id": index + 1, "driver_id": driver_id, "driver_name": "Audit Driver " + account, "client_id": driver_id, "plate_number": "12ع345ایران67", "status": "failed", "created_at": timestamp, "updated_at": timestamp, "year": 1405, "month": 7, "error_message": "Synthetic fixture record", "job_id": f"fixture-{index + 1}", "priority": 5, "attempt_count": 0, "source": "audit_fixture", "max_retries": 3, "payload_json": {}, "result_json": {}, "plate_source": "request_snapshot", "driver_name_source": "request_snapshot"})
            records.append({**records[0], "id": 26, "job_id": "fixture-26", "created_at": "2026-10-05T20:30:00Z", "updated_at": "2026-10-05T20:30:00Z"})
            if path.endswith("/waybill-jobs"):
                records[-1].update({"status": "success", "payload_json": {"origin": "تهران", "destination": "تهران", "originLat": 35.6892, "originLng": 51.389, "destLat": 35.70, "destLng": 51.40}, "result_json": {"tracking_code": "00000026", "document_id": "26"}})
            if account == "B":
                records.append({**records[0], "id": 27, "job_id": "fixture-27", "driver_id": 303})
            if params.get("driver_id"):
                records = [item for item in records if str(item["driver_id"]) == params["driver_id"]]
            if params.get("status"):
                records = [item for item in records if item["status"] == params["status"]]
            if params.get("date_from"):
                boundary = datetime.fromisoformat(params["date_from"]) - timedelta(hours=3, minutes=30)
                records = [item for item in records if datetime.fromisoformat(item["created_at"].rstrip("Z")) >= boundary]
            if params.get("date_to"):
                boundary = datetime.fromisoformat(params["date_to"]) + timedelta(days=1, hours=-3, minutes=-30)
                records = [item for item in records if datetime.fromisoformat(item["created_at"].rstrip("Z")) < boundary]
            records.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
            page, page_size = int(params.get("page", 1)), int(params.get("page_size", 20))
            key = "items" if path.endswith("/fuel-inquiries") else "tasks"
            data = {key: records[(page - 1) * page_size:page * page_size], "total": len(records), "page": page, "page_size": page_size, "total_pages": (len(records) + page_size - 1) // page_size}
        elif path.endswith("/timeline"):
            data = {"job_id": path.split("/")[-2], "entries": [], "total": 0, "page": 1, "page_size": 50}
        elif path.startswith("/shipping/status/"):
            data = {"status": "delivered", "origin": {"lat": 35.6892, "lng": 51.389, "address": '<img src=x onerror="window.__barproAuditXss=1">'}, "destination": {"lat": 35.70, "lng": 51.40, "address": "مقصد آزمایشی"}, "distance_km": 2, "traveled_km": 2, "progress_pct": 100, "current_step": 1, "total_steps": 1, "waypoints": [{"lat": 35.6892, "lon": 51.389, "speed": 0, "cum_km": 0, "type": 2, "ts": "2026-10-06T08:00:00Z"}, {"lat": 35.70, "lon": 51.40, "speed": 0, "cum_km": 2, "type": 3, "ts": "2026-10-06T09:00:00Z"}], "gps_list": [], "route_source": "simulation", "is_real_route": False}
        elif "/otp/forwarder-config/" in path:
            data = {"driver_id": int(path.rsplit("/", 1)[1]), "driver_phone": "09120000000", "webhook_path": "/api/v1/otp/sms-forwarder/09120000000", "token_configured": False, "storage_ready": True, "intake_ready": False, "required_header_name": "X-OTP-Webhook-Token", "authentication_instructions": "Operator setup required", "forwarder_connection_verified": False}
        elif path.endswith("/driver-tracking"):
            data = {"period": {"phase": 2, "label": "دوره آزمایشی", "start_jalali": "1405/07/16", "end_jalali": "1405/07/30", "start_at": "2026-10-06T20:30:00Z", "end_at": "2026-10-21T20:30:00Z"}, "items": []}
        elif path.endswith("/locations/provinces"):
            data = [{"name": "تهران", "capital": "تهران", "lat": 35.6892, "lng": 51.389, "cities_count": 1}]
        elif path.endswith("/locations/cities"):
            data = [{"name": "تهران", "lat": 35.6892, "lng": 51.389}]
        elif path.endswith("/locations/reverse-geocode"):
            scenario = {}
            with GEOCODE_LOCK:
                if GEOCODE_SCENARIO.exists():
                    sequence = json.loads(GEOCODE_SCENARIO.read_text())
                    if sequence:
                        scenario = sequence.pop(0)
                        GEOCODE_SCENARIO.write_text(json.dumps(sequence))
            if scenario.get("delay"):
                sleep(scenario["delay"])
            data = {"success": scenario.get("success", True), "province": "تهران", "city": "تهران", "district": "بخش آزمایشی", "address": scenario.get("address", "نشانی آزمایشی انتخاب پین"), "is_approximate": False}
        elif path.endswith("/plates"):
            driver_id = 101 if account == "A" else 202
            data = [{"id": 1, "client_id": driver_id, "driver_id": driver_id, "plate_number": "12ع345ایران67", "vehicle_type": "کامیون", "status": "active", "notes": None, "created_at": "2026-10-06T00:00:00Z", "updated_at": "2026-10-06T00:00:00Z"}]
        elif path.endswith("/driver-schedules"):
            data = []
        elif path.endswith("/auth/stats"):
            data = {"client_id": 101 if account == "A" else 202, "total_drivers": 1, "active_drivers": 1, "total_jobs": 0, "pending_jobs": 0, "in_progress_jobs": 0, "success_jobs": 0, "failed_jobs": 0, "today_jobs": 0, "today_success": 0, "today_failed": 0, "success_rate": 0}
        else:
            data = {"items": [], "tasks": [], "drivers": [], "total": 0}
        print(json.dumps({"method": self.command, "path": path, "params": params, "account": account}), flush=True)
        content = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        for cookie in response_cookies:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


class FixtureServer(ThreadingHTTPServer):
    request_queue_size = 128


FixtureServer(("0.0.0.0", 3127), Fixture).serve_forever()
