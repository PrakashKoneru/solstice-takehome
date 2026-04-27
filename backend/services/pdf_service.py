import base64
import json
import os
import cloudinary
import cloudinary.uploader


def extract_text_by_page(filepath: str) -> list:
    """Return [{"page_number": 1, "text": "..."}, ...] for each page."""
    try:
        import fitz
        doc = fitz.open(filepath)
        return [{"page_number": i + 1, "text": page.get_text()} for i, page in enumerate(doc)]
    except Exception:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        return [{"page_number": i + 1, "text": page.extract_text() or ''} for i, page in enumerate(reader.pages)]


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
    Extract brand assets from a PDF using docling layout analysis (DocLayNet).
    Detected figure/picture regions are cropped and saved directly — no Claude Vision
    calls needed for classification. Returns list of { filename, filepath, asset_type, name }.
    """
    print(f"[ASSETS] Starting docling asset extraction for: {filepath}")
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.document import PictureItem
        print("[ASSETS] Docling imports successful")
    except ImportError as e:
        print(f"[ASSETS] ERROR: docling import failed: {e}")
        return []

    pipeline_options = PdfPipelineOptions(
        generate_picture_images=True,
        images_scale=2.0,
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )

    print("[ASSETS] Running docling converter.convert()...")
    try:
        result = converter.convert(filepath)
        print(f"[ASSETS] Conversion complete. Document has {len(list(result.document.iterate_items()))} items total")
    except Exception as e:
        print(f"[ASSETS] ERROR: converter.convert() failed: {e}")
        import traceback
        traceback.print_exc()
        return []

    assets = []
    fig_idx = 0
    skipped_no_image = 0

    for item, _level in result.document.iterate_items():
        item_type = type(item).__name__
        if not isinstance(item, PictureItem):
            continue
        if item.image is None:
            skipped_no_image += 1
            print(f"[ASSETS] PictureItem on page {item.prov[0].page_no if item.prov else '?'} has no image data, skipping")
            continue

        fig_idx += 1
        page_no = item.prov[0].page_no if item.prov else 0
        filename = f'docling_figure_p{page_no}_{fig_idx}.png'
        out_path = os.path.join(output_dir, filename)
        print(f"[ASSETS] Saving figure {fig_idx} from page {page_no} -> {out_path}")

        try:
            item.image.pil_image.save(out_path, format='PNG')
        except Exception as e:
            print(f"[ASSETS] ERROR saving figure {fig_idx}: {e}")
            continue

        file_url = out_path
        try:
            upload_result = cloudinary.uploader.upload(
                out_path,
                folder='solstice/assets',
                public_id=f'docling_figure_p{page_no}_{fig_idx}',
                overwrite=True,
                resource_type='image',
            )
            file_url = upload_result['secure_url']
            print(f"[ASSETS] Uploaded figure {fig_idx} to Cloudinary: {file_url}")
        except Exception as e:
            print(f"[ASSETS] Cloudinary upload failed for figure {fig_idx}: {e} (using local path)")

        assets.append({
            'filename': filename,
            'filepath': file_url,
            'asset_type': 'image',
            'name': f'Figure {fig_idx} (page {page_no})',
            'source': 'docling',
        })

    print(f"[ASSETS] Done. Found {fig_idx} PictureItems, {skipped_no_image} had no image, returning {len(assets)} assets")
    return assets


def extract_tables_docling(filepath: str) -> list:
    """
    Extract structured table data from a PDF using docling's TableFormer.
    Returns list of { page_no, markdown, index }.
    """
    print(f"[TABLES] Starting docling table extraction for: {filepath}")
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.document import TableItem
        print("[TABLES] Docling imports successful")
    except ImportError as e:
        print(f"[TABLES] ERROR: docling import failed: {e}")
        return []

    pipeline_options = PdfPipelineOptions(
        generate_picture_images=False,
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )

    print("[TABLES] Running docling converter.convert()...")
    try:
        result = converter.convert(filepath)
    except Exception as e:
        print(f"[TABLES] ERROR: converter.convert() failed: {e}")
        import traceback
        traceback.print_exc()
        return []

    tables = []
    tbl_idx = 0

    for item, _level in result.document.iterate_items():
        if not isinstance(item, TableItem):
            continue

        tbl_idx += 1
        page_no = item.prov[0].page_no if item.prov else 0
        try:
            md = item.export_to_markdown()
            print(f"[TABLES] Table {tbl_idx} from page {page_no}: {len(md)} chars")
        except Exception as e:
            print(f"[TABLES] ERROR exporting table {tbl_idx}: {e}")
            continue
        tables.append({
            'page_no': page_no,
            'markdown': md,
            'index': tbl_idx,
        })

    print(f"[TABLES] Done. Found {tbl_idx} tables")
    return tables
