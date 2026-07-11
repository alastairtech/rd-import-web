"""
Filesystem browsing (scoped to IMPORT_ROOT) and the rdimport subprocess wrapper.
"""
import re
import shutil
import uuid
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .config import AUDIO_EXTENSIONS, IMPORT_ROOT, IMPORT_TIMEOUT_SECONDS, RDIMPORT_BIN

UPLOAD_SUBDIR = "_uploads"

_GLOB_UNSAFE = re.compile(r"[\\*?\[\]]")


def sanitize_for_rdimport(name: str) -> str:
    """
    Strips characters rdimport's internal glob(3)-based filespec matching
    treats specially (\\, *, ?, [, ]), replacing each with '_'.

    rdimport does its own wildcard expansion on every filespec argument
    it's given (it #includes <glob.h> directly), quite apart from
    anything the shell does — so a real file whose name happens to
    contain e.g. literal square brackets gets misparsed as a bracket
    character class instead of literal text, and the match silently
    fails ("Unable to open ... skipping"). Backslash-escaping those
    characters does NOT work around it — testing showed rdimport takes
    the backslash literally rather than treating it as an escape
    character — so the only reliable fix is to never hand it a filename
    containing these characters in the first place.
    """
    return _GLOB_UNSAFE.sub("_", name)


class PathSecurityError(Exception):
    """Raised whenever a requested path would escape IMPORT_ROOT."""


def resolve_within_root(relative: str) -> Path:
    """
    Resolves a user-supplied relative path against IMPORT_ROOT and refuses
    to return anything outside it (blocks '../' traversal, symlink escapes, etc).
    """
    candidate = (IMPORT_ROOT / relative.lstrip("/")).resolve()
    try:
        candidate.relative_to(IMPORT_ROOT)
    except ValueError:
        raise PathSecurityError(f"Path '{relative}' escapes the import root")
    return candidate


@dataclass
class BrowseEntry:
    name: str
    is_dir: bool
    rel_path: str


def browse(relative: str = "") -> List[BrowseEntry]:
    target = resolve_within_root(relative)
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist")
    if not target.is_dir():
        raise NotADirectoryError(f"{target} is not a directory")

    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.is_dir() or child.suffix.lower() in AUDIO_EXTENSIONS:
            rel = str(child.relative_to(IMPORT_ROOT))
            entries.append(BrowseEntry(name=child.name, is_dir=child.is_dir(), rel_path=rel))
    return entries


def collect_audio_files(paths: List[str], recursive: bool) -> List[Path]:
    """
    Given a list of relative paths (each either a file or a folder), return
    the deduplicated list of audio files to import. Files are included
    directly; folders are expanded (recursively if requested).
    """
    all_files: List[Path] = []
    seen = set()

    for relative in paths:
        target = resolve_within_root(relative)
        if not target.exists():
            raise FileNotFoundError(f"{target} does not exist")

        if target.is_file():
            if target.suffix.lower() not in AUDIO_EXTENSIONS:
                raise ValueError(f"{target.name} is not a recognized audio file")
            found = [target]
        else:
            pattern_iter = target.rglob("*") if recursive else target.glob("*")
            found = sorted(
                p for p in pattern_iter if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
            )
            if not found:
                raise ValueError(f"No audio files found under {target}")

        for f in found:
            if f not in seen:
                seen.add(f)
                all_files.append(f)

    if not all_files:
        raise ValueError("No audio files selected")
    return all_files


def save_uploaded_files(filenames_and_data) -> tuple[str, List[str]]:
    """
    Saves a batch of uploaded (filename, bytes) pairs into a fresh staging
    directory under IMPORT_ROOT/_uploads/<uuid>/. Returns the staging dir's
    relative path (for later cleanup) and the list of relative file paths
    (for use as normal import paths).

    Only the file's basename is trusted — any directory components in a
    supplied filename are stripped, since browsers can't be relied on not
    to send one and we never want an upload to write outside the staging dir.
    """
    staging_rel = f"{UPLOAD_SUBDIR}/{uuid.uuid4().hex}"
    staging_dir = IMPORT_ROOT / staging_rel
    staging_dir.mkdir(parents=True, exist_ok=False)

    saved_rel_paths = []
    used_names = set()
    for filename, data in filenames_and_data:
        base = Path(filename).name  # strip any directory components
        if not base:
            continue
        if Path(base).suffix.lower() not in AUDIO_EXTENSIONS:
            continue  # skip non-audio files silently (e.g. .DS_Store, images)

        base = sanitize_for_rdimport(base)

        candidate = base
        n = 1
        while candidate in used_names:
            stem = Path(base).stem
            suffix = Path(base).suffix
            candidate = f"{stem}_{n}{suffix}"
            n += 1
        used_names.add(candidate)

        (staging_dir / candidate).write_bytes(data)
        saved_rel_paths.append(f"{staging_rel}/{candidate}")

    if not saved_rel_paths:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise ValueError("No recognized audio files were in the upload")

    return staging_rel, saved_rel_paths


def cleanup_staging_dir(staging_rel: str) -> None:
    """Removes a staging directory created by save_uploaded_files. Refuses
    to touch anything outside _uploads/ as a safety guard."""
    if not staging_rel.startswith(f"{UPLOAD_SUBDIR}/"):
        return
    target = resolve_within_root(staging_rel)
    shutil.rmtree(target, ignore_errors=True)


@dataclass
class ImportResult:
    command: List[str] = field(default_factory=list)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    skipped_count: int = 0


def run_rdimport(
    group: str,
    files: List[Path],
    cart_number: int = 0,
    delete_source: bool = False,
    delete_cuts: bool = False,
    scheduler_codes: List[str] | None = None,
    normalization_level: int | None = None,
    autotrim_level: int | None = None,
    segue_level: int | None = None,
    fix_broken_formats: bool = False,
    startdate_offset: int | None = None,
    enddate_offset: int | None = None,
) -> ImportResult:
    """
    Invokes rdimport for the given group against one or more files.

    rdimport's syntax is: rdimport [options] <group> <file> [<file> ...]
    There is no positional cart-number argument — by default it
    auto-assigns the next free cart in the group's range. To target a
    specific cart, pass cart_number and it's translated to --to-cart=N
    (only valid/sensible for a single-file import).

    When targeting an existing cart, delete_cuts controls whether its
    current cuts are wiped first (--delete-cuts) or the new audio is
    simply added alongside them (rdimport's default with the flag absent).
    """
    cmd = [RDIMPORT_BIN, "--verbose"]
    if delete_source:
        cmd.append("--delete-source")
    if delete_cuts:
        cmd.append("--delete-cuts")
    if fix_broken_formats:
        cmd.append("--fix-broken-formats")
    for code in scheduler_codes or []:
        if code:
            cmd.append(f"--add-scheduler-code={code}")
    if normalization_level is not None:
        cmd.append(f"--normalization-level={normalization_level}")
    if autotrim_level is not None:
        cmd.append(f"--autotrim-level={autotrim_level}")
    if segue_level is not None:
        cmd.append(f"--segue-level={segue_level}")
    if startdate_offset is not None:
        cmd.append(f"--startdate-offset={startdate_offset}")
    if enddate_offset is not None:
        cmd.append(f"--enddate-offset={enddate_offset}")
    if cart_number:
        cmd.append(f"--to-cart={cart_number}")
    cmd.append(group)
    cmd += [str(f) for f in files]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=IMPORT_TIMEOUT_SECONDS,
    )
    # rdimport can exit 0 even when it skipped one or more files it
    # couldn't open — the exit code alone isn't a reliable success signal,
    # so we also scan its own stdout for the phrase it uses when this
    # happens.
    skipped_count = proc.stdout.count("Unable to open")

    return ImportResult(
        command=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        skipped_count=skipped_count,
    )
