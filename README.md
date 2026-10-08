# HL7 v2 <-> FHIR R4 Mapper & Data Pipeline

Bi-directional conversion utility between HL7 v2.x messages and FHIR R4 Bundles built with Python.

## Features
- Maps HL7 v2.x (`ORU^R01`, `ADT^A08`, `ORM^O01`) to standard FHIR R4 JSON Bundles.
- Reconstructs HL7 v2.x messages back from FHIR Bundles without data loss.
- Preserves unmapped fields and custom Z-segments using FHIR Extensions.

## Setup & Execution
1. Install dependencies:
   ```bash
   pip install hl7apy fhir.resources pydantic