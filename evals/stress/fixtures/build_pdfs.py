"""Generate calibrated synthetic PDFs for the stress runner.

Produces ``attach_{5,20,50,100}kb.pdf`` where the suffix is the size of the
*extracted text* (what ``pypdf`` pulls out), not the bytes on disk: the runner
cares about the prompt budget. Output is deterministic (same paragraph, fixed
creation date), so re-running yields byte-identical PDFs. The PDFs are
git-ignored; only this script is committed.

    uv run python -m evals.stress.fixtures.build_pdfs [--out-dir DIR]
"""

import argparse
import datetime
from collections.abc import Sequence
from pathlib import Path

from fpdf import FPDF
from pypdf import PdfReader

TARGETS_KB = (5, 20, 50, 100)
DEFAULT_DIR = Path(__file__).parent
_FIXED_DATE = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)

_PARAGRAPH = (
    "The supplier portal must replace the existing manual workflow. Vendors "
    "upload PDFs of compliance certificates which the procurement team reviews "
    "for completeness, expiration, and conformance to the company's standard. "
    "Approved suppliers are unlocked for purchase order generation; rejected "
    "suppliers must remediate before the next review cycle. Every state "
    "transition is recorded in an immutable audit log retained for seven years "
    "in compliance with internal policy. Reviewers may attach comments to a "
    "specific certificate; comments are visible to the supplier and form part "
    "of the formal record. The portal must integrate with the legacy ERP for "
    "vendor master data synchronisation, propagating changes within fifteen "
    "minutes. Single sign-on is mandatory for internal users; vendors use "
    "magic-link email authentication scoped to a single tenant. Performance "
    "expectations are P95 page load under two seconds with two hundred "
    "concurrent users, and the system must remain available under one hour of "
    "downtime per quarter excluding planned maintenance windows scheduled "
    "outside business hours. "
)


def pdf_path(out_dir: Path, size_kb: int) -> Path:
    return out_dir / f"attach_{size_kb}kb.pdf"


def _build_pdf(target_kb: int, output_path: Path) -> int:
    """Write a PDF with about ``target_kb`` KB of text. Returns the file size in bytes."""
    pdf = FPDF()
    pdf.set_creation_date(_FIXED_DATE)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)

    target_chars = target_kb * 1024
    text_chars = 0
    while text_chars < target_chars:
        pdf.multi_cell(0, 5, _PARAGRAPH)
        text_chars += len(_PARAGRAPH)
        if text_chars < target_chars:
            pdf.ln(3)

    pdf.output(str(output_path))
    return output_path.stat().st_size


def extracted_chars(path: Path) -> int:
    """Length of the text ``pypdf`` extracts, i.e. what the attachment pipeline sees."""
    reader = PdfReader(str(path))
    return len("\n\n".join(page.extract_text() or "" for page in reader.pages))


def build_all(out_dir: Path = DEFAULT_DIR, sizes: Sequence[int] = TARGETS_KB) -> list[Path]:
    """(Re)generate the PDFs for ``sizes`` into ``out_dir`` and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for kb in sizes:
        path = pdf_path(out_dir, kb)
        _build_pdf(kb, path)
        paths.append(path)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_DIR, help="Where to write the PDFs.")
    args = parser.parse_args(argv)
    print(f"Writing PDFs to: {args.out_dir}")
    for path in build_all(args.out_dir):
        print(f"  {path.name}: file_bytes={path.stat().st_size} pypdf_extracted={extracted_chars(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
