"""Entry point for the Training HL7 Server."""

from training_hl7_server.server_application import TrainingHl7ServerApplication


def main() -> None:
    """
    Main entry point - create and start the server.

    This function is called when you run:
        python -m training_hl7_server.application

    It creates an instance of TrainingHl7ServerApplication and starts it.
    """
    # Create the server application instance
    app = TrainingHl7ServerApplication()

    # Start the server (this blocks until the server is stopped)
    app.start_server()


# This block ensures main() is only called when running this file directly
# (not when importing it as a module)
if __name__ == "__main__":
    main()
