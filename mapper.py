import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import hl7apy
from hl7apy.parser import parse_message
from hl7apy.core import Message, Segment

from fhir.resources.bundle import Bundle, BundleEntry
from fhir.resources.patient import Patient
from fhir.resources.encounter import Encounter
from fhir.resources.servicerequest import ServiceRequest
from fhir.resources.diagnosticreport import DiagnosticReport
from fhir.resources.observation import Observation
from fhir.resources.extension import Extension
from fhir.resources.identifier import Identifier
from fhir.resources.coding import Coding
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.reference import Reference

# Custom Extension URLs for zero data loss
LOSSY_FIELD_EXT_URL = "http://example.org/fhir/StructureDefinition/hl7v2-unmapped-field"
Z_SEGMENT_EXT_URL = "http://example.org/fhir/StructureDefinition/hl7v2-zsegment"


class HL7FHIRMapper:

    # -------------------------------------------------------------------------
    # UTILITY METHODS
    # -------------------------------------------------------------------------
    @staticmethod
    def parse_hl7_date(dt_str: str) -> Optional[str]:
        """Converts YYYYMMDDHHMMSS / YYYYMMDD to ISO-8601 format."""
        if not dt_str:
            return None
        clean_dt = str(dt_str).split('.')[0]
        length = len(clean_dt)
        try:
            if length >= 14:
                dt = datetime.strptime(clean_dt[:14], "%Y%m%d%H%M%S")
                return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            elif length >= 8:
                dt = datetime.strptime(clean_dt[:8], "%Y%m%d")
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
        return None

    @staticmethod
    def format_hl7_date(iso_str: Any) -> str:
        """Converts FHIR date/datetime object or ISO-8601 string back to YYYYMMDDHHMMSS."""
        if not iso_str:
            return ""
        
        raw_str = str(iso_str).strip()
        if not raw_str:
            return ""

        clean_iso = raw_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean_iso)
            return dt.strftime("%Y%m%d%H%M%S")
        except ValueError:
            clean_date = raw_str.replace("-", "").replace(":", "").replace("T", "").split("+")[0].split(" ")[0]
            return clean_date

    # -------------------------------------------------------------------------
    # FORWARD MAPPING: HL7 v2.x -> FHIR R4 Bundle
    # -------------------------------------------------------------------------
    def hl7_to_fhir(self, hl7_raw: str) -> Bundle:
        hl7_normalized = hl7_raw.replace("\r\n", "\r").replace("\n", "\r")
        msg = parse_message(hl7_normalized, find_groups=False)
        
        bundle_entries = []
        msg_type = msg.MSH.MSH_9.MSH_9_1.value if hasattr(msg.MSH, 'MSH_9') else ""

        patient_ref = None
        encounter_ref = None

        # 1. PID -> Patient
        if hasattr(msg, 'PID'):
            patient, p_id = self._map_pid_to_patient(msg.PID)
            patient_ref = f"Patient/{p_id}"
            bundle_entries.append(BundleEntry(fullUrl=f"urn:uuid:{p_id}", resource=patient))

        # 2. PV1 -> Encounter
        if hasattr(msg, 'PV1'):
            encounter, enc_id = self._map_pv1_to_encounter(msg.PV1, patient_ref)
            encounter_ref = f"Encounter/{enc_id}"
            bundle_entries.append(BundleEntry(fullUrl=f"urn:uuid:{enc_id}", resource=encounter))

        # 3. ORM Mapping (ORC -> ServiceRequest)
        if msg_type in ['ORM', 'OML'] and hasattr(msg, 'ORC'):
            sr, sr_id = self._map_orc_to_servicerequest(msg.ORC, patient_ref, encounter_ref)
            bundle_entries.append(BundleEntry(fullUrl=f"urn:uuid:{sr_id}", resource=sr))

        # 4. ORU Mapping (OBR/OBX -> DiagnosticReport & Observation)
        if msg_type in ['ORU', 'R01'] and hasattr(msg, 'OBR'):
            report, obs_list = self._map_oru_to_resources(msg, patient_ref, encounter_ref)
            for obs, o_id in obs_list:
                bundle_entries.append(BundleEntry(fullUrl=f"urn:uuid:{o_id}", resource=obs))
            if report:
                bundle_entries.append(BundleEntry(fullUrl=f"urn:uuid:{report.id}", resource=report))

        # 5. Dynamic Z-Segments (Zero Data Loss)
        for children in msg.children:
            if isinstance(children, Segment) and children.name.startswith("Z"):
                z_ext = self._pack_z_segment(children)
                if bundle_entries:
                    target_res = bundle_entries[0].resource
                    if target_res.extension is None:
                        target_res.extension = []
                    target_res.extension.append(z_ext)

        bundle = Bundle(
            id=str(uuid.uuid4()),
            type="transaction",
            entry=bundle_entries
        )
        return bundle

    def _map_pid_to_patient(self, pid: Segment) -> Tuple[Patient, str]:
        p_id = str(uuid.uuid4())
        patient = Patient(id=p_id)
        
        mrn = pid.PID_3.PID_3_1.value if hasattr(pid, 'PID_3') and pid.PID_3.PID_3_1.value else "UNKNOWN"
        patient.identifier = [Identifier(system="http://hospital.smart.org/mrn", value=mrn)]
        
        if hasattr(pid, 'PID_5'):
            family = pid.PID_5.PID_5_1.value if hasattr(pid.PID_5, 'PID_5_1') and pid.PID_5.PID_5_1.value else "UNKNOWN"
            given = [pid.PID_5.PID_5_2.value] if hasattr(pid.PID_5, 'PID_5_2') and pid.PID_5.PID_5_2.value else ["UNKNOWN"]
            patient.name = [{"family": family, "given": given}]

        if hasattr(pid, 'PID_8') and pid.PID_8.value:
            g_map = {"M": "male", "F": "female", "O": "other", "U": "unknown"}
            patient.gender = g_map.get(pid.PID_8.value, "unknown")

        if hasattr(pid, 'PID_7') and pid.PID_7.value:
            patient.birthDate = self.parse_hl7_date(pid.PID_7.value)

        if hasattr(pid, 'PID_26') and pid.PID_26.value:
            ext = Extension(
                url=LOSSY_FIELD_EXT_URL,
                valueString=f"PID-26={pid.PID_26.value}"
            )
            patient.extension = [ext]

        return patient, p_id

    def _map_pv1_to_encounter(self, pv1: Segment, patient_ref: Optional[str]) -> Tuple[Encounter, str]:
        enc_id = str(uuid.uuid4())
        status = "in-progress"
        
        cls_code = "IMP"
        if hasattr(pv1, 'PV1_2') and pv1.PV1_2.value:
            pv1_cls = pv1.PV1_2.value
            cls_code = "IMP" if pv1_cls == "I" else "AMB"

        encounter = Encounter(
            id=enc_id, 
            status=status, 
            class_fhir=[
                CodeableConcept(
                    coding=[
                        Coding(
                            system="http://terminology.hl7.org/CodeSystem/v3-ActCode", 
                            code=cls_code
                        )
                    ]
                )
            ]
        )
        
        if patient_ref:
            encounter.subject = Reference(reference=patient_ref)

        period_data = {}
        if hasattr(pv1, 'PV1_44') and pv1.PV1_44.value:
            period_data["start"] = self.parse_hl7_date(pv1.PV1_44.value)
        if hasattr(pv1, 'PV1_45') and pv1.PV1_45.value:
            period_data["end"] = self.parse_hl7_date(pv1.PV1_45.value)
            encounter.status = "completed"

        if period_data:
            # Handles both actualPeriod (FHIR v7+) and period (legacy FHIR)
            if hasattr(encounter, 'actualPeriod'):
                encounter.actualPeriod = period_data
            else:
                encounter.period = period_data

        return encounter, enc_id

    def _map_orc_to_servicerequest(self, orc: Segment, patient_ref: Optional[str], enc_ref: Optional[str]) -> Tuple[ServiceRequest, str]:
        sr_id = str(uuid.uuid4())
        sr = ServiceRequest(
            id=sr_id,
            status="active",
            intent="order",
            subject=Reference(reference=patient_ref) if patient_ref else Reference(display="Unknown Patient")
        )
        if hasattr(orc, 'ORC_2') and orc.ORC_2.value:
            sr.identifier = [Identifier(system="http://hospital.smart.org/orders", value=orc.ORC_2.value)]
        if enc_ref:
            sr.encounter = Reference(reference=enc_ref)
        return sr, sr_id

    def _map_oru_to_resources(self, msg: Message, patient_ref: Optional[str], enc_ref: Optional[str]) -> Tuple[DiagnosticReport, List[Tuple[Observation, str]]]:
        obs_list = []
        obs_refs = []
        
        for child in msg.children:
            if isinstance(child, Segment) and child.name == 'OBX':
                obs_id = str(uuid.uuid4())
                
                code_text = "Observation"
                if hasattr(child, 'OBX_3'):
                    if hasattr(child.OBX_3, 'OBX_3_2') and child.OBX_3.OBX_3_2.value:
                        code_text = str(child.OBX_3.OBX_3_2.value).strip()
                    elif child.OBX_3.value:
                        code_text = str(child.OBX_3.value).strip()

                obs = Observation(
                    id=obs_id,
                    status="final",
                    code=CodeableConcept(text=code_text)
                )
                if hasattr(child, 'OBX_5') and child.OBX_5.value:
                    obs.valueString = str(child.OBX_5.value)
                if patient_ref:
                    obs.subject = Reference(reference=patient_ref)
                
                obs_list.append((obs, obs_id))
                obs_refs.append(Reference(reference=f"Observation/{obs_id}"))

        report_id = str(uuid.uuid4())
        report = DiagnosticReport(
            id=report_id,
            status="final",
            code=CodeableConcept(text="Lab Report"),
            result=obs_refs,
            subject=Reference(reference=patient_ref) if patient_ref else None
        )
        return report, obs_list

    def _pack_z_segment(self, z_seg: Segment) -> Extension:
        raw_val = z_seg.to_er7()
        return Extension(
            url=Z_SEGMENT_EXT_URL,
            valueString=raw_val
        )

    # -------------------------------------------------------------------------
    # REVERSE MAPPING: FHIR R4 Bundle -> HL7 v2.x Message
    # -------------------------------------------------------------------------
    def fhir_to_hl7(self, bundle: Bundle, msg_type: str = "ADT^A08^ADT_A01") -> str:
        hl7_segments = []
        
        now_str = datetime.now().strftime("%Y%m%d%H%M%S")
        msh = f"MSH|^~\\&|FHIR_BRIDGE|FACILITY|RECEIVER|DEST|{now_str}||{msg_type}|MSG{now_str[:8]}|P|2.5"
        hl7_segments.append(msh)

        patient_res: Optional[Patient] = None
        encounter_res: Optional[Encounter] = None
        observations: List[Observation] = []
        z_segments_raw: List[str] = []

        for entry in bundle.entry:
            res = entry.resource
            
            # Safe resource type detection to prevent Pydantic AttributeError
            r_type = res.get_resource_type() if hasattr(res, 'get_resource_type') else getattr(res, '__resource_type__', res.__class__.__name__)

            if r_type == "Patient":
                patient_res = res
            elif r_type == "Encounter":
                encounter_res = res
            elif r_type == "Observation":
                observations.append(res)

            if hasattr(res, 'extension') and res.extension:
                for ext in res.extension:
                    if ext.url == Z_SEGMENT_EXT_URL:
                        z_segments_raw.append(ext.valueString)

        if patient_res:
            pid_str = self._reconstruct_pid(patient_res)
            hl7_segments.append(pid_str)

        if encounter_res:
            pv1_str = self._reconstruct_pv1(encounter_res)
            hl7_segments.append(pv1_str)

        for idx, obs in enumerate(observations, start=1):
            obx_str = self._reconstruct_obx(obs, idx)
            hl7_segments.append(obx_str)

        for z_raw in z_segments_raw:
            hl7_segments.append(z_raw)

        return "\r".join(hl7_segments)

    def _reconstruct_pid(self, patient: Patient) -> str:
        mrn = patient.identifier[0].value if patient.identifier else ""
        family = patient.name[0].family if patient.name else ""
        given = patient.name[0].given[0] if patient.name and patient.name[0].given else ""
        gender = "U"
        if patient.gender:
            g_map = {"male": "M", "female": "F", "other": "O", "unknown": "U"}
            gender = g_map.get(patient.gender, "U")
        
        dob = self.format_hl7_date(patient.birthDate) if patient.birthDate else ""

        pid_26_val = ""
        if patient.extension:
            for ext in patient.extension:
                if ext.url == LOSSY_FIELD_EXT_URL and "PID-26=" in ext.valueString:
                    pid_26_val = ext.valueString.split("=")[1]

        pid_fields = ["PID", "1", "", mrn, "", f"{family}^{given}", "", dob, gender, "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", pid_26_val]
        return "|".join(pid_fields)

    def _reconstruct_pv1(self, enc: Encounter) -> str:
        pv1_cls = "O"
        if hasattr(enc, 'class_fhir') and enc.class_fhir:
            first_concept = enc.class_fhir[0]
            if hasattr(first_concept, 'coding') and first_concept.coding:
                if first_concept.coding[0].code == "IMP":
                    pv1_cls = "I"

        # Safely checks actualPeriod (FHIR v7+) and period (legacy FHIR)
        enc_period = getattr(enc, 'actualPeriod', None) or getattr(enc, 'period', None)
        
        start_time = ""
        end_time = ""
        if enc_period:
            if getattr(enc_period, 'start', None):
                start_time = self.format_hl7_date(enc_period.start)
            if getattr(enc_period, 'end', None):
                end_time = self.format_hl7_date(enc_period.end)

        pv1_fields = ["PV1", "1", pv1_cls] + [""] * 41 + [start_time, end_time]
        return "|".join(pv1_fields)

    def _reconstruct_obx(self, obs: Observation, idx: int) -> str:
        obs_code = obs.code.text if obs.code and obs.code.text else "Observation"
        obs_val = obs.valueString if obs.valueString else ""
        obx_fields = ["OBX", str(idx), "ST", obs_code, "", obs_val, "", "", "", "", "", "F"]
        return "|".join(obx_fields)