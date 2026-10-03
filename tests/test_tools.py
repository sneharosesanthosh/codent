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


def test_errors_are_returned_not_raised(tmp_path):
    assert run_tool(tmp_path, "read_file", {"path": "missing"})[1]
    assert run_tool(tmp_path, "nope", {})[1]
    assert run_tool(tmp_path, "read_file", {})[1]
