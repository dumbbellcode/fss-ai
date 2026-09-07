from pre_processing.regulation_parser import Chapter, Regulation, Section, Subsection, parse_regulation


def _subsection(no="1.1.1", text="body") -> Subsection:
    return Subsection(no=no, text=text)


def _chapter(title="GENERAL", no=1, sections=None) -> Chapter:
    return Chapter(no=no, title=title, sections=sections or [])


def _section(no="1.1", text="1.1: Short title") -> Section:
    return Section(no=no, text=text)


def test_chunk_title_uses_title_when_present():
    assert _chapter().get_chunk_title() == "GENERAL"


def test_chunk_title_falls_back_to_number():
    assert _chapter(title="").get_chunk_title() == "1"


def test_get_chunk_header_uses_chapter_title_and_section_text():
    header = _subsection().get_chunk_header(_chapter(), _section())
    assert header == "Chapter: GENERAL\nSection: 1.1: Short title"


def test_get_chunk_header_falls_back_to_chapter_number():
    header = _subsection().get_chunk_header(_chapter(title=""), _section())
    assert header == "Chapter: 1\nSection: 1.1: Short title"


def test_get_chunk_header_prefixes_subsection_chunks():
    from ingestion.chunks_creator import create_chunks

    section = Section(no="1.1", text="1.1: Short title", sub_sections=[_subsection()])
    regulation = Regulation(title="reg", chapters=[_chapter(sections=[section])])
    chunks = create_chunks(regulation)
    assert len(chunks) == 1
    assert chunks[0].text.startswith("Chapter: GENERAL\nSection: 1.1: Short title\n\nbody")


def test_parse_regulation_populates_title_from_regulation_directory(tmp_path):
    regulation_dir = tmp_path / "My Regulation" / "parsed"
    regulation_dir.mkdir(parents=True)
    path = regulation_dir / "Regulation.md"
    path.write_text("CHAPTER 1\nGENERAL\n", encoding="utf-8")

    regulation = parse_regulation(path)

    assert regulation.title == "My Regulation"


def test_parse_regulation_preserves_schedule_text(tmp_path):
    regulation_dir = tmp_path / "My Regulation" / "cleaned"
    regulation_dir.mkdir(parents=True)
    path = regulation_dir / "Regulation.md"
    path.write_text("Schedule 4\nGeneral hygienic requirements.\n", encoding="utf-8")

    regulation = parse_regulation(path)

    assert regulation.schedules[0].name == "Schedule 4"
    assert regulation.schedules[0].text == "General hygienic requirements."
