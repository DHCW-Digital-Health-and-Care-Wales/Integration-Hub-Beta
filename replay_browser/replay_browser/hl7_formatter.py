from dataclasses import dataclass


@dataclass(frozen=True)
class Hl7Subcomponent:
    index: int
    value: str


@dataclass(frozen=True)
class Hl7Component:
    index: int
    value: str
    subcomponents: list[Hl7Subcomponent]


@dataclass(frozen=True)
class Hl7Repetition:
    index: int
    value: str
    components: list[Hl7Component]


@dataclass(frozen=True)
class Hl7Field:
    number: int
    value: str
    repetitions: list[Hl7Repetition]


@dataclass(frozen=True)
class Hl7Segment:
    name: str
    index: int
    fields: list[Hl7Field]


def _normalize_lines(hl7_text: str) -> list[str]:
    normalized = hl7_text.replace("\r\n", "\n").replace("\r", "\n")
    return [line.strip() for line in normalized.split("\n") if line.strip()]


def _parse_subcomponents(value: str) -> list[Hl7Subcomponent]:
    if "&" not in value:
        return []
    return [Hl7Subcomponent(index=i + 1, value=part) for i, part in enumerate(value.split("&"))]


def _parse_components(value: str) -> list[Hl7Component]:
    if "^" not in value:
        return []

    components: list[Hl7Component] = []
    for component_index, part in enumerate(value.split("^"), start=1):
        components.append(
            Hl7Component(
                index=component_index,
                value=part,
                subcomponents=_parse_subcomponents(part),
            )
        )
    return components


def _parse_repetitions(value: str) -> list[Hl7Repetition]:
    if "~" not in value:
        return []

    repetitions: list[Hl7Repetition] = []
    for repetition_index, part in enumerate(value.split("~"), start=1):
        repetitions.append(
            Hl7Repetition(
                index=repetition_index,
                value=part,
                components=_parse_components(part),
            )
        )
    return repetitions


def parse_hl7(hl7_text: str) -> list[Hl7Segment]:
    if not hl7_text.strip():
        return []

    segments: list[Hl7Segment] = []
    for segment_index, line in enumerate(_normalize_lines(hl7_text), start=1):
        parts = line.split("|")
        if not parts:
            continue

        segment_name = parts[0].strip() or "UNK"

        fields: list[Hl7Field] = []
        for field_index, raw_value in enumerate(parts[1:], start=1):
            field_number = field_index + 1 if segment_name == "MSH" else field_index
            fields.append(
                Hl7Field(
                    number=field_number,
                    value=raw_value,
                    repetitions=_parse_repetitions(raw_value),
                )
            )

        if segment_name == "MSH":
            fields.insert(
                0,
                Hl7Field(
                    number=1,
                    value="|",
                    repetitions=[],
                ),
            )

        segments.append(Hl7Segment(name=segment_name, index=segment_index, fields=fields))

    return segments


def first_field_value(segments: list[Hl7Segment], segment_name: str, field_number: int) -> str | None:
    for segment in segments:
        if segment.name != segment_name:
            continue
        for field in segment.fields:
            if field.number == field_number:
                return field.value
    return None
