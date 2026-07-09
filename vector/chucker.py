import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = PROJECT_ROOT / "data" / "private" / "sample.md"


def split_by_sections(text):
    lines = text.splitlines()

    chunks = []
    current_title = None
    current_lines = []

    section_pattern = re.compile(r"^\d+\.\s+.+$")

    for line in lines:
        if section_pattern.match(line):
            if current_lines:
                chunks.append(
                    {
                        "section": current_title or "metadata",
                        "text": "\n".join(current_lines).strip(),
                    }
                )

            current_title = line.strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        chunks.append(
            {
                "section": current_title or "metadata",
                "text": "\n".join(current_lines).strip(),
            }
        )

    return chunks


def main():
    text = SAMPLE_PATH.read_text(encoding="utf-8")
    chunks = split_by_sections(text)

    print(f"전체 글자 수: {len(text)}")
    print(f"chunk 개수: {len(chunks)}")
    print()

    for index, chunk in enumerate(chunks, start=1):
        print("=" * 80)
        print(f"chunk {index}")
        print(f"section: {chunk['section']}")
        print("=" * 80)
        print(chunk["text"][:1200])
        print()


if __name__ == "__main__":
    main()