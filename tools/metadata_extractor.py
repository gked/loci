"""Extract metadata from ebook and document files."""

from pathlib import Path


MIME_TYPES = {
    ".epub": "application/epub+zip",
    ".mobi": "application/x-mobipocket-ebook",
    ".azw": "application/vnd.amazon.ebook",
    ".azw3": "application/vnd.amazon.ebook",
    ".pdf": "application/pdf",
    ".djvu": "image/vnd.djvu",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
}


def extract_epub_metadata(path: Path) -> dict:
    """
    Parse EPUB metadata from the OPF file via zipfile + xml.etree.
    Returns {title, author, language, publisher, published_at, identifier}.
    Returns empty dict on any error.
    """
    try:
        import zipfile
        import defusedxml.ElementTree as ET

        with zipfile.ZipFile(str(path), "r") as zf:
            # Find container.xml to get the OPF path
            container_xml = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
            container_root = ET.fromstring(container_xml)
            ns_container = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            rootfile = container_root.find(".//c:rootfile", ns_container)
            if rootfile is None:
                # Try without namespace
                rootfile = container_root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
            if rootfile is None:
                return {}
            opf_path = rootfile.get("full-path", "")
            if not opf_path:
                return {}

            # Guard against path traversal: OPF path must be a known zip member
            if opf_path not in zf.namelist():
                return {}

            opf_data = zf.read(opf_path).decode("utf-8", errors="replace")
            opf_root = ET.fromstring(opf_data)

        # OPF namespaces
        dc_ns = "http://purl.org/dc/elements/1.1/"
        opf_ns = "http://www.idpf.org/2007/opf"

        def find_dc(tag: str) -> str | None:
            el = opf_root.find(f".//{{{dc_ns}}}{tag}")
            return el.text.strip() if el is not None and el.text else None

        result = {}

        title = find_dc("title")
        if title:
            result["title"] = title

        # Creator may have role attribute in OPF namespace
        creator_els = opf_root.findall(f".//{{{dc_ns}}}creator")
        for el in creator_els:
            role = el.get(f"{{{opf_ns}}}role", "")
            if role in ("aut", "") and el.text:
                result["author"] = el.text.strip()
                break
        if "author" not in result and creator_els:
            first = creator_els[0]
            if first.text:
                result["author"] = first.text.strip()

        language = find_dc("language")
        if language:
            result["language"] = language

        publisher = find_dc("publisher")
        if publisher:
            result["publisher"] = publisher

        date = find_dc("date")
        if date:
            result["published_at"] = date

        identifier = find_dc("identifier")
        if identifier:
            result["identifier"] = identifier

        return result

    except Exception as e:
        return {"_extraction_error": f"epub: {e}"}


def extract_pdf_metadata(path: Path) -> dict:
    """
    Extract metadata from a PDF using pypdf.
    Import is inside function so it's optional.
    Returns empty dict if pypdf not installed or any error.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return {}

    try:
        reader = PdfReader(str(path))
        info = reader.metadata or {}
        result = {}

        title = info.get("/Title", "") or info.get("Title", "")
        if title:
            result["title"] = str(title).strip()

        author = info.get("/Author", "") or info.get("Author", "")
        if author:
            result["author"] = str(author).strip()

        publisher = info.get("/Publisher", "") or info.get("Publisher", "")
        if publisher:
            result["publisher"] = str(publisher).strip()

        creation_date = info.get("/CreationDate", "") or info.get("CreationDate", "")
        if creation_date:
            result["published_at"] = str(creation_date).strip()

        return result

    except Exception as e:
        return {"_extraction_error": f"pdf: {e}"}


def extract_from_filename(path: Path) -> dict:
    """
    Fallback metadata extraction from filename.
    If stem contains ' - ', split as 'Author - Title'.
    Otherwise use stem as title (underscores replaced with spaces; hyphens kept).
    Returns {title} or {author, title}.
    """
    stem = path.stem

    if " - " in stem:
        parts = stem.split(" - ", 1)
        author = parts[0].strip()
        title = parts[1].strip()
        return {"author": author, "title": title}
    else:
        title = stem.replace("_", " ").strip()
        return {"title": title}


def extract_metadata(path: Path) -> dict:
    """
    Dispatch metadata extraction by file suffix, fill missing fields from filename fallback.
    Also adds mime_type and format (extension without dot).
    """
    suffix = path.suffix.lower()
    result: dict = {}

    if suffix == ".epub":
        result = extract_epub_metadata(path)
    elif suffix == ".pdf":
        result = extract_pdf_metadata(path)
    # Other formats: rely on filename fallback

    # Fill missing fields from filename
    fallback = extract_from_filename(path)
    for key, val in fallback.items():
        if key not in result or not result[key]:
            result[key] = val

    # Add mime_type and format
    result["mime_type"] = MIME_TYPES.get(suffix, "application/octet-stream")
    result["format"] = suffix.lstrip(".")

    return result
