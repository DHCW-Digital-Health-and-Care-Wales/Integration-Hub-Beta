import unittest

from ultra7.formats.structure import (
    filter_structure_nodes,
    find_deepest_node,
    parse_hl7_structure,
    parse_json_structure,
    parse_structure,
    parse_xml_structure,
)


class TestHl7Structure(unittest.TestCase):
    def test_parses_segments_fields_components_and_exact_offsets(self) -> None:
        msg = (
            "MSH|^~\\&|PHW|SITE|MPI|DHCW|20250101||ADT^A01|0001|P|2.5\n"
            "PID|1||12345^^^NHS^NH~99999^^^LOCAL||DOE^JOHN&J"
        )
        nodes = parse_hl7_structure(msg)
        self.assertEqual([n.label for n in nodes], ["MSH", "PID"])

        msh, pid = nodes
        self.assertEqual(msg[msh.start : msh.end], msg.splitlines()[0])
        self.assertEqual(msg[pid.start : pid.end], msg.splitlines()[1])

        msh_by_label = {c.label: c for c in msh.children}
        self.assertEqual(msg[msh_by_label["MSH-1"].start : msh_by_label["MSH-1"].end], "|")
        self.assertEqual(msg[msh_by_label["MSH-2"].start : msh_by_label["MSH-2"].end], "^~\\&")
        self.assertEqual(msg[msh_by_label["MSH-9"].start : msh_by_label["MSH-9"].end], "ADT^A01")
        self.assertEqual([c.label for c in msh_by_label["MSH-9"].children], ["MSH-9.1", "MSH-9.2"])
        self.assertEqual(
            msg[msh_by_label["MSH-9"].children[1].start : msh_by_label["MSH-9"].children[1].end],
            "A01",
        )

        pid_by_label = {c.label: c for c in pid.children}
        # PID-3 has repetitions (~) and components (^)
        self.assertEqual([r.label for r in pid_by_label["PID-3"].children], ["PID-3[1]", "PID-3[2]"])
        rep1 = pid_by_label["PID-3"].children[0]
        self.assertEqual(msg[rep1.start : rep1.end], "12345^^^NHS^NH")

        # PID-5 has components (^) and subcomponents (&)
        pid5 = pid_by_label["PID-5"]
        self.assertEqual([c.label for c in pid5.children], ["PID-5.1", "PID-5.2"])
        john_node = pid5.children[1]
        self.assertEqual([s.label for s in john_node.children], ["PID-5.2.1", "PID-5.2.2"])
        self.assertEqual(msg[john_node.children[0].start : john_node.children[0].end], "JOHN")
        self.assertEqual(msg[john_node.children[1].start : john_node.children[1].end], "J")

    def test_find_deepest_node_in_hl7(self) -> None:
        msg = "MSH|^~\\&|PHW|SITE\nPID|1||12345||DOE^JOHN"
        nodes = parse_hl7_structure(msg)
        offset = msg.index("JOHN") + 2
        found = find_deepest_node(nodes, offset)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.label, "PID-5.2")
        self.assertEqual(msg[found.start : found.end], "JOHN")


class TestXmlStructure(unittest.TestCase):
    def test_parses_elements_attributes_and_exact_offsets(self) -> None:
        xml = '<Patient id="42">\n  <Name lang="en">Jane Doe</Name>\n  <Active/>\n</Patient>'
        nodes, error = parse_xml_structure(xml)
        self.assertIsNone(error)
        self.assertEqual(len(nodes), 1)

        root = nodes[0]
        self.assertEqual(root.label, "<Patient>")
        self.assertEqual(xml[root.start : root.end], xml)

        child_labels = [c.label for c in root.children]
        self.assertEqual(child_labels, ["@id", "<Name>", "<Active>"])

        id_attr = root.children[0]
        self.assertEqual(xml[id_attr.start : id_attr.end], 'id="42"')

        name_el = root.children[1]
        self.assertEqual(name_el.value, "Jane Doe")
        self.assertEqual(xml[name_el.start : name_el.end], '<Name lang="en">Jane Doe</Name>')

        active_el = root.children[2]
        self.assertEqual(xml[active_el.start : active_el.end], "<Active/>")

    def test_handles_unicode_offsets(self) -> None:
        xml = "<Note><Text>Cymru — £10</Text></Note>"
        nodes, error = parse_xml_structure(xml)
        self.assertIsNone(error)
        text_node = nodes[0].children[0]
        self.assertEqual(xml[text_node.start : text_node.end], "<Text>Cymru — £10</Text>")

    def test_malformed_xml_returns_error(self) -> None:
        nodes, error = parse_xml_structure("<Broken><Unclosed>")
        self.assertEqual(nodes, [])
        self.assertIsNotNone(error)

    def test_find_deepest_node_in_xml(self) -> None:
        xml = '<Patient id="42"><Name>Jane</Name></Patient>'
        nodes, _ = parse_xml_structure(xml)
        found = find_deepest_node(nodes, xml.index("Jane") + 1)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.label, "<Name>")


class TestJsonStructure(unittest.TestCase):
    def test_parses_json_with_exact_offsets(self) -> None:
        raw = '{"patient": {"name": "Jane", "ids": [101, 202]}}'
        nodes, error = parse_json_structure(raw)
        self.assertIsNone(error)
        self.assertEqual(len(nodes), 1)
        found = find_deepest_node(nodes, raw.index("202"))
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.label, "[1]")
        self.assertEqual(raw[found.start : found.end], "202")

    def test_parse_structure_dispatches_by_format(self) -> None:
        nodes, error = parse_structure("<A/>", "xml")
        self.assertIsNone(error)
        self.assertEqual(nodes[0].label, "<A>")

    def test_hl7_descriptions_paths_and_filter(self) -> None:
        msg = "MSH|^~\\&|PHW|SITE|MPI|DHCW|20250101||ADT^A01|0001|P|2.5\nPID|1||9991234567||DOE^JOHN"
        nodes = parse_hl7_structure(msg)
        self.assertEqual(nodes[0].description, "Message Header")
        pid_node = nodes[1]
        pid5 = next(c for c in pid_node.children if c.label == "PID-5")
        self.assertEqual(pid5.description, "Patient Name")
        self.assertEqual(pid5.children[1].description, "Given Name")
        self.assertEqual(pid5.children[1].path, "PID-5.2")
        self.assertTrue(pid5.children[1].editable)

        filtered = filter_structure_nodes(nodes, "given name")
        self.assertEqual([n.label for n in filtered], ["PID"])
        self.assertEqual([c.label for c in filtered[0].children], ["PID-5"])

    def test_xml_and_json_paths_and_editable_ranges(self) -> None:
        xml = '<Patient id="42"><Name>Jane</Name></Patient>'
        x_nodes, _ = parse_xml_structure(xml)
        id_attr = x_nodes[0].children[0]
        name_el = x_nodes[0].children[1]
        self.assertEqual(id_attr.path, "/Patient/@id")
        assert id_attr.value_start is not None and id_attr.value_end is not None
        self.assertEqual(xml[id_attr.value_start : id_attr.value_end], "42")
        self.assertEqual(name_el.path, "/Patient/Name")
        assert name_el.value_start is not None and name_el.value_end is not None
        self.assertEqual(xml[name_el.value_start : name_el.value_end], "Jane")

        raw = '{"patient": {"name": "Jane"}}'
        j_nodes, _ = parse_json_structure(raw)
        leaf = find_deepest_node(j_nodes, raw.index("Jane"))
        assert leaf is not None and leaf.value_start is not None and leaf.value_end is not None
        self.assertEqual(leaf.path, "$.patient.name")
        self.assertEqual(raw[leaf.value_start : leaf.value_end], "Jane")


if __name__ == "__main__":
    unittest.main()
