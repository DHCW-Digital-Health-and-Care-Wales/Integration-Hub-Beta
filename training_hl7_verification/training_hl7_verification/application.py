"""
Training HL7 Verification - Application Entry Point
===================================================

This is the main entry point for running the Training HL7 Verification.
It's invoked when you run: python -m training_hl7_verification.application

LEARNING OBJECTIVES:
-------------------
1. Understand how Python modules are structured as packages
2. See the pattern for creating runnable applications

RUNNING THE VERIFICATION:
-----------------------
There are several ways to run this verification:

1. From command line (after installing dependencies):
   $ cd training_hl7_verification
   $ uv sync
   $ uv run python -m training_hl7_verification.application

2. With Docker:
   $ just training-up  # (from the local/ directory)

3. In VS Code:
   - Set up launch.json to run this module
   - Press F5 to debug

WHAT HAPPENS WHEN THIS RUNS:
---------------------------
1. Creates a TrainingVerification instance
2. Calls verification.run() which:
   - Loads configuration from environment and config.ini
   - Connects to ingress and egress Service Bus queues
   - Enters a loop waiting for messages
   - Transforms and forwards each message
3. Continues until Ctrl+C or SIGTERM is received
"""

from training_hl7_verification.training_verification import TrainingVerification


def main() -> None:
    """
    Create and run the training verification.

    This function is the entry point for the application.
    It creates a verification instance and starts the main loop.
    """
    # Create the verification instance
    verification = TrainingVerification()

    # Run the main processing loop
    # This blocks until shutdown signal is received
    verification.run()


# This block runs when the module is executed directly
# e.g., python -m training_hl7_verification.application
if __name__ == "__main__":
    main()
