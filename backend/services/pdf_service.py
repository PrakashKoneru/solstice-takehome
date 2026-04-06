import base64
import json
import os


def extract_text_from_pdf(filepath: str) -> str:
    try:
        import fitz
        doc = fitz.open(filepath)
        return '\n\n'.join(page.get_text() for page in doc)
    except Exception:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        return '\n'.join(page.extract_text() or '' for page in reader.pages)


def render_pdf_pages_as_images(filepath: str, max_pages: int = 15) -> list:
    """Render PDF pages as PNG images at 1.5× zoom. Returns list of (base64_data, mime_type)."""
    try:
        import fitz
    except ImportError:
        return []
    doc = fitz.open(filepath)
    mat = fitz.Matrix(1.5, 1.5)
    result = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(matrix=mat)
        b64 = base64.standard_b64encode(pix.tobytes('png')).decode()
        result.append((b64, 'image/png'))
    return result


def _classify_image_with_claude(client, image_bytes: bytes, ext: str):
    """
    Ask Claude vision to classify a single image.
    Returns { "type": "logo"|"icon"|"image"|"skip", "name": str }
    or None on failure.
    """
    mime = {
        'png': 'image/png',
        'jpeg': 'image/jpeg',
        'jpg': 'image/jpeg',
        'gif': 'image/gif',
        'webp': 'image/webp',
    }.get(ext.lower(), 'image/png')

    b64 = base64.standard_b64encode(image_bytes).decode()

    try:
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=80,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {'type': 'base64', 'media_type': mime, 'data': b64},
                    },
                    {
                        'type': 'text',
                        'text': (
                            'Classify this image extracted from a pharma brand style guide. '
                            'Reply with ONLY valid JSON: {"type":"logo"|"icon"|"image"|"skip","name":"short descriptive name"}. '
                            'Use "logo" for brand/product wordmarks, "icon" for individual icons/symbols, '
                            '"image" for brand graphics/backgrounds/callouts worth keeping, '
                            '"skip" for blank, gradient-only, or decorative noise with no reusable content.'
                        ),
                    },
                ],
            }],
        )
        raw = response.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        result = json.loads(raw)
        if result.get('type') in ('logo', 'icon', 'image', 'skip'):
            return result
    except Exception:
        pass
    return None


def extract_assets_from_pdf(filepath: str, output_dir: str) -> list:
    """
    Extract brand assets from a PDF using Claude vision to classify each image.
    Skips degenerate/noise images. Returns list of { filename, filepath, asset_type, name }.
    """
    try:
        import fitz
    except ImportError:
        return []

    from services.claude_service import _get_client
    client = _get_client()

    doc = fitz.open(filepath)
    seen_xrefs = set()
    assets = []

    for page in doc:
        for img in page.get_images(full=True):
            xref, w, h = img[0], img[2], img[3]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            # Skip genuinely degenerate images before sending to Claude
            if w < 20 or h < 20 or (w * h) < 2000:
                continue

            try:
                pix = doc.extract_image(xref)
            except Exception:
                continue

            ext = pix.get('ext', 'png')
            image_bytes = pix['image']

            classification = _classify_image_with_claude(client, image_bytes, ext)
            if not classification or classification['type'] == 'skip':
                continue

            filename = f'extracted_{xref}_{w}x{h}.{ext}'
            out_path = os.path.join(output_dir, filename)
            with open(out_path, 'wb') as f:
                f.write(image_bytes)

            assets.append({
                'filename': filename,
                'filepath': out_path,
                'asset_type': classification['type'],
                'name': classification.get('name', f'{classification["type"].capitalize()} {xref}'),
            })

    return assets
