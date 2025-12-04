#!/usr/bin/env python3
"""
Integration test runner for message throttling functionality.

This script runs the throttling integration test against already-running docker containers.

Assumes the following containers are already running:
- sb-emulator (Azure Service Bus emulator)
- mpi-hl7-sender (HL7 sender with throttling enabled)
- mpi-hl7-mock-receiver (Mock HL7 receiver for ACKs)

Usage:
    python run_integration_test.py
"""

import re
import sys
import time
from datetime import datetime
from pathlib import Path

EXPECTED_SERVICES = [
    "sb-emulator",
    "mpi-hl7-sender",
    "mpi-hl7-mock-receiver"
]


def run_command(cmd: list[str], cwd: Path = None) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    import subprocess
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        print("Command timed out")
        return -1, "", "Command timed out"


def check_containers_running(services: list[str]) -> bool:
    """Check if expected containers are running."""
    import subprocess

    print(f"Checking for running containers: {', '.join(services)}")

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "table {{.Names}}"],
            capture_output=True,
            text=True
        )

        running_containers = result.stdout.strip().split('\n')[1:]
        running_services = [line.strip() for line in running_containers if line.strip()]

        missing_services = [service for service in services if service not in running_services]

        if missing_services:
            print(f"Missing required containers: {', '.join(missing_services)}")
            print(f"Running containers: {running_services}")
            return False

        print("All required containers are running")
        return True

    except Exception as e:
        print(f"Error checking container status: {e}")
        return False


def get_actual_timing_from_logs() -> dict:
    """Parse container logs to get actual message timing from the most recent test run."""
    import subprocess
    result = subprocess.run(
        ["docker", "logs", "mpi-hl7-sender", "-t", "--since", "5m"],
        capture_output=True,
        text=True
    )
    logs = result.stdout + result.stderr

    pattern = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)Z.*Sent message: THROTTLE_TEST_(\d+)"
    matches = re.findall(pattern, logs)

    if len(matches) < 2:
        return {}

    all_entries = []
    for ts_str, msg_num in matches:
        ts = datetime.fromisoformat(ts_str)
        all_entries.append((int(msg_num), ts))

    # Find the last occurrence of message 000 (start of most recent test run)
    last_start_idx = -1
    for i, (msg_num, _) in enumerate(all_entries):
        if msg_num == 0:
            last_start_idx = i

    if last_start_idx < 0:
        return {}

    # Get only messages from the most recent test run
    timestamps = all_entries[last_start_idx:]
    timestamps.sort(key=lambda x: x[0])

    first_ts = timestamps[0][1]
    last_ts = timestamps[-1][1]
    total_seconds = (last_ts - first_ts).total_seconds()
    message_count = len(timestamps)

    if total_seconds > 0:
        actual_rate = (message_count - 1) / total_seconds * 60
    else:
        actual_rate = 0

    intervals = []
    for i in range(1, len(timestamps)):
        interval = (timestamps[i][1] - timestamps[i - 1][1]).total_seconds()
        intervals.append(interval)

    avg_interval = sum(intervals) / len(intervals) if intervals else 0

    return {
        "message_count": message_count,
        "total_seconds": total_seconds,
        "actual_rate": actual_rate,
        "avg_interval": avg_interval,
        "first_timestamp": first_ts.isoformat(),
        "last_timestamp": last_ts.isoformat(),
    }


def main() -> int:
    """Main test runner function."""

    if not check_containers_running(EXPECTED_SERVICES):
        print("Required containers are not running. Please start them first:")
        print("  cd local")
        print("  docker compose --profile phw-to-mpi up -d sb-emulator mpi-hl7-sender mpi-hl7-mock-receiver")
        return 1

    print("Waiting for services to be ready...")
    time.sleep(5)

    print("Running integration test inside mpi-hl7-sender container...")
    project_root = Path(__file__).parent.parent.parent

    copy_cmd = [
        "docker", "cp",
        str(project_root / "hl7_sender" / "tests" / "test_throttling_local.py"),
        "mpi-hl7-sender:/app/test_throttling_local.py"
    ]

    copy_exit, copy_stdout, copy_stderr = run_command(copy_cmd, project_root)
    if copy_exit != 0:
        print(f"Failed to copy test file to container: {copy_stderr}")
        return 1

    test_cmd = [
        "docker", "exec", "mpi-hl7-sender",
        "python", "/app/test_throttling_local.py"
    ]

    test_exit_code, test_stdout, test_stderr = run_command(test_cmd, project_root)

    cleanup_cmd = [
        "docker", "exec", "mpi-hl7-sender",
        "rm", "-f", "/app/test_throttling_local.py"
    ]
    run_command(cleanup_cmd, project_root)

    print("Test STDOUT:")
    print(test_stdout)
    if test_stderr:
        print("Test STDERR:")
        print(test_stderr)

    timing = get_actual_timing_from_logs()
    if timing:
        print("\n" + "=" * 60)
        print("ACTUAL MEASURED RESULTS (from container logs):")
        print("=" * 60)
        print(f"  Messages processed: {timing['message_count']}")
        print(f"  Processing time: {timing['total_seconds']:.2f} seconds")
        print(f"  Actual rate: {timing['actual_rate']:.2f} messages/minute")
        print(f"  Average interval: {timing['avg_interval']:.2f} seconds")
        print(f"  First message: {timing['first_timestamp']}")
        print(f"  Last message: {timing['last_timestamp']}")
        print("=" * 60)

    return test_exit_code


if __name__ == "__main__":
    sys.exit(main())
