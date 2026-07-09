from graph.documents import documents


def build_document_chunks():
    """Graph RAG에서 Entity/Relation 추출 대상이 될 문서 단위를 만든다."""
    chunks = []

    for index, (document_id, content) in enumerate(documents.items(), start=1):
        text = content.strip()

        if not text:
            continue

        chunks.append(
            {
                "document_id": document_id,
                "chunk_index": index,
                "text": text,
            }
        )

    return chunks


def print_chunks(chunks):
    for chunk in chunks:
        print("=" * 80)
        print(f"document: {chunk['document_id']}")
        print(f"chunk_index: {chunk['chunk_index']}")
        print("=" * 80)
        print(chunk["text"])
        print()


def main():
    chunks = build_document_chunks()
    print_chunks(chunks)


if __name__ == "__main__":
    main()
