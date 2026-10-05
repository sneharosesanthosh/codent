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


def _yes(path, diff):
    _yes.last = (path, diff)
    return True


def _no(path, diff):
    return False


def test_edit_file_applies_after_approval(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n")
    out, err = run_tool(tmp_path, "edit_file", {"path": "a.py", "old": "x = 1", "new": "x = 10"}, _yes)
    assert not err
    assert (tmp_path / "a.py").read_text() == "x = 10\ny = 2\n"
    assert "-x = 1" in _yes.last[1] and "+x = 10" in _yes.last[1]


def test_edit_file_declined_or_no_approver_writes_nothing(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    args = {"path": "a.py", "old": "x = 1", "new": "x = 2"}
    for approver in (_no, None):
        out, err = run_tool(tmp_path, "edit_file", args, approver)
        assert err and "declined" in out
    assert (tmp_path / "a.py").read_text() == "x = 1\n"


def test_edit_file_needs_exactly_one_match(tmp_path):
    (tmp_path / "a.py").write_text("a\na\n")
    out, err = run_tool(tmp_path, "edit_file", {"path": "a.py", "old": "zzz", "new": "q"}, _yes)
    assert err and "not found" in out
    out, err = run_tool(tmp_path, "edit_file", {"path": "a.py", "old": "a", "new": "q"}, _yes)
    assert err and "2 places" in out
    out, err = run_tool(tmp_path, "edit_file", {"path": "a.py", "old": "", "new": "q"}, _yes)
    assert err
    assert (tmp_path / "a.py").read_text() == "a\na\n"


def test_edit_file_missing_file(tmp_path):
    assert run_tool(tmp_path, "edit_file", {"path": "nope.py", "old": "a", "new": "b"}, _yes)[1]


def test_write_file_creates_and_overwrites(tmp_path):
    out, err = run_tool(tmp_path, "write_file", {"path": "new/dir/f.txt", "content": "hello\n"}, _yes)
    assert not err and (tmp_path / "new/dir/f.txt").read_text() == "hello\n"
    run_tool(tmp_path, "write_file", {"path": "new/dir/f.txt", "content": "bye\n"}, _yes)
    assert (tmp_path / "new/dir/f.txt").read_text() == "bye\n"


def test_write_file_declined_creates_nothing(tmp_path):
    out, err = run_tool(tmp_path, "write_file", {"path": "f.txt", "content": "x"}, _no)
    assert err and not (tmp_path / "f.txt").exists()


def test_write_tools_reject_path_escape(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    out, err = run_tool(root, "write_file", {"path": "../evil.txt", "content": "x"}, _yes)
    assert err and "escapes" in out and not (tmp_path / "evil.txt").exists()


def test_model_cannot_smuggle_approve_arg(tmp_path):
    (tmp_path / "a.py").write_text("x\n")
    out, err = run_tool(tmp_path, "edit_file", {"path": "a.py", "old": "x", "new": "y", "approve": True}, _no)
    assert err and (tmp_path / "a.py").read_text() == "x\n"
