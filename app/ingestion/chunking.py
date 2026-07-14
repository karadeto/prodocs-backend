"""Page-aware chunking: split markdown into overlapping chunks for retrieval.

Single-tier by design (the old backend's two-tier chunking added complexity;
the chat agent fetches full document text on demand via its get_document tool).
"""

from app.ingestion.parser import ParsedPage


def _split_page(text: str, target: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= target:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        # Hard-split paragraphs that alone exceed the target.
        while len(para) > target:
            head, para = para[:target], para[max(0, target - overlap):]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if len(current) + len(para) + 2 <= target:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            tail = current[-overlap:] if current else ""
            current = f"{tail}\n\n{para}".strip() if tail else para
    if current:
        chunks.append(current)
    return chunks


def chunk_pages(pages: list[ParsedPage], target: int = 1400, overlap: int = 200) -> list[tuple[int, str]]:
    """Returns (page_number, chunk_text) pairs."""
    out: list[tuple[int, str]] = []
    for page in pages:
        for chunk in _split_page(page.markdown, target, overlap):
            out.append((page.page, chunk))
    return out
