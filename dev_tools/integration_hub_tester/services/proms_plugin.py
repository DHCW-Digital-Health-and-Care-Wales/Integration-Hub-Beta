"""PROMS Transformer plugin.

transform_proms_xml_to_fhir_bundle() is a standalone function — no class init needed.
"""
from __future__ import annotations

import json

from .base import ServicePlugin

_PROMS_REFERRAL = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>REFERRAL</eventCode>
  <eventDate>2024-06-12</eventDate>
  <eventPathway>ORTHO</eventPathway>
  <pathway>7A22867970</pathway>
  <activityNotekey>31688553</activityNotekey>
  <nhsNumber>9434765919</nhsNumber>
  <crn>SB0099887</crn>
  <patientTitle>Mr</patientTitle>
  <patientFirstname>Aneurin</patientFirstname>
  <patientMiddlename>Nye</patientMiddlename>
  <patientSurname>Bevan</patientSurname>
  <gender>M</gender>
  <dob>1897-11-15</dob>
  <buildingName>Tredegar House</buildingName>
  <streetRoadName>Park Street</streetRoadName>
  <postTown>Tredegar</postTown>
  <postalCounty>Gwent</postalCounty>
  <postCode>NP22 3AA</postCode>
  <preferred_spoken_language_code>CY</preferred_spoken_language_code>
  <spoken_language>Welsh</spoken_language>
  <referrer_code>G7654321</referrer_code>
  <referrer_name>ARDERN-JONES L</referrer_name>
  <referrer_location>YSBYTY GWYNEDD, PENRHOSGARNEDD, BANGOR, GWYNEDD, LL57 2PW</referrer_location>
  <referrer_postcode>LL57 2PW</referrer_postcode>
  <referrer_org></referrer_org>
  <dhaCode>7A1</dhaCode>
  <consultant_code>HANJO</consultant_code>
  <clinicianName>Jones, Hannah</clinicianName>
  <consultant_specialty>110</consultant_specialty>
  <main_specialty_name>Trauma and Orthopaedics</main_specialty_name>
  <appointmentDate></appointmentDate>
  <appointmentTime></appointmentTime>
</PromsEventRequest>"""

_PROMS_SURGERY = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>SURGERY</eventCode>
  <eventDate>2024-07-20</eventDate>
  <eventPathway>ORTHO</eventPathway>
  <pathway>7A22867971</pathway>
  <nhsNumber>9434765927</nhsNumber>
  <crn>CV0044221</crn>
  <patientFirstname>Megan</patientFirstname>
  <patientSurname>Williams</patientSurname>
  <gender>F</gender>
  <dob>1975-06-30</dob>
  <postCode>CF10 1EP</postCode>
  <referrer_location>UNIVERSITY HOSPITAL OF WALES, HEATH PARK, CARDIFF, CF14 4XW</referrer_location>
  <referrer_postcode>CF14 4XW</referrer_postcode>
  <dhaCode>7A4</dhaCode>
  <consultant_code>JONMG</consultant_code>
  <clinicianName>Morgan, James</clinicianName>
  <appointmentDate>2024-07-20</appointmentDate>
  <appointmentTime>09:30</appointmentTime>
</PromsEventRequest>"""

_PROMS_PREOP = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>PREOP</eventCode>
  <eventDate>2024-08-05</eventDate>
  <pathway>7A22867972</pathway>
  <activityNotekey>ANK-7A22867972</activityNotekey>
  <nhsNumber>9434765935</nhsNumber>
  <crn>SB0011223</crn>
  <patientFirstname>Gareth</patientFirstname>
  <patientSurname>Jones</patientSurname>
  <gender>M</gender>
  <dob>1960-01-20</dob>
  <postCode>SA2 8QA</postCode>
  <referrer_location>MORRISTON HOSPITAL, SWANSEA, SA6 6NL</referrer_location>
  <referrer_postcode>SA6 6NL</referrer_postcode>
  <dhaCode>7A2</dhaCode>
  <consultant_code>DAVIP</consultant_code>
  <clinicianName>Price, David</clinicianName>
  <main_specialty_name>Trauma and Orthopaedics</main_specialty_name>
  <appointmentDate>2024-08-15</appointmentDate>
  <appointmentTime>14:00</appointmentTime>
  <CONFIRM_APPT>Y</CONFIRM_APPT>
</PromsEventRequest>"""

_PROMS_INPATIENT = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>INPATIENT</eventCode>
  <eventDate>2024-09-10</eventDate>
  <pathway>7A22867973</pathway>
  <activityNotekey>ANK-7A22867973</activityNotekey>
  <nhsNumber>9434765943</nhsNumber>
  <crn>SB0055667</crn>
  <patientFirstname>Eleri</patientFirstname>
  <patientSurname>Price</patientSurname>
  <gender>F</gender>
  <dob>1940-09-02</dob>
  <postCode>SA2 8QA</postCode>
  <referrer_location>MORRISTON HOSPITAL, SWANSEA, SA6 6NL</referrer_location>
  <referrer_postcode>SA6 6NL</referrer_postcode>
  <dhaCode>7A2</dhaCode>
  <consultant_code>WILLR</consultant_code>
  <clinicianName>Williams, Rhys</clinicianName>
</PromsEventRequest>"""

_PROMS_CANCELLED = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>CANCELLED</eventCode>
  <eventDate>2024-10-01</eventDate>
  <pathway>7A22867974</pathway>
  <nhsNumber>9434765951</nhsNumber>
  <crn>SB0077889</crn>
  <patientFirstname>Rhys</patientFirstname>
  <patientSurname>Hughes</patientSurname>
  <gender>M</gender>
  <dob>1985-03-15</dob>
  <postCode>LL57 2AA</postCode>
  <referrer_location>YSBYTY GWYNEDD, PENRHOSGARNEDD, BANGOR, GWYNEDD, LL57 2PW</referrer_location>
  <referrer_postcode>LL57 2PW</referrer_postcode>
  <dhaCode>7A1</dhaCode>
  <consultant_code>HANJO</consultant_code>
  <clinicianName>Jones, Hannah</clinicianName>
  <appointmentDate>2024-10-15</appointmentDate>
  <appointmentTime>11:00</appointmentTime>
  <CONFIRM_APPT>N</CONFIRM_APPT>
</PromsEventRequest>"""

_PROMS_PREREAD = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>PREREAD</eventCode>
  <eventDate>2024-11-05</eventDate>
  <pathway>7A22867975</pathway>
  <nhsNumber>9434765960</nhsNumber>
  <crn>CV0099001</crn>
  <patientFirstname>Owain</patientFirstname>
  <patientSurname>Davies</patientSurname>
  <gender>M</gender>
  <dob>1978-07-22</dob>
  <postCode>CF10 1EP</postCode>
  <referrer_location>UNIVERSITY HOSPITAL OF WALES, HEATH PARK, CARDIFF, CF14 4XW</referrer_location>
  <referrer_postcode>CF14 4XW</referrer_postcode>
  <dhaCode>7A4</dhaCode>
  <consultant_code>DAVIP</consultant_code>
  <clinicianName>Price, David</clinicianName>
</PromsEventRequest>"""

# --- TEMP: placeholder samples for the additional WPAS PROMS event scenarios ---
# No real WPAS sample payloads exist yet for these codes (SURGERY-PERF, SURGERY-DN,
# PREOP-VIS, PREOP-AR are all placeholder eventCode values — see
# PROMS Scenarios.xlsx "PROMS Message-TEMP" column). Field values are dummy/
# best-guess data pending real samples from WPAS.

_PROMS_SURGERY_PERF = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>SURGERY-PERF</eventCode>
  <eventDate>2024-07-21</eventDate>
  <eventPathway>ORTHO</eventPathway>
  <pathway>7A22867981</pathway>
  <nhsNumber>9434766118</nhsNumber>
  <crn>CV0044318</crn>
  <patientFirstname>Ifor</patientFirstname>
  <patientSurname>Rees</patientSurname>
  <gender>M</gender>
  <dob>1968-02-11</dob>
  <postCode>CF10 1EP</postCode>
  <referrer_location>UNIVERSITY HOSPITAL OF WALES, HEATH PARK, CARDIFF, CF14 4XW</referrer_location>
  <referrer_postcode>CF14 4XW</referrer_postcode>
  <dhaCode>7A4</dhaCode>
  <consultant_code>JONMG</consultant_code>
  <clinicianName>Morgan, James</clinicianName>
  <appointmentDate>2024-07-21</appointmentDate>
  <appointmentTime>10:00</appointmentTime>
</PromsEventRequest>"""

_PROMS_DISCHARGE = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>SURGERY-DN</eventCode>
  <eventDate>2024-07-23</eventDate>
  <pathway>7A22867982</pathway>
  <activityNotekey>ANK-7A22867982</activityNotekey>
  <nhsNumber>9434766126</nhsNumber>
  <crn>CV0044326</crn>
  <patientFirstname>Ifor</patientFirstname>
  <patientSurname>Rees</patientSurname>
  <gender>M</gender>
  <dob>1968-02-11</dob>
  <postCode>CF10 1EP</postCode>
  <referrer_location>UNIVERSITY HOSPITAL OF WALES, HEATH PARK, CARDIFF, CF14 4XW</referrer_location>
  <referrer_postcode>CF14 4XW</referrer_postcode>
  <dhaCode>7A4</dhaCode>
  <consultant_code>JONMG</consultant_code>
  <clinicianName>Morgan, James</clinicianName>
</PromsEventRequest>"""

_PROMS_OUTPATIENT = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>PREOP-VIS</eventCode>
  <eventDate>2024-08-20</eventDate>
  <pathway>7A22867984</pathway>
  <activityNotekey>ANK-7A22867984</activityNotekey>
  <nhsNumber>9434766142</nhsNumber>
  <crn>SB0011318</crn>
  <patientFirstname>Bethan</patientFirstname>
  <patientSurname>Lewis</patientSurname>
  <gender>F</gender>
  <dob>1972-05-09</dob>
  <postCode>SA2 8QA</postCode>
  <referrer_location>MORRISTON HOSPITAL, SWANSEA, SA6 6NL</referrer_location>
  <referrer_postcode>SA6 6NL</referrer_postcode>
  <dhaCode>7A2</dhaCode>
  <consultant_code>DAVIP</consultant_code>
  <clinicianName>Price, David</clinicianName>
</PromsEventRequest>"""

_PROMS_RESCHEDULE = """\
<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>PREOP-AR</eventCode>
  <eventDate>2024-08-10</eventDate>
  <pathway>7A22867983</pathway>
  <activityNotekey>ANK-7A22867983</activityNotekey>
  <nhsNumber>9434766134</nhsNumber>
  <crn>SB0011300</crn>
  <patientFirstname>Gareth</patientFirstname>
  <patientSurname>Jones</patientSurname>
  <gender>M</gender>
  <dob>1960-01-20</dob>
  <postCode>SA2 8QA</postCode>
  <referrer_location>MORRISTON HOSPITAL, SWANSEA, SA6 6NL</referrer_location>
  <referrer_postcode>SA6 6NL</referrer_postcode>
  <dhaCode>7A2</dhaCode>
  <consultant_code>DAVIP</consultant_code>
  <clinicianName>Price, David</clinicianName>
  <main_specialty_name>Trauma and Orthopaedics</main_specialty_name>
  <appointmentDate>2024-08-22</appointmentDate>
  <appointmentTime>16:30</appointmentTime>
</PromsEventRequest>"""


class PromsPlugin(ServicePlugin):
    tab_label = "PROMS Transformer"
    description = (
        "WPAS XML (PromsEventRequest) → Promptly FHIR R4B message Bundle\n"
        "Supported eventCodes: REFERRAL · SURGERY(-PROC/-PERF/-DN) · PREOP(-AS/-VIS/-AR) · "
        "INPATIENT · CANCELLED · PREREAD  (TEMP: suffixed codes are placeholders, see README)"
    )
    input_label = "WPAS PromsEventRequest XML"
    output_label = "FHIR R4B JSON Bundle"
    button_label = "▶  Transform"
    samples = {
        "REFERRAL (Referral)": _PROMS_REFERRAL,
        "SURGERY (Procedure, legacy)": _PROMS_SURGERY,
        "SURGERY-PERF (Surgery Performed) TEMP": _PROMS_SURGERY_PERF,
        "SURGERY-DN (Discharge) TEMP": _PROMS_DISCHARGE,
        "PREOP (Appointment, legacy)": _PROMS_PREOP,
        "PREOP-VIS (Outpatient Visit) TEMP": _PROMS_OUTPATIENT,
        "PREOP-AR (Appointment Reschedule) TEMP": _PROMS_RESCHEDULE,
        "INPATIENT (Encounter)": _PROMS_INPATIENT,
        "CANCELLED (Appointment Cancelled)": _PROMS_CANCELLED,
        "PREREAD (Pre-admission)": _PROMS_PREREAD,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        from xml_fhir_proms_transformer.proms_transformer import transform_proms_xml_to_fhir_bundle

        bundle = transform_proms_xml_to_fhir_bundle(input_text.strip())
        raw = bundle.model_dump_json()
        pretty = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)

        entries = [e.resource.get_resource_type() for e in (bundle.entry or [])]
        summary = f"✓  {len(entries)} entries: {', '.join(entries)}"
        return pretty, summary

