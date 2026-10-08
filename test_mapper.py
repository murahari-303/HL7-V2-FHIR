import unittest
from mapper import HL7FHIRMapper

class TestHL7FHIRMapper(unittest.TestCase):
    def setUp(self):
        self.mapper = HL7FHIRMapper()
        self.sample_hl7 = (
            "MSH|^~\\&|EPIC|HOSPITAL|LAB|DEST|20261003120000||ORU^R01|MSG00001|P|2.5\r"
            "PID|1||MRN998877^^^HOSP||DOE^JANE||19850512|F\r"
            "PV1|1|I||||||||||||||||||||||||||||||||||||||||20261003080000"
        )

    def test_hl7_to_fhir(self):
        bundle = self.mapper.hl7_to_fhir(self.sample_hl7)
        self.assertEqual(bundle.type, "transaction")
        self.assertTrue(len(bundle.entry) >= 2)

    def test_fhir_to_hl7_roundtrip(self):
        bundle = self.mapper.hl7_to_fhir(self.sample_hl7)
        reconstructed = self.mapper.fhir_to_hl7(bundle, msg_type="ORU^R01")
        self.assertIn("PID", reconstructed)
        self.assertIn("DOE^JANE", reconstructed)

if __name__ == "__main__":
    unittest.main()