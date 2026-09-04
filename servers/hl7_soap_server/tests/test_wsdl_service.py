import unittest

from hl7_soap_server.wsdl_service import build_wsdl_document


class TestBuildWsdlDocument(unittest.TestCase):
    def test_wsdl_document_addresses_the_given_base_url(self) -> None:
        base_url = "https://uks-dev-lims-hl7soapserver-ca.example.uksouth.azurecontainerapps.io/soap"

        wsdl_bytes = build_wsdl_document(base_url)
        wsdl_text = wsdl_bytes.decode("utf-8")

        self.assertIn(base_url, wsdl_text)

    def test_wsdl_document_declares_both_hl7_operations(self) -> None:
        wsdl_text = build_wsdl_document("http://localhost:8080/soap").decode("utf-8")

        self.assertIn("SubmitADT_A05", wsdl_text)
        self.assertIn("SubmitADT_A39", wsdl_text)

    def test_wsdl_document_is_regenerated_for_a_different_environment(self) -> None:
        dev_url = "https://dev-example.uksouth.azurecontainerapps.io/soap"
        prod_url = "https://prod-example.uksouth.azurecontainerapps.io/soap"

        dev_wsdl = build_wsdl_document(dev_url).decode("utf-8")
        prod_wsdl = build_wsdl_document(prod_url).decode("utf-8")

        self.assertIn(dev_url, dev_wsdl)
        self.assertNotIn(prod_url, dev_wsdl)
        self.assertIn(prod_url, prod_wsdl)
        self.assertNotIn(dev_url, prod_wsdl)


if __name__ == "__main__":
    unittest.main()
