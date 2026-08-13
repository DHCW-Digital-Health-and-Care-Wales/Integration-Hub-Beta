import http.client
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from unittest.mock import MagicMock

from hl7_soap_server.hl7_soap_server_application import create_soap_request_handler


class TestWsdlEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.processor = MagicMock()
        handler_class = create_soap_request_handler(
            processor=self.processor,
            endpoint_path="/soap",
            max_request_size_bytes=1_048_576,
            tls_enabled=False,
        )
        self.server = HTTPServer(("127.0.0.1", 0), handler_class)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()

    def test_get_wsdl_returns_wsdl_document_addressed_at_the_requesting_host(self) -> None:
        # Fixed http:// URL against our own local test server, not user-controlled input.
        with urllib.request.urlopen(f"{self.base_url}/soap?wsdl") as response:  # nosec B310
            body = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type")

        self.assertEqual(200, response.status)
        self.assertIn("text/xml", content_type)
        self.assertIn(f"{self.base_url}/soap", body)
        self.processor.process.assert_not_called()

    def test_get_wsdl_with_absolute_form_request_target_returns_wsdl_document(self) -> None:
        # Simulate a reverse proxy (e.g. Azure Container Apps ingress) forwarding
        # the request with an absolute-form request-target such as:
        #   GET http://127.0.0.1:<port>/soap?wsdl HTTP/1.1
        # http.client lets us write the request line manually to achieve this.
        port = self.server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port)
        absolute_target = f"http://127.0.0.1:{port}/soap?wsdl"
        conn.request("GET", absolute_target, headers={"Host": f"127.0.0.1:{port}"})
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        content_type = response.getheader("Content-Type")
        conn.close()

        self.assertEqual(200, response.status)
        self.assertIn("text/xml", content_type)
        self.assertIn("/soap", body)
        self.processor.process.assert_not_called()

    def test_get_without_wsdl_query_is_rejected(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            # Fixed http:// URL against our own local test server, not user-controlled input.
            urllib.request.urlopen(f"{self.base_url}/soap")  # nosec B310

        self.assertEqual(405, context.exception.code)


if __name__ == "__main__":
    unittest.main()
