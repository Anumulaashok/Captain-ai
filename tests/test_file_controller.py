"""actions/file_controller._is_safe_path is the guard that keeps LLM-parsed file
paths from escaping the user's home directory. It's the single highest-value pure
function to protect with tests, since actions/file_processor.py (a sibling file that
had NO such check until this session) reuses it directly now."""
from pathlib import Path

from actions.file_controller import _is_safe_path


def test_home_directory_itself_is_safe():
    assert _is_safe_path(Path.home()) is True


def test_file_inside_home_is_safe():
    assert _is_safe_path(Path.home() / "Desktop" / "notes.txt") is True


def test_nested_path_inside_home_is_safe():
    assert _is_safe_path(Path.home() / "a" / "b" / "c" / "file.txt") is True


def test_root_etc_passwd_is_unsafe():
    assert _is_safe_path(Path("/etc/passwd")) is False


def test_traversal_out_of_home_is_unsafe():
    # .. that resolves to outside home must be rejected, not naively string-matched.
    outside = Path.home() / ".." / ".." / "etc" / "passwd"
    assert _is_safe_path(outside) is False


def test_sibling_directory_with_home_as_prefix_is_unsafe():
    # A classic path-check bug: "/Users/alice-evil" starts with "/Users/alice" as a
    # string, but is not actually inside it. is_relative_to must reject this, not a
    # naive str.startswith().
    home = Path.home()
    lookalike = home.parent / (home.name + "-evil") / "secrets.txt"
    assert _is_safe_path(lookalike) is False
