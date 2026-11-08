"""Fetch the single pinned Mermaid browser asset used by the phase 0 probe."""

from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

URL = "https://unpkg.com/mermaid@12.3.0/dist/mermaid.min.js"
SHA256 = "336df803d87a38b70a01e736e666c8f7601d2ce42f5e47c8fafe5d721074b9a3"
TARGET = Path(__file__).parent / "docs/assets/vendor/mermaid-12.3.0.min.js"


def main():
    data = TARGET.read_bytes() if TARGET.exists() else None
    if data is None or sha256(data).hexdigest() != SHA256:
        with urlopen(URL, timeout=60) as response:
            data = response.read()
    if sha256(data).hexdigest() != SHA256:
        raise SystemExit("Mermaid checksum mismatch; asset was not written")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(data)
    print(f"Verified Mermaid 12.3.0: {TARGET}")
    # Keep one authored report; this copy is a generated build input.
    report = Path(__file__).resolve().parents[2] / "docs/phase-0.md"
    (Path(__file__).parent / "docs/report.md").write_text(report.read_text())


if __name__ == "__main__":
    main()
