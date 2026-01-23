"""Script to ingest knowledge base documents into vector store."""
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vector_store import get_vector_store


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks.

    Args:
        text: Text to chunk
        chunk_size: Target chunk size in characters
        overlap: Overlap between chunks

    Returns:
        List of text chunks
    """
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence end in last 100 chars of chunk
            search_start = max(start, end - 100)
            last_period = text.rfind('.', search_start, end)
            last_newline = text.rfind('\n', search_start, end)

            # Use the latest sentence/paragraph boundary
            boundary = max(last_period, last_newline)
            if boundary > start:
                end = boundary + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks


def ingest_markdown_policies():
    """Ingest markdown policy documents."""
    vector_store = get_vector_store()
    base_path = Path(__file__).parent.parent / "data" / "knowledge_base" / "policies"

    policies = [
        ("billing_policy.md", "billing"),
        ("subscription_policy.md", "subscription"),
        ("account_policy.md", "account"),
    ]

    doc_id = 0

    for filename, category in policies:
        filepath = base_path / filename
        if not filepath.exists():
            print(f"Warning: {filepath} not found")
            continue

        print(f"Ingesting {filename}...")

        with open(filepath) as f:
            content = f.read()

        # Chunk the document
        chunks = chunk_text(content, chunk_size=500, overlap=50)

        # Add to vector store
        for i, chunk in enumerate(chunks):
            vector_store.add_documents(
                documents=[chunk],
                metadatas=[{
                    "source": filename,
                    "category": category,
                    "chunk_index": i,
                    "doc_type": "policy"
                }],
                ids=[f"policy_{category}_{doc_id}"]
            )
            doc_id += 1

        print(f"  Added {len(chunks)} chunks from {filename}")


def ingest_json_faqs():
    """Ingest JSON FAQ documents."""
    vector_store = get_vector_store()
    base_path = Path(__file__).parent.parent / "data" / "knowledge_base" / "faqs"

    faqs = [
        ("billing_faqs.json", "billing"),
        ("feature_faqs.json", "features"),
        ("technical_faqs.json", "technical"),
        ("general_faqs.json", "general"),
    ]

    doc_id = 0

    for filename, category in faqs:
        filepath = base_path / filename
        if not filepath.exists():
            print(f"Warning: {filepath} not found")
            continue

        print(f"Ingesting {filename}...")

        with open(filepath) as f:
            data = json.load(f)

        # Each FAQ is a separate document
        faqs_list = data.get("faqs", [])

        for faq in faqs_list:
            # Combine question and answer
            document = f"Q: {faq['question']}\n\nA: {faq['answer']}"

            vector_store.add_documents(
                documents=[document],
                metadatas=[{
                    "source": filename,
                    "category": category,
                    "faq_id": faq["id"],
                    "doc_type": "faq",
                    "keywords": ",".join(faq.get("keywords", []))
                }],
                ids=[f"faq_{category}_{doc_id}"]
            )
            doc_id += 1

        print(f"  Added {len(faqs_list)} FAQs from {filename}")


def main():
    """Main ingestion function."""
    print("=" * 50)
    print("Knowledge Base Ingestion")
    print("=" * 50)

    vector_store = get_vector_store()

    # Check if collection already has documents
    existing_count = vector_store.count()
    if existing_count > 0:
        response = input(f"\nVector store already contains {existing_count} documents. "
                        f"Reset and re-ingest? (y/n): ")
        if response.lower() == 'y':
            print("Resetting vector store...")
            vector_store.reset()
        else:
            print("Aborting ingestion.")
            return

    print("\n1. Ingesting policy documents...")
    ingest_markdown_policies()

    print("\n2. Ingesting FAQ documents...")
    ingest_json_faqs()

    print("\n" + "=" * 50)
    print(f"Ingestion complete! Total documents: {vector_store.count()}")
    print("=" * 50)


if __name__ == "__main__":
    main()
