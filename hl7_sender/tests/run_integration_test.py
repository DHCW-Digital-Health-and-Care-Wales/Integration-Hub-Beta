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

import sys
import time
from pathlib import Path

# Services that should be running
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
            timeout=300  # 5 minute timeout
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
        # Check if all required containers are running
        result = subprocess.run(
            ["docker", "ps", "--format", "table {{.Names}}"],
            capture_output=True,
            text=True
        )

        running_containers = result.stdout.strip().split('\n')[1:]  # Skip header
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

def main() -> int:
    """Main test runner function."""

    # Check if required containers are running
    if not check_containers_running(EXPECTED_SERVICES):
        print("Required containers are not running. Please start them first:")
        print("  cd local")
        print("  docker compose --profile phw-to-mpi up -d sb-emulator mpi-hl7-sender mpi-hl7-mock-receiver")
        return 1

    # Give containers a moment to be fully ready
    print("Waiting for services to be ready...")
    time.sleep(5)

    # Copy test file to container and run it
    print("Running integration test inside mpi-hl7-sender container...")
    project_root = Path(__file__).parent.parent.parent

    # Copy test file to container
    copy_cmd = [
        "docker", "cp",
        str(project_root / "hl7_sender" / "tests" / "test_integration_throttling.py"),
        "mpi-hl7-sender:/app/test_integration_throttling.py"
    ]

    copy_exit, copy_stdout, copy_stderr = run_command(copy_cmd, project_root)
    if copy_exit != 0:
        print(f"Failed to copy test file to container: {copy_stderr}")
        return 1

    # Run the test inside the container
    test_cmd = [
        "docker", "exec", "mpi-hl7-sender",
        "python", "/app/test_integration_throttling.py"
    ]

    test_exit_code, test_stdout, test_stderr = run_command(test_cmd, project_root)

    # Clean up - remove test file from container
    cleanup_cmd = [
        "docker", "exec", "mpi-hl7-sender",
        "rm", "-f", "/app/test_integration_throttling.py"
    ]
    run_command(cleanup_cmd, project_root)  # Don't check result, cleanup is best effort

    # Print test results
    print("Test STDOUT:")
    print(test_stdout)
    if test_stderr:
        print("Test STDERR:")
        print(test_stderr)

    # Return test results
    return test_exit_code

if __name__ == "__main__":
    sys.exit(main())
