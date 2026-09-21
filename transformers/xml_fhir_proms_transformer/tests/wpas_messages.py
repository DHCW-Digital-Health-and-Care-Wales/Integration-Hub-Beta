"""WPAS XML fixtures for the PROMS transformer tests.

All fixtures use the actual PromsEventRequest root element format confirmed
from real WPAS SIT payload samples. The eventCode field inside the document
is used for message routing (not the root element tag).

Field names match the actual camelCase WPAS payload fields observed in SIT
(e.g. nhsNumber, patientFirstname, patientSurname, hbCode, referrer_code).
"""

# Full REFERRAL message — all currently-mapped fields populated.
# Based on real SIT payload format (hbCode X98 is a SIT test code).
REFERRAL_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
  <postCode>NP22 3AA</postCode>
  <postalCounty>Gwent</postalCounty>
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
</PromsEventRequest>
"""

# SURGERY (Procedure Performed) message
SURGERY_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
</PromsEventRequest>
"""

# PREOP (Appointment Scheduled) message
PREOP_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
</PromsEventRequest>
"""

# INPATIENT (Inpatient Admission) message
INPATIENT_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
</PromsEventRequest>
"""

# CANCELLED (Appointment Cancelled) message
CANCELLED_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
</PromsEventRequest>
"""

# PREREAD (Pre-admission Notification) message
PREREAD_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
</PromsEventRequest>
"""

# --- TEMP: placeholder fixtures for the additional WPAS PROMS event scenarios ---
# No real WPAS sample payloads exist yet for these codes (SURGERY-PROC,
# SURGERY-PERF, SURGERY-DN, PREOP-AS, PREOP-VIS, PREOP-AR are all placeholder
# eventCode values — see PROMS Scenarios.xlsx "PROMS Message-TEMP" column).
# Field values below are dummy/best-guess data, modelled on the existing
# SURGERY/PREOP fixtures above, pending real samples from WPAS.

# SURGERY-PROC (Procedure Performed, disambiguated code)
SURGERY_PROC_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>SURGERY-PROC</eventCode>
  <eventDate>2024-07-20</eventDate>
  <eventPathway>ORTHO</eventPathway>
  <pathway>7A22867980</pathway>
  <nhsNumber>9434766100</nhsNumber>
  <crn>CV0044300</crn>
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
</PromsEventRequest>
"""

# SURGERY-PERF (Surgery Performed)
SURGERY_PERF_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
</PromsEventRequest>
"""

# SURGERY-DN (Discharge Notification)
DISCHARGE_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
</PromsEventRequest>
"""

# PREOP-AS (Appointment Scheduled, disambiguated code)
PREOP_AS_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <system_id>149</system_id>
  <hbCode>X98</hbCode>
  <eventCode>PREOP-AS</eventCode>
  <eventDate>2024-08-05</eventDate>
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
  <appointmentDate>2024-08-15</appointmentDate>
  <appointmentTime>14:00</appointmentTime>
</PromsEventRequest>
"""

# PREOP-VIS (Outpatient Visit)
OUTPATIENT_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
</PromsEventRequest>
"""

# PREOP-AR (Appointment Reschedule) — same activityNotekey as PREOP_AS_MESSAGE,
# with an updated appointmentDate/appointmentTime, per the "Appointment
# resource shall contain the updated date and time" acceptance criterion.
RESCHEDULE_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
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
</PromsEventRequest>
"""

# Minimal REFERRAL — only routing and patient identity present.
MINIMAL_REFERRAL_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <eventCode>REFERRAL</eventCode>
  <nhsNumber>9434765994</nhsNumber>
  <patientSurname>Unknown</patientSurname>
  <patientFirstname>Minimal</patientFirstname>
</PromsEventRequest>
"""

# Explicit eventCode field in a generic root element (confirms eventCode routing).
EXPLICIT_EVENT_CODE_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
<WpasMessage>
  <eventCode>SURGERY</eventCode>
  <system_id>149</system_id>
  <nhsNumber>9434766001</nhsNumber>
  <patientSurname>Nested</patientSurname>
  <patientFirstname>Field</patientFirstname>
</WpasMessage>
"""

# Unroutable message — eventCode not in the known set.
UNROUTABLE_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <eventCode>UNKNOWN_TYPE</eventCode>
  <nhsNumber>9434766010</nhsNumber>
</PromsEventRequest>
"""

# Nested payload — proves the parser is depth-agnostic.
NESTED_REFERRAL_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <Header>
    <eventCode>REFERRAL</eventCode>
    <system_id>149</system_id>
  </Header>
  <Patient>
    <nhsNumber>9434766019</nhsNumber>
    <patientSurname>Nested</patientSurname>
    <patientFirstname>Field</patientFirstname>
  </Patient>
</PromsEventRequest>
"""

# Legacy field names kept as a backwards-compatibility check for the parser.
LEGACY_MESSAGE_TYPE_MESSAGE = """<?xml version="1.0" encoding="UTF-8"?>
<PromsEventRequest>
  <MESSAGE_TYPE>REFERRAL</MESSAGE_TYPE>
  <system_id>149</system_id>
  <nhsNumber>9434766028</nhsNumber>
  <patientSurname>Legacy</patientSurname>
  <patientFirstname>Type</patientFirstname>
</PromsEventRequest>
"""
