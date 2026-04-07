import base64
import json
import os
import cloudinary
import cloudinary.uploader


def extract_text_from_pdf(filepath: str) -> str:
    try:
        import fitz
        doc = fitz.open(filepath)
        return '\n\n'.join(page.get_text() for page in doc)
    except Exception:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        return '\n'.join(page.extract_text() or '' for page in reader.pages)


def render_pdf_pages_as_images(filepath: str, max_pages: int = 30) -> list:
    """Render PDF pages as PNG images at 1.0× zoom. Returns list of (base64_data, mime_type)."""
    try:
        import fitz
    except ImportError:
        return []
    doc = fitz.open(filepath)
    mat = fitz.Matrix(1.0, 1.0)
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

            # Detect layout captures: strips, full-page images, slide-shaped images
            SLIDE_W, SLIDE_H = 1024, 576
            coverage = (w * h) / (SLIDE_W * SLIDE_H)
            img_aspect = w / h
            slide_aspect = SLIDE_W / SLIDE_H  # 1.78
            aspect = max(w, h) / min(w, h)

            is_strip = aspect > 5
            is_layout = (
                coverage > 0.60
                or (abs(img_aspect / slide_aspect - 1) < 0.20 and coverage > 0.40)
                or (h > w and coverage > 0.50)
            )

            try:
                pix = doc.extract_image(xref)
            except Exception:
                continue

            ext = pix.get('ext', 'png')
            image_bytes = pix['image']

            if is_strip or is_layout:
                # Store as reference without burning a Claude classification call
                filename = f'extracted_{xref}_{w}x{h}.{ext}'
                out_path = os.path.join(output_dir, filename)
                with open(out_path, 'wb') as f:
                    f.write(image_bytes)
                file_url = out_path
                try:
                    result = cloudinary.uploader.upload(
                        out_path,
                        folder='solstice/assets',
                        public_id=f'extracted_{xref}_{w}x{h}',
                        overwrite=True,
                        resource_type='image',
                    )
                    file_url = result['secure_url']
                except Exception:
                    pass
                assets.append({
                    'filename': filename,
                    'filepath': file_url,
                    'asset_type': 'image',
                    'name': f'PDF layout strip {xref}',
                    'source': 'page_render',
                })
                continue

            classification = _classify_image_with_claude(client, image_bytes, ext)
            if not classification or classification['type'] == 'skip':
                continue

            filename = f'extracted_{xref}_{w}x{h}.{ext}'
            out_path = os.path.join(output_dir, filename)
            with open(out_path, 'wb') as f:
                f.write(image_bytes)

            file_url = out_path
            try:
                result = cloudinary.uploader.upload(
                    out_path,
                    folder='solstice/assets',
                    public_id=f'extracted_{xref}_{w}x{h}',
                    overwrite=True,
                    resource_type='image',
                )
                file_url = result['secure_url']
            except Exception:
                pass  # fall back to local path if Cloudinary not configured

            assets.append({
                'filename': filename,
                'filepath': file_url,
                'asset_type': classification['type'],
                'name': classification.get('name', f'{classification["type"].capitalize()} {xref}'),
                'source': 'raster',
            })

    # ── Vector asset pass: find logo/brand graphic pages via page renders ────
    try:
        _extract_vector_assets(doc, client, output_dir, assets)
    except Exception:
        pass  # existing raster assets already collected — safe to swallow

    return assets


def _extract_vector_assets(doc, client, output_dir: str, assets: list) -> None:
    """
    Render each PDF page as a small thumbnail, ask Claude in one call which
    pages contain a standalone logo, wordmark, or key brand graphic, then
    re-render those pages at full resolution and save as assets.
    """
    import fitz as _fitz

    THUMB_ZOOM = 0.3

    # Build thumbnails for all pages
    mat_thumb = _fitz.Matrix(THUMB_ZOOM, THUMB_ZOOM)
    thumbnails = []  # list of (page_index, b64_png)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat_thumb)
        b64 = base64.standard_b64encode(pix.tobytes('png')).decode()
        thumbnails.append((i, b64))

    if not thumbnails:
        return

    # Build a single multi-image Claude message
    content = []
    for page_idx, b64 in thumbnails:
        content.append({
            'type': 'text',
            'text': f'Page {page_idx + 1}:',
        })
        content.append({
            'type': 'image',
            'source': {'type': 'base64', 'media_type': 'image/png', 'data': b64},
        })
    content.append({
        'type': 'text',
        'text': (
            'These are pages from a pharma brand style guide. '
            'Identify every page that contains a standalone logo, wordmark, or key brand graphic '
            '(NOT a full slide layout — only pages where the primary content is an isolated brand asset). '
            'Reply with ONLY valid JSON: {"pages": [{"page": <1-based number>, "type": "logo"|"icon"|"image", "name": "<short descriptive name>"}]}. '
            'Return an empty array if none qualify.'
        ),
    })

    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=512,
        messages=[{'role': 'user', 'content': content}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
    identified = json.loads(raw).get('pages', [])

    if not identified:
        return

    # Re-render qualifying pages at full resolution and upload
    mat_full = _fitz.Matrix(2.0, 2.0)
    for entry in identified:
        page_idx = int(entry['page']) - 1
        if page_idx < 0 or page_idx >= len(doc):
            continue

        asset_type = entry.get('type', 'image')
        if asset_type not in ('logo', 'icon', 'image'):
            asset_type = 'image'

        page = doc[page_idx]
        pix = page.get_pixmap(matrix=mat_full)
        image_bytes = pix.tobytes('png')
        filename = f'page_{page_idx + 1}_vector.png'
        out_path = os.path.join(output_dir, filename)
        with open(out_path, 'wb') as f:
            f.write(image_bytes)

        file_url = out_path
        try:
            result = cloudinary.uploader.upload(
                out_path,
                folder='solstice/assets',
                public_id=f'page_{page_idx + 1}_vector',
                overwrite=True,
                resource_type='image',
            )
            file_url = result['secure_url']
        except Exception:
            pass

        assets.append({
            'filename': filename,
            'filepath': file_url,
            'asset_type': asset_type,
            'name': entry.get('name', f'{asset_type.capitalize()} page {page_idx + 1}'),
            'source': 'page_render',
        })
