import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
# Vector 인덱싱 대상 폴더 (graph와 동일 규약: 명시 지정, 비재귀)
#   - data/public/  : 커밋되는 공개 샘플
#   - data/private/ : gitignore되는 비공개 원문
DOCUMENT_SOURCE_DIRS = [DATA_DIR / "public", DATA_DIR / "private"]


def load_documents():
    """지정 폴더의 .md를 [(doc_id, 본문)] 리스트로 반환. doc_id는 data/ 기준 상대경로."""
    documents = []
    for source_dir in DOCUMENT_SOURCE_DIRS:
        if not source_dir.is_dir():
            continue
        for path in sorted(source_dir.glob("*.md")):
            if path.is_symlink():
                continue
            content = path.read_text(encoding="utf-8")
            if content.strip():
                doc_id = path.relative_to(DATA_DIR).with_suffix("").as_posix()
                documents.append((doc_id, content))
    return documents


def split_by_sections(text):
    lines = text.splitlines()

    chunks = []
    current_title = None
    current_lines = []

    section_pattern = re.compile(r"^(?:\d+\.\s+|#{2,6}\s+).+$")

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
    for doc_id, text in load_documents():
        chunks = split_by_sections(text)

        print(f"문서: {doc_id}")
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