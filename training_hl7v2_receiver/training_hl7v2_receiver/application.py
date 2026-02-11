"""Entry point for the Training HL7v2 Receiver."""

from training_hl7v2_receiver.training_receiver import TrainingHl7v2ReceiverApplication


def main() -> None:
    """
    Main entry point - create and start the server.

    This function is called when you run:
        python -m training_hl7v2_receiver.application

    It creates an instance of TrainingHl7v2ReceiverApplication and starts it.
    """
    # Create the server application instance
    app = TrainingHl7v2ReceiverApplication()

    # Start the server (this blocks until the server is stopped)
    app.start_server()


# This block ensures main() is only called when running this file directly
# (not when importing it as a module)
if __name__ == "__main__":
    main()
