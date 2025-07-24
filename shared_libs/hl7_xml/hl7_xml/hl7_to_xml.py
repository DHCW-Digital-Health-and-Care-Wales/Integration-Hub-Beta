from typing import Any

import hl7apy.core
from lxml import etree


def mapHl7toXml(hl7Element: hl7apy.core.Element) -> str:
    xml = _mapElement(hl7Element)
    formatted_xml = etree.tostring(xml, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode()
    return formatted_xml

def _mapElement(hl7Element: hl7apy.core.Element) -> Any:
    elementName = hl7Element.name if hl7Element.classname == "Message" else str.replace(str(hl7Element.name), '_', '.')

    xmlElement = etree.Element("{urn:hl7-org:v2xml}%s" % elementName, nsmap={'ns': 'urn:hl7-org:v2xml'}, attrib={})

    if hl7Element.ordered_children and hl7Element.children:
        for child in hl7Element.children:
            xmlElement.append(_mapElement(child))
    else:
        xmlElement.text = hl7Element.to_er7()

    return xmlElement