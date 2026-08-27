from agents.sandbox.files import EntryKind
from agents.sandbox.util.parse_utils import parse_ls_la


def test_parse_ls_la_matches_replacement_decoded_symlink_targets() -> None:
    target = b"target -> \xff"
    raw_output = (
        b"lrwxrwxrwx 1 root root "
        + str(len(target)).encode()
        + b" Jan 1 00:00 link -> alias -> "
        + target
        + b"\n"
    )

    entries = parse_ls_la(raw_output.decode("utf-8", errors="replace"), base="/workspace/docs")

    assert len(entries) == 1
    assert entries[0].path == "/workspace/docs/link -> alias"
    assert entries[0].kind == EntryKind.SYMLINK


def test_parse_ls_la_uses_raw_bytes_for_symlink_boundaries() -> None:
    target = "target -> 失败".encode()
    output = (
        b"lrwxrwxrwx 1 root root "
        + str(len(target)).encode()
        + b" Jan 1 00:00 link -> alias -> "
        + target
        + b"\n"
    )

    entries = parse_ls_la(output, base="/workspace/docs")

    assert len(entries) == 1
    assert entries[0].path == "/workspace/docs/link -> alias"
    assert entries[0].kind == EntryKind.SYMLINK


def test_parse_ls_la_does_not_raise_for_surrogate_text() -> None:
    output = "lrwxrwxrwx 1 root root 1 Jan 1 00:00 link -> \udcff\n"

    entries = parse_ls_la(output, base="/workspace/docs")

    assert entries == []


def test_parse_ls_la_skips_ambiguous_replacement_decoded_symlinks() -> None:
    target = b"xx -> \xed\xa0\x80"
    output = (
        b"lrwxrwxrwx 1 root root "
        + str(len(target)).encode()
        + b" Jan 1 00:00 link -> "
        + target
        + b"\n"
    )

    entries = parse_ls_la(output.decode("utf-8", errors="replace"), base="/workspace/docs")

    assert entries == []
