from mapper import HL7FHIRMapper

if __name__ == "__main__":
    mapper = HL7FHIRMapper()

    raw_hl7 = (
        "MSH|^~\\&|EPIC|HOSPITAL|LAB|DEST|20261003120000||ORU^R01|MSG00001|P|2.5\r"
        "PID|1||MRN998877^^^HOSP||DOE^JANE||19850512|F||||||||||||||||||PAT_SENSITIVE_FLAG\r"
        "PV1|1|I||||||||||||||||||||||||||||||||||||||||20261003080000\r"
        "OBR|1|ORD123|LAB456|88305^PATHOLOGY\r"
        "OBX|1|ST|88305^GLUCOSE||105|mg/dL|||||F\r"
        "ZDS|100928374^GE_PAC_SYS|APPROVED|CRITICAL_NOTE_55"
    )

    print("=== 1. INCOMING HL7 MESSAGE ===")
    print(raw_hl7.replace("\r", "\n"))

    fhir_bundle = mapper.hl7_to_fhir(raw_hl7)
    
    print("\n=== 2. CONVERTED FHIR R4 BUNDLE (JSON) ===")
    print(fhir_bundle.json(indent=2))

    reconstructed_hl7 = mapper.fhir_to_hl7(fhir_bundle, msg_type="ORU^R01^ORU_R01")

    print("\n=== 3. RECONSTRUCTED HL7 v2.x MESSAGE ===")
    print(reconstructed_hl7.replace("\r", "\n"))