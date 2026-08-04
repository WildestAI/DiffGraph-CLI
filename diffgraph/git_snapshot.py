"""Resolve exact Git object identities for index and working-tree changes.

This module deliberately models only the two local snapshot pairs:

* staged: ``HEAD`` -> index
* unstaged: index -> working tree

Commit/range resolution belongs to a separate layer.  Paths returned by Git are
read using its NUL-delimited raw format, so tabs, newlines, and other unusual
filename bytes are not delimiters.
"""

from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SnapshotEntry:
    """One changed path pair and its exact pre/post Git identities.

    ``status`` is Git's one-letter raw status (``A``, ``M``, ``D``, ``R``,
    ``C``, or ``T``).  A path, mode, or object ID is ``None`` when that side of
    the change does not exist.  Object IDs are full-length hexadecimal IDs.
    """

    status: str
    old_path: Optional[str]
    new_path: Optional[str]
    old_mode: Optional[str]
    new_mode: Optional[str]
    old_oid: Optional[str]
    new_oid: Optional[str]


@dataclass(frozen=True)
class ResolutionWarning:
    """A structured, non-fatal reason a snapshot entry was not resolved."""

    code: str
    message: str
    path: Optional[str] = None


@dataclass(frozen=True)
class SnapshotResolution:
    """Deterministically ordered entries plus any resolver warnings."""

    entries: Tuple[SnapshotEntry, ...]
    warnings: Tuple[ResolutionWarning, ...]


@dataclass(frozen=True)
class _RawEntry:
    status: str
    old_path: Optional[str]
    new_path: Optional[str]
    old_mode: Optional[str]
    new_mode: Optional[str]
    old_oid: Optional[str]
    new_oid: Optional[str]


def resolve_staged(
    repository: str, pathspecs: Optional[Sequence[str]] = None
) -> SnapshotResolution:
    """Resolve changes from ``HEAD`` to the index.

    ``pathspecs`` are passed verbatim after Git's ``--`` separator.  In
    particular, a non-empty scope is never replaced with a repository-wide
    query if it has no matches.
    """

    return _resolve(repository, pathspecs, staged=True)


def resolve_unstaged(
    repository: str, pathspecs: Optional[Sequence[str]] = None
) -> SnapshotResolution:
    """Resolve tracked changes from the index to the working tree.

    Git does not include ordinary untracked files in this diff.  For each
    post-change regular file, the object ID is computed with ``git
    hash-object --path`` so clean filters and attributes match ``git add``
    semantics without modifying the index.
    """

    return _resolve(repository, pathspecs, staged=False)


def _resolve(
    repository: str, pathspecs: Optional[Sequence[str]], staged: bool
) -> SnapshotResolution:
    warnings: List[ResolutionWarning] = []
    root = _repository_root(repository, warnings)
    if root is None:
        return SnapshotResolution((), tuple(warnings))

    command = ["git", "diff"]
    if staged:
        command.append("--cached")
    command.extend(
        ["--raw", "-z", "--no-abbrev", "--no-ext-diff", "--find-renames=50%"]
    )
    if pathspecs:
        command.append("--")
        command.extend(pathspecs)

    output = _run(command, root, warnings, "git_diff_failed")
    if output is None:
        return SnapshotResolution((), tuple(warnings))

    raw_entries = _parse_raw(output, warnings)
    entries: List[SnapshotEntry] = []
    for raw in raw_entries:
        if staged:
            entry = _exact_staged_entry(raw, warnings)
        else:
            entry = _exact_unstaged_entry(root, raw, warnings)
        if entry is not None:
            entries.append(entry)

    entries.sort(key=_entry_sort_key)
    return SnapshotResolution(tuple(entries), tuple(warnings))


def _repository_root(
    repository: str, warnings: List[ResolutionWarning]
) -> Optional[str]:
    output = _run(
        ["git", "rev-parse", "--show-toplevel"],
        os.fspath(repository),
        warnings,
        "not_a_git_repository",
    )
    if output is None:
        return None
    return os.fsdecode(output.rstrip(b"\n"))


def _run(
    command: Sequence[str],
    cwd: str,
    warnings: List[ResolutionWarning],
    code: str,
    input_bytes: Optional[bytes] = None,
    path: Optional[str] = None,
) -> Optional[bytes]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except (OSError, ValueError) as error:
        warnings.append(ResolutionWarning(code, str(error), path))
        return None

    if completed.returncode != 0:
        detail = os.fsdecode(completed.stderr).strip()
        message = detail or "Git command exited with status {}".format(completed.returncode)
        warnings.append(ResolutionWarning(code, message, path))
        return None
    return completed.stdout


def _parse_raw(data: bytes, warnings: List[ResolutionWarning]) -> List[_RawEntry]:
    fields = data.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()

    parsed: List[_RawEntry] = []
    index = 0
    while index < len(fields):
        header = fields[index]
        index += 1
        try:
            metadata = header[1:].split(b" ") if header.startswith(b":") else []
            if len(metadata) != 5:
                raise ValueError("malformed raw-diff metadata")
            old_mode_b, new_mode_b, old_oid_b, new_oid_b, status_b = metadata
            status_text = status_b.decode("ascii")
            status = status_text[:1]
            path_count = 2 if status in ("R", "C") else 1
            if not status or index + path_count > len(fields):
                raise ValueError("malformed raw-diff path fields")
            paths = [os.fsdecode(value) for value in fields[index : index + path_count]]
            index += path_count

            if status in ("R", "C"):
                old_path, new_path = paths
            elif status == "A":
                old_path, new_path = None, paths[0]
            elif status == "D":
                old_path, new_path = paths[0], None
            else:
                old_path = new_path = paths[0]

            parsed.append(
                _RawEntry(
                    status=status,
                    old_path=old_path,
                    new_path=new_path,
                    old_mode=_mode(old_mode_b),
                    new_mode=_mode(new_mode_b),
                    old_oid=_oid(old_oid_b),
                    new_oid=_oid(new_oid_b),
                )
            )
        except (UnicodeDecodeError, ValueError) as error:
            warnings.append(
                ResolutionWarning("malformed_git_output", str(error), None)
            )
            # Record boundaries are no longer trustworthy.  Returning the
            # successfully parsed prefix avoids inventing changes.
            break
    return parsed


def _mode(value: bytes) -> Optional[str]:
    text = value.decode("ascii")
    return None if not text or set(text) == {"0"} else text


def _oid(value: bytes) -> Optional[str]:
    text = value.decode("ascii")
    return None if not text or set(text) == {"0"} else text


def _exact_staged_entry(
    raw: _RawEntry, warnings: List[ResolutionWarning]
) -> Optional[SnapshotEntry]:
    if (raw.old_path is not None and raw.old_oid is None) or (
        raw.new_path is not None and raw.new_oid is None
    ):
        warnings.append(
            ResolutionWarning(
                "missing_object_id",
                "Git did not provide an exact staged object ID",
                raw.new_path or raw.old_path,
            )
        )
        return None
    return SnapshotEntry(**raw.__dict__)


def _exact_unstaged_entry(
    root: str, raw: _RawEntry, warnings: List[ResolutionWarning]
) -> Optional[SnapshotEntry]:
    if raw.old_path is not None and raw.old_oid is None:
        warnings.append(
            ResolutionWarning(
                "missing_object_id",
                "Git did not provide an exact index object ID",
                raw.old_path,
            )
        )
        return None

    new_oid = raw.new_oid
    if raw.new_path is not None:
        new_oid = _working_tree_oid(root, raw.new_path, raw.new_mode, warnings)
        if new_oid is None:
            return None

    return SnapshotEntry(
        status=raw.status,
        old_path=raw.old_path,
        new_path=raw.new_path,
        old_mode=raw.old_mode,
        new_mode=raw.new_mode,
        old_oid=raw.old_oid,
        new_oid=new_oid,
    )


def _working_tree_oid(
    root: str,
    path: str,
    mode: Optional[str],
    warnings: List[ResolutionWarning],
) -> Optional[str]:
    full_path = os.path.join(root, path)
    try:
        before = os.lstat(full_path)
        if mode == "120000" and stat.S_ISLNK(before.st_mode):
            content = os.fsencode(os.readlink(full_path))
        elif mode in ("100644", "100755") and stat.S_ISREG(before.st_mode):
            with open(full_path, "rb") as handle:
                content = handle.read()
                opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise OSError("working-tree file changed while it was opened")
        else:
            warnings.append(
                ResolutionWarning(
                    "unsupported_worktree_entry",
                    "Cannot derive a Git blob ID for working-tree mode {}".format(mode),
                    path,
                )
            )
            return None
        after = os.lstat(full_path)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise OSError("working-tree file changed while it was hashed")
    except OSError as error:
        warnings.append(ResolutionWarning("worktree_read_failed", str(error), path))
        return None

    output = _run(
        ["git", "hash-object", "--stdin", "--path={}".format(path)],
        root,
        warnings,
        "hash_object_failed",
        input_bytes=content,
        path=path,
    )
    if output is None:
        return None
    oid = os.fsdecode(output).strip()
    if not oid or any(character not in "0123456789abcdef" for character in oid):
        warnings.append(
            ResolutionWarning("malformed_hash_object_output", "Git returned an invalid object ID", path)
        )
        return None
    return oid


def _entry_sort_key(entry: SnapshotEntry) -> Tuple[bytes, bytes, str]:
    return (
        os.fsencode(entry.old_path or ""),
        os.fsencode(entry.new_path or ""),
        entry.status,
    )
