"""Validate a 23andMe genome zip and parse it with the snps library.

Plaintext raw data stays in memory for the request. Callers encrypt whatever
they keep. The full marker table is not returned — only a count, build,
source, and the few genotypes the trait map knows about.
"""
from __future__ import annotations

import io
import logging
import re
import warnings
import zipfile

from snps import SNPs

import traits

log = logging.getLogger("genemeal.genome")

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
MAX_MEMBERS = 30

PDF_MSG = (
    "This is a PDF, not a 23andMe raw-data zip. Download the genome zip "
    "(usually named genome_….zip), not a health report or a printed summary."
)
IMAGE_MSG = (
    "This looks like an image or screenshot, not raw genotype data. "
    "Upload the genome zip from the 23andMe download email."
)
NEED_ZIP_MSG = (
    "Upload the .zip of your 23andMe raw data. It is usually named genome_….zip. "
    "Do not upload a loose text file, a PDF, or a photo of the page."
)
HEADER_MSG = (
    "This file does not look like 23andMe raw data. Expected comment lines starting "
    "with #, then columns rsid, chromosome, position, and genotype."
)
PARSE_MSG = (
    "The header looks like genotype text, but the marker parser could not read it. "
    "Use the 23andMe raw download: the first line should mention 23andMe and the "
    "column line should be rsid, chromosome, position, genotype."
)

_HEADER_NEEDED = {"rsid", "chromosome", "position", "genotype"}
_DATA_RSID = re.compile(r"^(rs\d+|i\d+)$", re.IGNORECASE)
_DATA_POS = re.compile(r"^\d+$")
_DATA_GT = re.compile(r"^[ACGTDI\-]{0,8}$", re.IGNORECASE)


class Rejected(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _limit_label(n: int) -> str:
    if n >= 1024 * 1024 and n % (1024 * 1024) == 0:
        return f"{n // (1024 * 1024)} MB"
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n} bytes"


def _sniff(data: bytes, filename: str) -> str:
    name = (filename or "").lower()
    if data.startswith(b"%PDF") or name.endswith(".pdf"):
        return "pdf"
    if data.startswith(b"\x89PNG") or name.endswith(".png"):
        return "image"
    if data.startswith(b"\xff\xd8\xff") or name.endswith((".jpg", ".jpeg")):
        return "image"
    if data.startswith((b"GIF87a", b"GIF89a")) or name.endswith(".gif"):
        return "image"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image"
    if data.startswith(b"PK") or name.endswith(".zip"):
        return "zip"
    return "other"


def _is_header(text: str) -> bool:
    cols = [part.strip().lower() for part in re.split(r"[\t,]+", text.strip()) if part.strip()]
    return _HEADER_NEEDED <= set(cols)


def _is_data_row(line: str) -> bool:
    parts = [part.strip() for part in re.split(r"\t|,", line.strip())]
    if len(parts) < 4:
        return False
    if not _DATA_RSID.match(parts[0]):
        return False
    if not _DATA_POS.match(parts[2]):
        return False
    return bool(_DATA_GT.match(parts[3]))


def validate_genome_text(raw: bytes) -> None:
    kind = _sniff(raw, "")
    if kind == "pdf":
        raise Rejected(PDF_MSG)
    if kind == "image":
        raise Rejected(IMAGE_MSG)
    if b"\x00" in raw[:2000]:
        raise Rejected("This file looks binary, not genotype text.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    lines = text.splitlines()
    comments = 0
    header_idx = None
    for i, line in enumerate(lines[:500]):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            comments += 1
            payload = stripped.lstrip("#").strip()
            if _is_header(payload):
                header_idx = i
                break
            continue
        if _is_header(stripped):
            header_idx = i
            break
        break
    if comments < 1 or header_idx is None:
        raise Rejected(HEADER_MSG)
    window = lines[header_idx + 1 : header_idx + 400]
    if not any(_is_data_row(line) for line in window):
        raise Rejected("The file has a genotype header but no rsid data rows.")


def _skip_member(name: str) -> bool:
    base = name.replace("\\", "/").strip()
    if not base or base.endswith("/"):
        return True
    lower = base.lower()
    if lower.startswith("__macosx/") or "/__macosx/" in lower:
        return True
    leaf = lower.rsplit("/", 1)[-1]
    if leaf.startswith(".") or leaf == "ds_store":
        return True
    return False


def _unsafe_name(name: str) -> bool:
    base = name.replace("\\", "/")
    if base.startswith("/") or base.startswith("../") or "/../" in base or base == "..":
        return True
    return any(part == ".." for part in base.split("/"))


def screen_upload(
    filename: str,
    data: bytes,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
    max_uncompressed: int = MAX_UNCOMPRESSED_BYTES,
) -> bytes:
    """Return the genotype text inside a genome zip, or raise Rejected."""
    if not data:
        raise Rejected("That upload was empty.")
    if len(data) > max_bytes:
        raise Rejected(f"This file is over the {_limit_label(max_bytes)} limit.")
    kind = _sniff(data, filename or "")
    if kind == "pdf":
        raise Rejected(PDF_MSG)
    if kind == "image":
        raise Rejected(IMAGE_MSG)
    if kind != "zip":
        raise Rejected(NEED_ZIP_MSG)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise Rejected(
            "That file could not be opened as a zip. Re-download the genome zip "
            "instead of a screenshot or a renamed report."
        ) from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise Rejected("The zip has too many files to be a 23andMe raw-data download.")
        uncompressed = 0
        for info in infos:
            if _unsafe_name(info.filename):
                raise Rejected("The zip contains an unsafe path and was rejected.")
            if info.flag_bits & 0x1:
                raise Rejected(
                    "Password-protected zips are not supported. Upload the standard 23andMe genome zip."
                )
            uncompressed += max(info.file_size, 0)
            if info.file_size > max_uncompressed or uncompressed > max_uncompressed:
                raise Rejected(
                    f"The unzipped data is larger than {_limit_label(max_uncompressed)}."
                )
        saw_pdf = False
        saw_image = False
        errors: list[Rejected] = []
        members = [info for info in infos if not _skip_member(info.filename)]
        members.sort(key=lambda info: (0 if "genome" in info.filename.lower() else 1, info.filename.lower()))
        for info in members:
            with zf.open(info, "r") as handle:
                blob = handle.read(max_uncompressed + 1)
            if len(blob) > max_uncompressed:
                raise Rejected(
                    f"The unzipped data is larger than {_limit_label(max_uncompressed)}."
                )
            inner_kind = _sniff(blob, info.filename)
            if inner_kind == "pdf":
                saw_pdf = True
                continue
            if inner_kind == "image":
                saw_image = True
                continue
            try:
                validate_genome_text(blob)
            except Rejected as exc:
                errors.append(exc)
                continue
            return blob
    if saw_pdf:
        raise Rejected(
            "The zip contains a PDF, not a genotype text file. Upload the raw-data "
            "zip named genome_….zip, not a report export."
        )
    if saw_image:
        raise Rejected(
            "The zip contains an image, not a genotype text file. Upload the raw-data zip, not a screenshot."
        )
    if errors:
        raise errors[0]
    raise Rejected("The zip did not contain a genotype text file.")


def parse_genotype_bytes(text: bytes) -> dict:
    """Parse genotype text with snps into a DataFrame, then keep a small summary."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            parsed = SNPs(text)
        frame = parsed.snps
    except Exception as exc:
        log.info("snps parse failed: %s", type(exc).__name__)
        raise Rejected(PARSE_MSG) from exc
    if frame is None or len(frame) == 0:
        raise Rejected(PARSE_MSG)
    build = int(parsed.build) if parsed.build else None
    if build == 0:
        build = None
    source = parsed.source
    if isinstance(source, (list, tuple)):
        source_name = str(source[0]) if source else ""
    else:
        source_name = str(source or "")
    genotypes: dict[str, str] = {}
    index = frame.index
    for entry in traits.TRAITS:
        rsid = entry["rsid"]
        if rsid not in index:
            continue
        value = frame.at[rsid, "genotype"]
        text_value = "" if value is None else str(value).strip()
        if text_value.lower() in {"", "nan", "none", "--", "-"}:
            continue
        genotypes[rsid] = text_value
    # The DataFrame is local to this call and is not stored.
    return {
        "marker_count": int(len(frame)),
        "build": build,
        "source": source_name,
        "genotypes": genotypes,
    }
