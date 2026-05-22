"""Tests for USC XML parsing."""

from pathlib import Path

from legal_mcp.data.usc_parser import parse_usc_xml


def write_usc_xml(tmp_path: Path, body: str) -> Path:
    xml_path = tmp_path / "usc42.xml"
    xml_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<uscDoc xmlns="http://xml.house.gov/schemas/uslm/1.0">
  <title>
    <num value="42">Title 42</num>
    {body}
  </title>
</uscDoc>
""",
        encoding="utf-8",
    )
    return xml_path


def test_parse_usc_xml_extracts_nested_codified_body_without_notes(tmp_path: Path):
    write_usc_xml(
        tmp_path,
        """
    <section identifier="/us/usc/t42/s299b">
      <num value="299b">§ 299b.</num>
      <heading>Health care outcome improvement research</heading>
      <subsection identifier="/us/usc/t42/s299b/a">
        <num value="a">(a)</num>
        <heading>Evidence rating systems</heading>
        <content>
          <p>In collaboration with experts, the Agency shall identify evidence rating systems.</p>
        </content>
      </subsection>
      <subsection identifier="/us/usc/t42/s299b/b">
        <num value="b">(b)</num>
        <heading>Health care improvement research centers</heading>
        <paragraph identifier="/us/usc/t42/s299b/b/1">
          <num value="1">(1)</num>
          <heading>In general</heading>
          <chapeau>The Agency shall employ research strategies including—</chapeau>
          <subparagraph identifier="/us/usc/t42/s299b/b/1/A">
            <num value="A">(A)</num>
            <content>health care improvement research centers;</content>
          </subparagraph>
          <subparagraph identifier="/us/usc/t42/s299b/b/1/B">
            <num value="B">(B)</num>
            <content>provider-based research networks.</content>
          </subparagraph>
          <continuation>and which could result in improved patient safety, health care quality, or health care outcomes; or</continuation>
        </paragraph>
      </subsection>
      <sourceCredit>(July 1, 1944, ch. 373, title IX, § 911.)</sourceCredit>
      <notes>
        <note topic="editorial">
          <heading>Editorial Notes</heading>
          <p>This editorial note should not be part of section text.</p>
        </note>
        <note topic="miscellaneous">
          <heading>Construction</heading>
          <p>This miscellaneous note is stored separately.</p>
        </note>
      </notes>
    </section>
""",
    )

    section = next(parse_usc_xml(tmp_path, titles={"42"}))

    assert section["title"] == "42"
    assert section["section"] == "299b"
    assert section["heading"] == "Health care outcome improvement research"
    assert "(a) Evidence rating systems" in section["text"]
    assert "In collaboration with experts" in section["text"]
    assert "(1) In general" in section["text"]
    assert "The Agency shall employ research strategies including" in section["text"]
    assert "(A)" in section["text"]
    assert "health care improvement research centers" in section["text"]
    assert "provider-based research networks" in section["text"]
    assert "which could result in improved patient safety" in section["text"]
    assert "July 1, 1944" not in section["text"]
    assert "editorial note" not in section["text"]
    assert "miscellaneous note" not in section["text"]
    assert section["notes"] is not None
    assert "This miscellaneous note is stored separately." in section["notes"]
    assert "This editorial note should not be part of section text." not in section["notes"]


def test_parse_usc_xml_keeps_direct_content_and_recursive_heading(tmp_path: Path):
    write_usc_xml(
        tmp_path,
        """
    <section identifier="/us/usc/t42/s1">
      <num value="1">§ 1.</num>
      <heading>Repealed. <ref href="/us/pl/1/1">Pub. L. 1-1</ref></heading>
      <content>
        <p>Direct section-level content remains supported.</p>
      </content>
    </section>
""",
    )

    section = next(parse_usc_xml(tmp_path, titles={"42"}))

    assert section["heading"] == "Repealed. Pub. L. 1-1"
    assert section["text"] == "Direct section-level content remains supported."


def test_parse_usc_xml_does_not_emit_note_sections_as_usc_sections(tmp_path: Path):
    write_usc_xml(
        tmp_path,
        """
    <section identifier="/us/usc/t42/s100">
      <num value="100">§ 100.</num>
      <heading>Main section</heading>
      <content><p>Main codified text.</p></content>
      <notes>
        <note topic="miscellaneous">
          <section>
            <num value="1">Section 1.</num>
            <heading>Uncodified note section</heading>
            <content>Note section text.</content>
          </section>
        </note>
      </notes>
    </section>
""",
    )

    sections = list(parse_usc_xml(tmp_path, titles={"42"}))

    assert len(sections) == 1
    assert sections[0]["section"] == "100"
