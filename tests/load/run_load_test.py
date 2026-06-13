#!/usr/bin/env python3
"""
Simple Python Load Test Runner for BarPro

This script provides a simple way to run load tests without Locust.
Useful for quick validation or when Locust is not available.

Usage:
    python tests/load/run_load_test.py --url https://staging.barpro.com --users 100 --duration 300
"""

import argparse
import asyncio
import json
import random
import string
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp


@dataclass
class TestResult:
    """Store test results."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    response_times: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    start_time: float | None = None
    end_time: float | None = None


@dataclass
class TestConfig:
    """Test configuration."""
    url: str
    users: int = 10
    duration: int = 60  # seconds
    spawn_rate: int = 2  # users per second
    endpoints: list = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)


def generate_random_string(length: int = 10) -> str:
    """Generate a random string."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_waybill_data() -> dict[str, Any]:
    """Generate random waybill data."""
    return {
        "origin": f"City {generate_random_string(5)}",
        "destination": f"City {generate_random_string(5)}",
        "driver_id": random.randint(1, 100),
        "vehicle_plate": f"IR{random.randint(10, 99)}{generate_random_string(3)}{random.randint(100, 999)}",
        "weight": random.randint(1, 20),
        "description": f"Test waybill {generate_random_string(20)}",
        "cargo_type": random.choice(["General", "Perishable", "Hazardous", "Fragile"]),
    }


async def make_request(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bool, float, str | None]:
    """Make an HTTP request and return (success, response_time, error)."""
    url = f"{path}"
    start_time = time.time()

    try:
        if method.upper() == "GET":
            async with session.get(url, headers=headers) as response:
                response_time = time.time() - start_time
                if response.status >= 400:
                    error_text = await response.text()
                    return False, response_time, f"HTTP {response.status}: {error_text[:100]}"
                return True, response_time, None

        elif method.upper() == "POST":
            async with session.post(url, json=data, headers=headers) as response:
                response_time = time.time() - start_time
                if response.status >= 400:
                    error_text = await response.text()
                    return False, response_time, f"HTTP {response.status}: {error_text[:100]}"
                return True, response_time, None

        elif method.upper() == "PUT":
            async with session.put(url, json=data, headers=headers) as response:
                response_time = time.time() - start_time
                if response.status >= 400:
                    error_text = await response.text()
                    return False, response_time, f"HTTP {response.status}: {error_text[:100]}"
                return True, response_time, None

        else:
            return False, 0, f"Unsupported method: {method}"

    except Exception as e:
        return False, time.time() - start_time, str(e)


async def user_task(
    user_id: int,
    config: TestConfig,
    result: TestResult,
) -> None:
    """Simulate a user making requests."""
    # Create a session for this user
    connector = aiohttp.TCPConnector(limit_per_host=10)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Define the tasks this user will perform
        tasks = [
            ("GET", f"{config.url}/healthz", None),
            ("GET", f"{config.url}/readyz", None),
            ("GET", f"{config.url}/api/v1/waybills", None),
            ("POST", f"{config.url}/api/v1/waybills", generate_waybill_data()),
            ("POST", f"{config.url}/waybill/calculate-route", {
                "origin": f"City {generate_random_string(5)}",
                "destination": f"City {generate_random_string(5)}",
            }),
        ]

        # Use custom endpoints if provided
        if config.endpoints:
            tasks = []
            for endpoint in config.endpoints:
                method = endpoint.get("method", "GET")
                path = endpoint.get("path", "/")
                data = endpoint.get("data", None)
                tasks.append((method, f"{config.url}{path}", data))

        # Random delay between requests
        await asyncio.sleep(random.uniform(0.1, 0.5))

        # Perform tasks in a loop
        start_time = time.time()
        while time.time() - start_time < config.duration:
            # Randomly select a task
            method, url, data = random.choice(tasks)

            # Make the request
            success, response_time, error = await make_request(
                session, method, url, data, config.headers
            )

            # Update results
            result.total_requests += 1
            if success:
                result.successful_requests += 1
            else:
                result.failed_requests += 1
                if error:
                    result.errors.append(f"User {user_id} - {method} {url}: {error}")

            result.total_response_time += response_time
            result.response_times.append(response_time)

            # Random wait between requests
            await asyncio.sleep(random.uniform(0.5, 2.0))


async def run_load_test(config: TestConfig) -> TestResult:
    """Run the load test."""
    result = TestResult()
    result.start_time = time.time()

    # Print test information
    print(f"\n{'='*60}")
    print("Starting Load Test")
    print(f"{'='*60}")
    print(f"URL: {config.url}")
    print(f"Users: {config.users}")
    print(f"Duration: {config.duration} seconds")
    print(f"Spawn Rate: {config.spawn_rate} users/second")
    print(f"{'='*60}\n")

    # Create user tasks
    tasks = []
    for user_id in range(config.users):
        # Add delay to simulate spawn rate
        if config.spawn_rate > 0:
            delay = user_id / config.spawn_rate
        else:
            delay = 0

        task = asyncio.create_task(
            asyncio.sleep(delay)
        )
        task.add_done_callback(
            lambda _, uid=user_id: asyncio.create_task(user_task(uid, config, result))
        )
        tasks.append(task)

    # Wait for all users to complete
    await asyncio.gather(*tasks, return_exceptions=True)

    result.end_time = time.time()

    return result


def print_report(result: TestResult) -> None:
    """Print the test report."""
    duration = result.end_time - result.start_time if result.end_time and result.start_time else 0

    print(f"\n{'='*60}")
    print("Load Test Report")
    print(f"{'='*60}")
    print(f"Duration: {duration:.2f} seconds")
    print(f"Total Requests: {result.total_requests}")
    print(f"Successful: {result.successful_requests}")
    print(f"Failed: {result.failed_requests}")

    if result.total_requests > 0:
        success_rate = (result.successful_requests / result.total_requests) * 100
        print(f"Success Rate: {success_rate:.2f}%")

    if result.response_times:
        avg_response_time = sum(result.response_times) / len(result.response_times) * 1000
        min_response_time = min(result.response_times) * 1000
        max_response_time = max(result.response_times) * 1000
        print(f"Average Response Time: {avg_response_time:.2f}ms")
        print(f"Min Response Time: {min_response_time:.2f}ms")
        print(f"Max Response Time: {max_response_time:.2f}ms")

    if result.total_requests > 0 and duration > 0:
        rps = result.total_requests / duration
        print(f"Requests Per Second: {rps:.2f}")

    print(f"{'='*60}")

    # Print errors if any
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        print("-" * 60)
        for error in result.errors[:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(result.errors) > 10:
            print(f"  ... and {len(result.errors) - 10} more errors")


def main():
    parser = argparse.ArgumentParser(description="Run load test on BarPro")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL to test")
    parser.add_argument("--users", type=int, default=10, help="Number of concurrent users")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--spawn-rate", type=int, default=2, help="Users to spawn per second")
    parser.add_argument("--token", default="", help="JWT token for authentication")
    parser.add_argument("--api-key", default="", help="API key for authentication")
    parser.add_argument("--endpoints", default="", help="JSON string of endpoints to test")
    parser.add_argument("--output", default="", help="Output file for JSON report")

    args = parser.parse_args()

    # Parse endpoints if provided
    endpoints = []
    if args.endpoints:
        try:
            endpoints = json.loads(args.endpoints)
        except json.JSONDecodeError:
            print("Error: Invalid JSON for --endpoints")
            sys.exit(1)

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    if args.api_key:
        headers["X-API-Key"] = args.api_key

    # Create config
    config = TestConfig(
        url=args.url,
        users=args.users,
        duration=args.duration,
        spawn_rate=args.spawn_rate,
        endpoints=endpoints,
        headers=headers,
    )

    # Run test
    result = asyncio.run(run_load_test(config))

    # Print report
    print_report(result)

    # Save JSON report if requested
    if args.output:
        report = {
            "duration": result.end_time - result.start_time if result.end_time and result.start_time else 0,
            "total_requests": result.total_requests,
            "successful_requests": result.successful_requests,
            "failed_requests": result.failed_requests,
            "success_rate": (result.successful_requests / result.total_requests) * 100 if result.total_requests > 0 else 0,
            "avg_response_time_ms": sum(result.response_times) / len(result.response_times) * 1000 if result.response_times else 0,
            "min_response_time_ms": min(result.response_times) * 1000 if result.response_times else 0,
            "max_response_time_ms": max(result.response_times) * 1000 if result.response_times else 0,
            "requests_per_second": result.total_requests / (result.end_time - result.start_time) if result.end_time and result.start_time and (result.end_time - result.start_time) > 0 else 0,
            "errors": result.errors[:10] if len(result.errors) > 10 else result.errors,
        }
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to {args.output}")

    # Exit with error code if there were failures
    if result.failed_requests > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
