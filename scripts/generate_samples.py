"""Generate synthetic PDFs and a labelled manifest; never use customer documents."""

import json
from pathlib import Path

import pymupdf

from backend.examples import examples


def main():
    destination = Path("artifacts/samples")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, example in enumerate(examples()):
        name = example["data"]["document_number"]
        with pymupdf.open() as document:
            document.new_page().insert_text((40, 50), example["text"], fontsize=10)
            document.save(destination / f"{name}.pdf")
            manifest.append({**example, "file": f"{name}.pdf", "scanned": False})
            if index % 3 == 1:
                with pymupdf.open() as scan:
                    page = scan.new_page()
                    page.insert_image(page.rect, pixmap=document[0].get_pixmap(dpi=120))
                    scan.save(destination / f"{name}-scan.pdf")
                manifest.append({**example, "file": f"{name}-scan.pdf", "scanned": True})
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Generated {len(manifest)} synthetic PDFs and labels in {destination}")


if __name__ == "__main__":
    main()
