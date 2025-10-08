import unittest

from hl7apy.parser import parse_message

from hl7_server.custom_validation.mpi_outbound_validation import _validate_mpi_outbound_specific_fields
from hl7_server.exceptions.validation_exception import ValidationException

BASE_MPI_OUTBOUND_MESSAGE = (
    "MSH|^~\\&|SRC|SRC|DST|DST|2025-05-05 23:23:32||ADT^A28^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1|123456^^^108^MR||Doe^John\r"
)


class TestMpiOutboundValidation(unittest.TestCase):
    def test_valid_message_passes(self) -> None:
        message = parse_message(BASE_MPI_OUTBOUND_MESSAGE)

        _validate_mpi_outbound_specific_fields(message)

    def test_missing_message_type_raises_validation_exception(self) -> None:
        message = parse_message(BASE_MPI_OUTBOUND_MESSAGE)
        message.msh.msh_9.msh_9_2.value = ""

        with self.assertRaisesRegex(ValidationException, "MSH.9.2 MessageType is missing"):
            _validate_mpi_outbound_specific_fields(message)

    def test_unsupported_message_type_raises_validation_exception(self) -> None:
        message = parse_message(BASE_MPI_OUTBOUND_MESSAGE)
        message.msh.msh_9.msh_9_2.value = "A01"

        with self.assertRaisesRegex(ValidationException, "Unsupported message type 'A01'"):
            _validate_mpi_outbound_specific_fields(message)

    def test_missing_update_source_raises_validation_exception(self) -> None:
        message = parse_message(BASE_MPI_OUTBOUND_MESSAGE)
        message.pid.pid_2.cx_4.hd_1.value = ""

        with self.assertRaisesRegex(ValidationException, "PID.2.4.1 UpdateSource is missing"):
            _validate_mpi_outbound_specific_fields(message)


if __name__ == "__main__":
    unittest.main()
