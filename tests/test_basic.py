"""Basic tests for docx-corpus-kit (no network; uses python-docx to fabricate inputs)."""
import os

from docx import Document

from docx_corpus import core, extract


def _make_docx(path, text):
    d = Document()
    for line in text.split("\n"):
        if line.strip():
            d.add_paragraph(line)
    d.save(path)


def test_base_name():
    assert core.base_name("鸿蒙生态参赛报名表 (1).docx") == "鸿蒙生态参赛报名表"
    assert core.base_name("report.docx") == "report"


def test_classify_default():
    assert core.classify("poetry/a.docx") == "poetry"
    assert core.classify("a.docx") == "root"


def test_classify_rules():
    rules = [["src/*", "source"], ["*report*", "reports"]]
    assert core.classify("src/a.docx", rules) == "source"
    assert core.classify("x/report-final.docx", rules) == "reports"


def test_index_and_search_chinese(tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    _make_docx(str(d / "kite.docx"), "风筝又名纸鸢，意象丰富。")
    _make_docx(str(d / "poem.docx"), "这是一首关于意象的诗。")
    db = str(tmp_path / "corpus.db")
    core.index(str(d), db_path=db)
    r = core.index(str(d), db_path=db, query="意象")
    assert r["total"] == 2
    assert len(r["hits"]) == 2
    r2 = core.index(str(d), db_path=db, query="风筝")
    assert len(r2["hits"]) == 1
    # incremental: unchanged -> 0 new / 0 updated
    r3 = core.index(str(d), db_path=db)
    assert r3["new"] == 0 and r3["updated"] == 0


def test_sync_generates_md(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    md = tmp_path / "md"
    md.mkdir()
    _make_docx(str(src / "note.docx"), "正文内容示例。")
    targets = core.sync(str(src), str(md), make=True)
    assert targets[0]["status"] == "MISSING"
    assert (md / "note.md").exists()
    # second run -> OK (drift check)
    targets2 = core.sync(str(src), str(md), make=True)
    assert targets2[0]["status"] == "OK"


def test_extract_plain(tmp_path):
    d = tmp_path / "doc.docx"
    _make_docx(str(d), "第一行\n第二行")
    assert "第一行" in extract.docx_text_plain(str(d))
