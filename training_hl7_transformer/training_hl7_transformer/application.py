"""
Training HL7 Transformer - Application Entry Point
===================================================

This is the main entry point for running the Training HL7 Transformer.
It's invoked when you run: python -m training_hl7_transformer.application

LEARNING OBJECTIVES:
-------------------
1. Understand how Python modules are structured as packages
2. See the pattern for creating runnable applications

RUNNING THE TRANSFORMER:
-----------------------
There are several ways to run this transformer:

1. From command line (after installing dependencies):
   $ cd training_hl7_transformer
   $ uv sync
   $ uv run python -m training_hl7_transformer.application

2. With Docker:
   $ just training-up  # (from the local/ directory)

3. In VS Code:
   - Set up launch.json to run this module
   - Press F5 to debug

WHAT HAPPENS WHEN THIS RUNS:
---------------------------
1. Creates a TrainingTransformer instance
2. Calls transformer.run() which:
   - Loads configuration from environment and config.ini
   - Connects to ingress and egress Service Bus queues
   - Enters a loop waiting for messages
   - Transforms and forwards each message
3. Continues until Ctrl+C or SIGTERM is received
"""

from training_hl7_transformer.training_transformer import TrainingTransformer


def main() -> None:
    """
    Create and run the training transformer.

    This function is the entry point for the application.
    It creates a transformer instance and starts the main loop.
    """
    # Create the transformer instance
    transformer = TrainingTransformer()

    # Run the main processing loop
    # This blocks until shutdown signal is received
    transformer.run()


# This block runs when the module is executed directly
# e.g., python -m training_hl7_transformer.application
if __name__ == "__main__":
    main()