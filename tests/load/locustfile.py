"""
Locust Load Testing Configuration for BarPro

This file defines load test scenarios for the BarPro application.
Run with: locust -f tests/load/locustfile.py

Usage:
  # Start web UI (http://localhost:8089)
  locust -f tests/load/locustfile.py

  # Run headless test
  locust -f tests/load/locustfile.py --headless -u 100 -r 10 --run-time 5m --host=https://staging.barpro.com

  # Generate HTML report
  locust -f tests/load/locustfile.py --headless -u 100 -r 10 --run-time 5m --host=https://staging.barpro.com --html=report.html
"""

from locust import HttpUser, task, between, TaskSet, SequentialTaskSet
from locust import run_single_user
import random
import string
import json
import os
from datetime import datetime, timedelta


# ============================================================================
# Configuration
# ============================================================================

# Read environment variables for authentication
JWT_TOKEN = os.getenv("JWT_TOKEN", "test-token")
API_KEY = os.getenv("API_KEY", "test-api-key")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Test user credentials (use test users for load testing)
TEST_USERS = [
    {"username": "test_user_1", "password": "test_pass_1"},
    {"username": "test_user_2", "password": "test_pass_2"},
    {"username": "test_user_3", "password": "test_pass_3"},
]


# ============================================================================
# Helper Functions
# ============================================================================

def generate_random_string(length=10):
    """Generate a random string."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_waybill_data():
    """Generate random waybill data for testing."""
    return {
        "origin": f"City {generate_random_string(5)}",
        "destination": f"City {generate_random_string(5)}",
        "driver_id": random.randint(1, 100),
        "vehicle_plate": f"IR{random.randint(10, 99)}{generate_random_string(3)}{random.randint(100, 999)}",
        "weight": random.randint(1, 20),
        "description": f"Test waybill {generate_random_string(20)}",
        "cargo_type": random.choice(["General", "Perishable", "Hazardous", "Fragile"]),
    }


def get_auth_headers(user=None):
    """Get headers with authentication."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Request-ID": generate_random_string(36),
    }
    
    if user and "token" in user:
        headers["Authorization"] = f"Bearer {user['token']}"
    elif JWT_TOKEN:
        headers["Authorization"] = f"Bearer {JWT_TOKEN}"
    
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    
    return headers


# ============================================================================
# Task Sets
# ============================================================================

class HealthCheckTasks(TaskSet):
    """Health check endpoints."""
    
    @task(10)
    def healthz(self):
        self.client.get("/healthz", headers=get_auth_headers())
    
    @task(5)
    def readyz(self):
        self.client.get("/readyz", headers=get_auth_headers())


class AuthenticationTasks(TaskSet):
    """Authentication related tasks."""
    
    def on_start(self):
        """Initialize test user session."""
        # Login to get a token (if not using pre-generated JWT_TOKEN)
        if not JWT_TOKEN:
            user = random.choice(TEST_USERS)
            response = self.client.post(
                "/api/v1/auth/login",
                json={
                    "username": user["username"],
                    "password": user["password"]
                }
            )
            if response.status_code == 200:
                self.user_data = {
                    **user,
                    "token": response.json().get("access_token", "")
                }
            else:
                self.user_data = user
        else:
            self.user_data = {"token": JWT_TOKEN}
    
    @task(3)
    def login(self):
        """Test login endpoint."""
        user = random.choice(TEST_USERS)
        self.client.post(
            "/api/v1/auth/login",
            json={
                "username": user["username"],
                "password": user["password"]
            },
            headers=get_auth_headers()
        )


class WaybillTasks(TaskSet):
    """Waybill related tasks."""
    
    def on_start(self):
        """Initialize user data."""
        self.user_data = {"token": JWT_TOKEN} if JWT_TOKEN else {}
    
    @task(5)
    def list_waybills(self):
        """List waybills."""
        self.client.get(
            "/api/v1/waybills",
            headers=get_auth_headers(self.user_data)
        )
    
    @task(3)
    def create_waybill(self):
        """Create a new waybill."""
        data = generate_waybill_data()
        self.client.post(
            "/api/v1/waybills",
            json=data,
            headers=get_auth_headers(self.user_data)
        )
    
    @task(2)
    def get_waybill(self):
        """Get a specific waybill."""
        # Try to get a random waybill ID
        response = self.client.get(
            "/api/v1/waybills",
            headers=get_auth_headers(self.user_data)
        )
        if response.status_code == 200 and response.json().get("items"):
            waybill_id = random.choice(response.json()["items"])["id"]
            self.client.get(
                f"/api/v1/waybills/{waybill_id}",
                headers=get_auth_headers(self.user_data)
            )
    
    @task(1)
    def update_waybill(self):
        """Update a waybill."""
        response = self.client.get(
            "/api/v1/waybills",
            headers=get_auth_headers(self.user_data)
        )
        if response.status_code == 200 and response.json().get("items"):
            waybill_id = random.choice(response.json()["items"])["id"]
            self.client.put(
                f"/api/v1/waybills/{waybill_id}",
                json={"description": f"Updated at {datetime.now().isoformat()}"},
                headers=get_auth_headers(self.user_data)
            )


class DriverTasks(TaskSet):
    """Driver related tasks."""
    
    def on_start(self):
        """Initialize user data."""
        self.user_data = {"token": JWT_TOKEN} if JWT_TOKEN else {}
    
    @task(3)
    def list_drivers(self):
        """List drivers."""
        self.client.get(
            "/api/v1/drivers",
            headers=get_auth_headers(self.user_data)
        )
    
    @task(2)
    def get_driver(self):
        """Get a specific driver."""
        self.client.get(
            "/api/v1/drivers/1",
            headers=get_auth_headers(self.user_data)
        )


class ReportTasks(TaskSet):
    """Report related tasks."""
    
    def on_start(self):
        """Initialize user data."""
        self.user_data = {"token": JWT_TOKEN} if JWT_TOKEN else {}
    
    @task(2)
    def get_reports(self):
        """Get reports."""
        self.client.get(
            "/api/v1/reports",
            headers=get_auth_headers(self.user_data)
        )
    
    @task(1)
    def get_dashboard_stats(self):
        """Get dashboard statistics."""
        self.client.get(
            "/api/v1/dashboard/stats",
            headers=get_auth_headers(self.user_data)
        )


class RPATasks(TaskSet):
    """RPA automation related tasks."""
    
    def on_start(self):
        """Initialize user data."""
        self.user_data = {"token": JWT_TOKEN} if JWT_TOKEN else {}
    
    @task(2)
    def calculate_route(self):
        """Calculate route for waybill."""
        data = {
            "origin": f"City {generate_random_string(5)}",
            "destination": f"City {generate_random_string(5)}",
        }
        self.client.post(
            "/waybill/calculate-route",
            json=data,
            headers=get_auth_headers(self.user_data)
        )
    
    @task(1)
    def check_rpa_status(self):
        """Check RPA system status."""
        self.client.get(
            "/api/v1/rpa/status",
            headers=get_auth_headers(self.user_data)
        )


# ============================================================================
# User Classes
# ============================================================================

class NormalUser(HttpUser):
    """Simulates a normal user with typical usage patterns."""
    
    wait_time = between(1, 3)
    tasks = [
        HealthCheckTasks,
        WaybillTasks,
        DriverTasks,
        ReportTasks,
    ]


class HeavyUser(HttpUser):
    """Simulates a power user with higher request rates."""
    
    wait_time = between(0.5, 1)
    tasks = [
        WaybillTasks,
        WaybillTasks,
        WaybillTasks,
        DriverTasks,
        ReportTasks,
    ]


class ReadOnlyUser(HttpUser):
    """Simulates a read-only user (viewer, auditor)."""
    
    wait_time = between(2, 5)
    tasks = [
        HealthCheckTasks,
        WaybillTasks,
        DriverTasks,
        ReportTasks,
    ]


class AuthUser(HttpUser):
    """Simulates authentication-heavy usage."""
    
    wait_time = between(1, 2)
    tasks = [
        AuthenticationTasks,
        HealthCheckTasks,
        WaybillTasks,
    ]


# ============================================================================
# Test Scenarios
# ============================================================================

class SmokeTestUser(HttpUser):
    """Lightweight smoke test user."""
    
    wait_time = between(0.5, 1)
    
    @task
    def smoke_test(self):
        self.client.get("/healthz")
        self.client.get("/readyz")
        if JWT_TOKEN:
            self.client.get("/api/v1/waybills", headers=get_auth_headers())


class FullFlowUser(HttpUser):
    """Simulates a complete user flow."""
    
    wait_time = between(1, 3)
    
    @task
    def complete_flow(self):
        # Health check
        self.client.get("/healthz")
        
        # List waybills
        self.client.get("/api/v1/waybills", headers=get_auth_headers())
        
        # Create waybill
        self.client.post(
            "/api/v1/waybills",
            json=generate_waybill_data(),
            headers=get_auth_headers()
        )
        
        # Get reports
        self.client.get("/api/v1/reports", headers=get_auth_headers())
        
        # Calculate route
        self.client.post(
            "/waybill/calculate-route",
            json={
                "origin": "Tehran",
                "destination": "Isfahan"
            },
            headers=get_auth_headers()
        )
