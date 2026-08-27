from ..files import EntryKind, FileEntry
from ..types import Permissions


def parse_ls_la(output: str | bytes, *, base: str) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for raw_line in output.splitlines():
        if isinstance(raw_line, bytes):
            line_bytes = raw_line.rstrip(b"\n")
            if not line_bytes or line_bytes.startswith(b"total"):
                continue
            raw_parts = line_bytes.split(maxsplit=8)
            if len(raw_parts) < 9:
                continue
            parts = [part.decode("utf-8", errors="replace") for part in raw_parts]
        else:
            line = raw_line.rstrip("\n")
            if not line or line.startswith("total"):
                continue
            raw_parts = None
            parts = line.split(maxsplit=8)
            if len(parts) < 9:
                continue

        # Typical coreutils format:
        # drwxr-xr-x  2 root root     4096 Jan  1 00:00 dirname
        # -rw-r--r--  1 root root      123 Jan  1 00:00 file.txt
        # lrwxrwxrwx  1 root root       12 Jan  1 00:00 link -> target
        permissions_str = parts[0]
        owner = parts[2]
        group = parts[3]
        size_field = parts[4]

        # Character and block devices report a device identifier in place of the
        # size column, in one of two formats. `stat` reports size 0 for them.
        if permissions_str[:1] in {"c", "b"}:
            size = 0
            if parts[4].endswith(","):
                # GNU coreutils prints "major, minor", which occupies two
                # fields and shifts every following field by one.
                if raw_parts is not None:
                    raw_parts = line_bytes.split(maxsplit=9)
                    parts = [part.decode("utf-8", errors="replace") for part in raw_parts]
                else:
                    parts = line.split(maxsplit=9)
                if len(parts) < 10:
                    continue
                name = parts[9]
            else:
                # BSD ls prints a single hexadecimal identifier, e.g. 0x3000002.
                name = parts[8]
        else:
            try:
                size = int(size_field)
            except ValueError:
                continue
            name = parts[8]

        name_index = 9 if permissions_str[:1] in {"c", "b"} and parts[4].endswith(",") else 8
        raw_name = raw_parts[name_index] if raw_parts is not None else None

        kind_map: dict[str, EntryKind] = {
            "d": EntryKind.DIRECTORY,
            "-": EntryKind.FILE,
            "l": EntryKind.SYMLINK,
        }
        kind: EntryKind = kind_map.get(permissions_str[:1], EntryKind.OTHER)

        # Permissions only track rwx bits and directory-ness; for symlink/other entries we
        # preserve rwx bits by normalizing the leading type marker to "-".
        if permissions_str[:1] not in {"d", "-"} and len(permissions_str) >= 2:
            permissions_str = "-" + permissions_str[1:]

        if kind == EntryKind.SYMLINK and " -> " in name:
            if raw_name is not None:
                target_start = len(raw_name) - size
                separator_start = target_start - len(b" -> ")
                if separator_start >= 0 and raw_name[separator_start:target_start] == b" -> ":
                    name = raw_name[:separator_start].decode("utf-8", errors="replace")
                else:
                    continue
            else:
                delimiter = " -> "
                matches: list[str] = []
                search_start = 0
                while True:
                    separator_start = name.find(delimiter, search_start)
                    if separator_start < 0:
                        break
                    target = name[separator_start + len(delimiter) :]
                    try:
                        encoded_target_length = len(target.encode("utf-8"))
                    except UnicodeEncodeError:
                        search_start = separator_start + len(delimiter)
                        continue

                    if encoded_target_length == size:
                        matches.append(name[:separator_start])
                    elif "\ufffd" in target:
                        # BaseSandboxSession decodes ls output with errors="replace".
                        # Each replacement character represents at least one original byte,
                        # so account for its expanded UTF-8 representation when matching the
                        # byte-sized symlink target.
                        minimum_target_length = encoded_target_length - 2 * target.count("\ufffd")
                        if minimum_target_length <= size <= encoded_target_length:
                            matches.append(name[:separator_start])
                    search_start = separator_start + len(delimiter)

                if len(matches) == 1:
                    name = matches[0]
                else:
                    # The decoded text cannot identify the target boundary when multiple
                    # candidates match the reported byte size. Do not expose the display form
                    # (`name -> target`) as a filesystem path in that case.
                    continue

        if name in {".", ".."}:
            continue

        permissions = Permissions.from_str(permissions_str)
        entry_path = (
            name
            if name.startswith("/")
            else (f"{base.rstrip('/')}/{name}" if base != "/" else f"/{name}")
        )
        entries.append(
            FileEntry(
                path=entry_path,
                permissions=permissions,
                owner=owner,
                group=group,
                size=size,
                kind=kind,
            )
        )

    return entries
