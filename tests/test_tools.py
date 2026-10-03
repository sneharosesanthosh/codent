from codent.tools import MAX_READ_CHARS, run_tool


def test_list_dir(tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    (tmp_path / "sub").mkdir()
    out, err = run_tool(tmp_path, "list_dir", {"path": "."})
    assert not err
    assert out.splitlines() == ["sub/", "a.txt"]


def test_read_file_numbers_lines(tmp_path):
    (tmp_path / "a.txt").write_text("x\ny\n")
    out, err = run_tool(tmp_path, "read_file", {"path": "a.txt"})
    assert not err and out == "1\tx\n2\ty"


def test_read_file_truncates(tmp_path):
    (tmp_path / "big.txt").write_text("a" * (MAX_READ_CHARS + 10))
    out, _ = run_tool(tmp_path, "read_file", {"path": "big.txt"})
    assert out.endswith("(truncated)")


def test_path_escape_rejected(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("nope")
    out, err = run_tool(root, "read_file", {"path": "../secret.txt"})
    assert err and "escapes" in out


def _make_project(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    (tmp_path / "b.txt").write_text("foo bar\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text("x = foo()\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "skip.py").write_text("foo\n")
    (tmp_path / "bin.dat").write_bytes(b"\xff\xfe\x00foo")


def test_search_finds_lines_and_skips_noise(tmp_path):
    _make_project(tmp_path)
    out, err = run_tool(tmp_path, "search", {"pattern": "foo"})
    assert not err
    assert out.splitlines() == ["a.py:1: def foo():", "b.txt:1: foo bar", "sub/c.py:1: x = foo()"]


def test_search_glob_filter(tmp_path):
    _make_project(tmp_path)
    out, _ = run_tool(tmp_path, "search", {"pattern": "foo", "glob": "*.py"})
    assert "b.txt" not in out and "a.py:1" in out


def test_search_no_match_and_bad_regex(tmp_path):
    _make_project(tmp_path)
    assert run_tool(tmp_path, "search", {"pattern": "zzz"}) == ("(no matches)", False)
    out, err = run_tool(tmp_path, "search", {"pattern": "("})
    assert err and "invalid regex" in out


def test_search_result_cap(tmp_path):
    (tmp_path / "big.txt").write_text("hit\n" * 500)
    out, _ = run_tool(tmp_path, "search", {"pattern": "hit"})
    assert "narrow your search" in out and len(out.splitlines()) == 101


def test_search_path_escape_rejected(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    out, err = run_tool(root, "search", {"pattern": "x", "path": ".."})
    assert err and "escapes" in out


def test_find_files(tmp_path):
    _make_project(tmp_path)
    out, _ = run_tool(tmp_path, "find_files", {"pattern": "*.py"})
    assert out.splitlines() == ["a.py", "sub/c.py"]


def test_errors_are_returned_not_raised(tmp_path):
    assert run_tool(tmp_path, "read_file", {"path": "missing"})[1]
    assert run_tool(tmp_path, "nope", {})[1]
    assert run_tool(tmp_path, "read_file", {})[1]
