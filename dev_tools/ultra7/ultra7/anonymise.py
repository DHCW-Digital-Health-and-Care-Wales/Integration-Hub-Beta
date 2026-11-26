"""One-click PII anonymiser / scrubber for HL7 v2.x, XML, and JSON clinical messages."""
from __future__ import annotations

import json
import random
import re
from typing import Any

from ultra7.models import MessageFormat
from ultra7.nhs_number import generate_nhs_number

_SYNTHETIC_SURNAMES = ("TESTSMITH", "TESTJONES", "TESTDAVIES", "TESTEVANS", "TESTWILLIAMS", "TESTMORGAN")
_SYNTHETIC_GIVENS = ("ALICE", "DAVID", "RHIAN", "GARETH", "MEGAN", "OWEN")
_SYNTHETIC_STREETS = ("1 TEST STREET", "10 SAMPLE ROAD", "42 MOCK AVENUE", "7 DEMO CLOSE")
_SYNTHETIC_CITIES = ("CARDIFF", "SWANSEA", "NEWPORT", "BANGOR", "WREXHAM")
_SYNTHETIC_POSTCODES = ("CF10 1AA", "SA1 1AA", "NP20 1AA", "LL57 1AA", "LL11 1AA")
_SYNTHETIC_PHONES = ("07700900001", "07700900123", "07700900456", "02920180001")
_SYNTHETIC_DOBS = ("19800115", "19750622", "19910309", "19681130", "19850814")

_XML_PII_TAGS = {
    "nhsnumber",
    "nhs_number",
    "patientid",
    "patientname",
    "fullname",
    "family",
    "familyname",
    "surname",
    "lastname",
    "given",
    "givenname",
    "forename",
    "firstname",
    "middlename",
    "dateofbirth",
    "dob",
    "birthdate",
    "address",
    "addressline",
    "addressline1",
    "street",
    "city",
    "postcode",
    "postalcode",
    "telephone",
    "phone",
    "mobile",
    "email",
}

_TAG_ATTRS_PART = r'(?:\s(?:"[^"]*"|\'[^\']*\'|[^>"\'])*)?'
_XML_CDATA_RE = re.compile(
    rf"(<([A-Za-z_][\w:.-]*){_TAG_ATTRS_PART}>\s*<!\[CDATA\[)(.*?)(\]\]>\s*</\2>)",
    re.DOTALL,
)
_XML_LEAF_RE = re.compile(rf"(<([A-Za-z_][\w:.-]*){_TAG_ATTRS_PART}>)([^<>]+)(</\2>)")
_XML_OPEN_TAG_RE = re.compile(r"<([A-Za-z_][\w:.-]*)((?:\s(?:\"[^\"]*\"|'[^']*'|[^<>\"'])*)?)(/?)>")
_XML_VALUE_ATTR_RE = re.compile(r'(\bvalue\s*=\s*)(["\'])([^"\']*)\2')


def anonymise_message(content: str, message_format: MessageFormat, seed: int | None = None) -> str:
    """Replace clinical PII in *content* with realistic synthetic values.

    Preserves message structure, delimiters, and valid Mod-11 NHS numbers.
    """
    if not content.strip():
        return content
    rng = random.Random(seed)  # nosec B311 - synthetic test data only
    if message_format == "hl7":
        return _anonymise_hl7(content, rng)
    if message_format == "xml":
        return _anonymise_xml(content, rng)
    if message_format == "json":
        return _anonymise_json(content, rng)
    return content


def _synthetic_for_key(key: str, original: str, rng: random.Random) -> str:
    low = key.lower().replace("-", "").replace("_", "")
    if "nhs" in low:
        return generate_nhs_number(rng, spaced=" " in original)
    if "family" in low or "surname" in low or "lastname" in low:
        return rng.choice(_SYNTHETIC_SURNAMES)
    if "given" in low or "forename" in low or "firstname" in low or "middle" in low:
        return rng.choice(_SYNTHETIC_GIVENS)
    if "name" in low:
        return f"{rng.choice(_SYNTHETIC_GIVENS)} {rng.choice(_SYNTHETIC_SURNAMES)}"
    if "birth" in low or "dob" in low:
        dob = rng.choice(_SYNTHETIC_DOBS)
        return f"{dob[:4]}-{dob[4:6]}-{dob[6:]}" if "-" in original else dob
    if "post" in low or "zip" in low:
        return rng.choice(_SYNTHETIC_POSTCODES)
    if "city" in low or "town" in low:
        return rng.choice(_SYNTHETIC_CITIES)
    if "address" in low or "street" in low or "line" in low:
        return rng.choice(_SYNTHETIC_STREETS)
    if "email" in low:
        return "test.patient@example.test"
    if "phone" in low or "tel" in low or "mobile" in low:
        return rng.choice(_SYNTHETIC_PHONES)
    if "patientid" in low:
        return f"TEST{rng.randint(100000, 999999)}"
    return original


# ---------------------------------------------------------------------------
# HL7 anonymiser
# ---------------------------------------------------------------------------

def _scrub_hl7_name(raw: str, comp_sep: str, rng: random.Random) -> str:
    if not raw.strip():
        return raw
    comps = raw.split(comp_sep)
    comps[0] = rng.choice(_SYNTHETIC_SURNAMES)
    if len(comps) > 1 and comps[1]:
        comps[1] = rng.choice(_SYNTHETIC_GIVENS)
    if len(comps) > 2 and comps[2]:
        comps[2] = "T"
    return comp_sep.join(comps)


def _scrub_hl7_address(raw: str, comp_sep: str, rng: random.Random) -> str:
    if not raw.strip():
        return raw
    comps = raw.split(comp_sep)
    comps[0] = rng.choice(_SYNTHETIC_STREETS)
    if len(comps) > 1 and comps[1]:
        comps[1] = ""
    if len(comps) > 2 and comps[2]:
        comps[2] = rng.choice(_SYNTHETIC_CITIES)
    if len(comps) > 4 and comps[4]:
        comps[4] = rng.choice(_SYNTHETIC_POSTCODES)
    return comp_sep.join(comps)


def _scrub_hl7_id_list(raw: str, comp_sep: str, rep_sep: str, rng: random.Random) -> str:
    if not raw.strip():
        return raw
    scrubbed_reps: list[str] = []
    for rep in raw.split(rep_sep):
        if not rep:
            scrubbed_reps.append(rep)
            continue
        comps = rep.split(comp_sep)
        id_val = comps[0]
        digits = "".join(ch for ch in id_val if ch.isdigit())
        is_nhs = (len(digits) == 10) or any("NHS" in c.upper() or c.upper() == "NH" for c in comps[1:])
        if is_nhs:
            comps[0] = generate_nhs_number(rng, spaced=" " in id_val)
        elif id_val:
            comps[0] = f"TEST{rng.randint(100000, 999999)}"
        scrubbed_reps.append(comp_sep.join(comps))
    return rep_sep.join(scrubbed_reps)


def _anonymise_hl7(content: str, rng: random.Random) -> str:
    field_sep = "|"
    comp_sep = "^"
    rep_sep = "~"
    for line in re.split(r"\r\n|\r|\n", content):
        if line.startswith("MSH") and len(line) >= 8:
            field_sep = line[3]
            comp_sep = line[4]
            rep_sep = line[5]
            break

    # Preserve original line separators exactly.
    tokens = re.split(r"(\r\n|\r|\n)", content)
    out: list[str] = []
    for token in tokens:
        if token in ("\r\n", "\r", "\n") or not token.strip():
            out.append(token)
            continue
        fields = token.split(field_sep)
        seg = fields[0].strip()

        if seg == "PID":
            if len(fields) > 2 and fields[2]:
                fields[2] = _scrub_hl7_id_list(fields[2], comp_sep, rep_sep, rng)
            if len(fields) > 3 and fields[3]:
                fields[3] = _scrub_hl7_id_list(fields[3], comp_sep, rep_sep, rng)
            for idx in (5, 6, 9):
                if len(fields) > idx and fields[idx]:
                    fields[idx] = rep_sep.join(
                        _scrub_hl7_name(r, comp_sep, rng) for r in fields[idx].split(rep_sep)
                    )
            if len(fields) > 7 and fields[7]:
                dob = rng.choice(_SYNTHETIC_DOBS)
                fields[7] = dob + fields[7][8:] if len(fields[7]) > 8 else dob
            if len(fields) > 11 and fields[11]:
                fields[11] = rep_sep.join(
                    _scrub_hl7_address(r, comp_sep, rng) for r in fields[11].split(rep_sep)
                )
            for idx in (13, 14):
                if len(fields) > idx and fields[idx]:
                    fields[idx] = rep_sep.join(
                        rng.choice(_SYNTHETIC_PHONES) if r.strip() else r for r in fields[idx].split(rep_sep)
                    )
            if len(fields) > 19 and fields[19]:
                fields[19] = generate_nhs_number(rng)
        elif seg == "NK1":
            if len(fields) > 2 and fields[2]:
                fields[2] = rep_sep.join(
                    _scrub_hl7_name(r, comp_sep, rng) for r in fields[2].split(rep_sep)
                )
            if len(fields) > 4 and fields[4]:
                fields[4] = rep_sep.join(
                    _scrub_hl7_address(r, comp_sep, rng) for r in fields[4].split(rep_sep)
                )
            if len(fields) > 5 and fields[5]:
                fields[5] = rep_sep.join(
                    rng.choice(_SYNTHETIC_PHONES) if r.strip() else r for r in fields[5].split(rep_sep)
                )
        elif seg == "MRG":
            if len(fields) > 1 and fields[1]:
                fields[1] = _scrub_hl7_id_list(fields[1], comp_sep, rep_sep, rng)
            if len(fields) > 7 and fields[7]:
                fields[7] = rep_sep.join(
                    _scrub_hl7_name(r, comp_sep, rng) for r in fields[7].split(rep_sep)
                )

        out.append(field_sep.join(fields))
    return "".join(out)


# ---------------------------------------------------------------------------
# XML anonymiser
# ---------------------------------------------------------------------------

def _anonymise_xml(content: str, rng: random.Random) -> str:
    def _replace_cdata(match: re.Match[str]) -> str:
        prefix, full_name, text_val, suffix = match.groups()
        local = full_name.split(":")[-1].lower()
        if local in _XML_PII_TAGS and text_val.strip():
            scrubbed = _synthetic_for_key(local, text_val.strip(), rng)
            return f"{prefix}{scrubbed}{suffix}"
        return match.group(0)

    def _replace_leaf(match: re.Match[str]) -> str:
        open_tag, full_name, text_val, close_tag = match.groups()
        local = full_name.split(":")[-1].lower()
        if local in _XML_PII_TAGS and text_val.strip():
            scrubbed = _synthetic_for_key(local, text_val.strip(), rng)
            return f"{open_tag}{scrubbed}{close_tag}"
        return match.group(0)

    def _replace_value_attr(match: re.Match[str]) -> str:
        full_name, attrs, slash = match.groups()
        local = full_name.split(":")[-1].lower()
        if local not in _XML_PII_TAGS or not attrs:
            return match.group(0)

        def _scrub_attr(attr_match: re.Match[str]) -> str:
            prefix, quote, val = attr_match.groups()
            if not val.strip():
                return attr_match.group(0)
            return f"{prefix}{quote}{_synthetic_for_key(local, val.strip(), rng)}{quote}"

        new_attrs = _XML_VALUE_ATTR_RE.sub(_scrub_attr, attrs)
        return f"<{full_name}{new_attrs}{slash}>"

    result = _XML_CDATA_RE.sub(_replace_cdata, content)
    result = _XML_LEAF_RE.sub(_replace_leaf, result)
    result = _XML_OPEN_TAG_RE.sub(_replace_value_attr, result)
    return result


# ---------------------------------------------------------------------------
# JSON anonymiser
# ---------------------------------------------------------------------------

_JSON_PII_KEYS = {
    "nhsnumber",
    "nhs_number",
    "family",
    "given",
    "surname",
    "forename",
    "patientname",
    "birthdate",
    "dateofbirth",
    "dob",
    "line",
    "street",
    "city",
    "postalcode",
    "postcode",
    "phone",
    "telephone",
    "email",
}


def _scrub_json_node(node: Any, rng: random.Random, parent_key: str = "") -> Any:
    if isinstance(node, dict):
        result: dict[str, Any] = {}
        # Handle FHIR Identifier (NHS number) and ContactPoint (telecom) objects by system.
        system = str(node.get("system", "")).lower()
        for k, v in node.items():
            low = k.lower().replace("-", "")
            if k == "value" and isinstance(v, str) and v.strip():
                if "nhs-number" in system:
                    result[k] = generate_nhs_number(rng, spaced=" " in v)
                elif system in ("phone", "fax", "sms", "pager"):
                    result[k] = rng.choice(_SYNTHETIC_PHONES)
                elif system == "email":
                    result[k] = "test.patient@example.test"
                elif system == "url" and parent_key == "telecom":
                    result[k] = "https://example.test"
                elif parent_key == "telecom":
                    result[k] = rng.choice(_SYNTHETIC_PHONES)
                else:
                    result[k] = v
            elif low in _JSON_PII_KEYS:
                result[k] = _scrub_json_value(low, v, rng)
            else:
                result[k] = _scrub_json_node(v, rng, parent_key=low)
        return result
    if isinstance(node, list):
        return [_scrub_json_node(item, rng, parent_key=parent_key) for item in node]
    return node


def _scrub_json_value(key: str, value: Any, rng: random.Random) -> Any:
    if isinstance(value, str):
        return _synthetic_for_key(key, value, rng)
    if isinstance(value, list):
        return [_synthetic_for_key(key, item, rng) if isinstance(item, str) else item for item in value]
    return value


def _anonymise_json(content: str, rng: random.Random) -> str:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content
    scrubbed = _scrub_json_node(parsed, rng)
    return json.dumps(scrubbed, indent=2)
