import base64
import os
import cloudinary
import cloudinary.uploader


def extract_document_outline(filepath: str) -> list:
    """Extract document outline (TOC) from a PDF.
    Returns [{"title": "...", "page": N, "level": N}, ...].
    Falls back to Haiku-based header detection if no TOC is present.
    """
    try:
        import fitz
        doc = fitz.open(filepath)
        toc = doc.get_toc()
        if toc:
            outline = [{"title": entry[1].strip(), "page": entry[2], "level": entry[0]}
                       for entry in toc if entry[1].strip()]
            print(f"[OUTLINE] Extracted outline from TOC: {[e['title'] for e in outline]}")
            return outline
    except Exception as e:
        print(f"[OUTLINE] PyMuPDF TOC extraction failed: {e}")

    # Fallback: use first 5 pages + Haiku to identify section headers
    try:
        import os
        import json
        import anthropic
        pages = extract_text_by_page(filepath)
        sample_text = "\n\n".join(
            f"--- Page {p['page_number']} ---\n{p['text'][:2000]}"
            for p in pages[:5]
        )
        client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            messages=[{
                'role': 'user',
                'content': (
                    f"Identify the major section headers from this document excerpt. "
                    f"Return ONLY a JSON array of objects with 'title', 'page', and 'level' fields.\n\n"
                    f"{sample_text}"
                ),
            }],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        outline = json.loads(raw)
        if isinstance(outline, list):
            print(f"[OUTLINE] Extracted outline via Haiku: {[e.get('title') for e in outline]}")
            return outline
    except Exception as e:
        print(f"[OUTLINE] Haiku fallback failed: {e}")

    return []


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


def _perceptual_hash(img, hash_size=16):
    """
    Compute a simple perceptual hash (average hash) for a PIL image.
    Returns an integer hash that can be compared with XOR for hamming distance.
    """
    resized = img.resize((hash_size, hash_size)).convert('L')
    pixels = list(resized.getdata())
    avg = sum(pixels) / len(pixels)
    return sum(1 << i for i, p in enumerate(pixels) if p > avg)


def _hamming_distance(h1, h2):
    """Count differing bits between two hashes."""
    return bin(h1 ^ h2).count('1')


def _deduplicate_assets(assets, crop_map, threshold=12):
    """
    Remove near-duplicate assets across pages using perceptual hashing.
    Keeps the largest (highest resolution) version of each duplicate.
    assets: list of asset dicts with 'page_number' and crop index info
    crop_map: dict mapping (page_number, asset_idx) -> PIL image
    threshold: max hamming distance to consider as duplicate (out of 256 bits)
    """
    if not assets:
        return assets

    # Compute hashes for all assets
    hashed = []
    for asset in assets:
        key = (asset['page_number'], asset['_crop_key'])
        img = crop_map.get(key)
        if img:
            h = _perceptual_hash(img)
            area = img.size[0] * img.size[1]
            hashed.append({'asset': asset, 'hash': h, 'area': area})
        else:
            hashed.append({'asset': asset, 'hash': 0, 'area': 0})

    # Group duplicates
    keep = [True] * len(hashed)
    for i in range(len(hashed)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(hashed)):
            if not keep[j]:
                continue
            dist = _hamming_distance(hashed[i]['hash'], hashed[j]['hash'])
            if dist <= threshold:
                # Keep the larger one
                if hashed[j]['area'] > hashed[i]['area']:
                    keep[i] = False
                    print(f"[ASSETS] Dedup: '{hashed[i]['asset']['name']}' (p{hashed[i]['asset']['page_number']}) "
                          f"is duplicate of '{hashed[j]['asset']['name']}' (p{hashed[j]['asset']['page_number']}), keeping larger")
                    break
                else:
                    keep[j] = False
                    print(f"[ASSETS] Dedup: '{hashed[j]['asset']['name']}' (p{hashed[j]['asset']['page_number']}) "
                          f"is duplicate of '{hashed[i]['asset']['name']}' (p{hashed[i]['asset']['page_number']}), keeping larger")

    result = [hashed[i]['asset'] for i in range(len(hashed)) if keep[i]]
    removed = len(assets) - len(result)
    if removed:
        print(f"[ASSETS] Dedup removed {removed} duplicate(s), {len(result)} unique assets remain")
    return result


def _build_extraction_guide(brand_guidelines):
    """
    Build a structured extraction guide from brand guidelines that tells Claude
    exactly what assets to look for and what to ignore.
    """
    if not brand_guidelines:
        return ""

    lines = ["\n--- BRAND EXTRACTION GUIDE ---"]

    # What assets this brand actually has (from requiredElements + hallmark)
    extract_targets = []
    if brand_guidelines.get('hallmark'):
        extract_targets.append(f"Hallmark: {brand_guidelines['hallmark']}")
    for el in (brand_guidelines.get('requiredElements') or []):
        extract_targets.append(el)

    if extract_targets:
        lines.append("\nASSETS TO EXTRACT (these are the brand's actual reusable assets):")
        for t in extract_targets:
            lines.append(f"  - {t}")

    # What this brand prohibits (helps identify things to skip)
    prohibited = brand_guidelines.get('prohibited') or []
    if prohibited:
        lines.append("\nPROHIBITED ELEMENTS (never extract these):")
        for p in prohibited:
            lines.append(f"  - {p}")

    # Page types we know are rule pages from otherRelevantGuidelines sections
    rule_sections = brand_guidelines.get('otherRelevantGuidelines') or {}
    if rule_sections:
        section_names = list(rule_sections.keys())
        lines.append(f"\nRULE SECTIONS IN THIS GUIDE (pages covering these topics are instructional, "
                     f"not asset pages): {', '.join(section_names)}")

    # Brand personality/tone — helps distinguish brand assets from generic imagery
    personality = brand_guidelines.get('personality') or []
    if personality:
        lines.append(f"\nBrand personality: {', '.join(personality)}")

    lines.append("--- END GUIDE ---\n")
    return '\n'.join(lines)


def _understand_page(client, page_b64, page_num, brand_guidelines=None):
    """
    Sonnet vision call: sees a rendered page + brand guidelines.
    Returns a text description of design-system-relevant assets on this page.
    """
    extraction_guide = _build_extraction_guide(brand_guidelines)

    content = [
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': page_b64}},
        {'type': 'text', 'text': (
            f'You are analyzing page {page_num} of a pharma brand style guide '
            f'for design system asset extraction.{extraction_guide}\n\n'
            'FIRST, determine what TYPE of page this is:\n'
            '- ASSET PAGE: a page dedicated to presenting logo variants, icons, or brand '
            'graphics as standalone deliverables for designers to use (e.g. "Logo Usage", '
            '"Brand Icons", "Product Photography"). Assets are shown cleanly, often with '
            'clear space or multiple variants side by side.\n'
            '- RULE PAGE: a page that teaches HOW to use the brand — typography rules, '
            'color usage, spacing guidelines, table formatting, chart styling, layout '
            'construction, do/don\'t examples. These pages contain EXAMPLE mockups, '
            'annotated screenshots, callout lines, and sample layouts to demonstrate rules. '
            'The images on rule pages exist to TEACH, not to be extracted.\n'
            '- MIXED: has both rule demonstrations and standalone assets\n\n'
            'If this is a RULE PAGE, reply: "RULE PAGE. No assets on this page." — '
            'everything on it is instructional.\n\n'
            'If this is an ASSET PAGE or MIXED, list ONLY standalone assets that match '
            'the ASSETS TO EXTRACT list above (if provided). A designer would drag these '
            'from an asset library into a new layout. For each, note location and what it is.\n\n'
            'ALWAYS IGNORE regardless of page type:\n'
            '- Slide/page numbers\n'
            '- The brand logo repeating in a corner on every page (page furniture)\n'
            '- Color swatches, palette blocks, gradient samples\n'
            '- Font specimens, typography samples, text blocks\n'
            '- Annotation lines, callout arrows, measurement markers\n'
            '- Tables, charts, data visualizations\n'
            '- Background photography, lifestyle photos, scenic images\n'
            '- Mockups or screenshots showing assets in context (these teach usage rules)\n'
            '- Do/don\'t examples\n\n'
            'If this page has NO extractable assets, reply: "No assets on this page."\n\n'
            'Reply with: 1) page type, 2) brief structured list of assets (if any).'
        )},
    ]

    try:
        resp = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1024,
            messages=[{'role': 'user', 'content': content}],
        )
        understanding = resp.content[0].text.strip()
        print(f"[ASSETS] Page {page_num} understanding: {understanding[:200]}...")
        return understanding
    except Exception as e:
        print(f"[ASSETS] Page {page_num} understanding failed: {e}")
        return f"Page {page_num} of a brand style guide. Could not analyze page contents."


def _review_crops(client, crop_images, page_understanding, brand_guidelines=None):
    """
    Haiku vision call: sees ALL crops from one page + the page understanding.
    Returns per-crop verdict: [{"index", "name", "asset_type", "keep", "reason"}]
    """
    import io
    import json

    content = []
    for i, img in enumerate(crop_images):
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.standard_b64encode(buf.getvalue()).decode()
        content.append({
            'type': 'image',
            'source': {'type': 'base64', 'media_type': 'image/png', 'data': b64},
        })

    extraction_guide = _build_extraction_guide(brand_guidelines)

    content.append({
        'type': 'text',
        'text': (
            f'Here is the page analysis:\n'
            f'{page_understanding}\n{extraction_guide}\n'
            f'Above are {len(crop_images)} image crops that were automatically extracted '
            f'from that page. The images appear in order (first image is index 0).\n\n'
            f'IMPORTANT: Use the page analysis above. If the page was identified as a '
            f'RULE PAGE (typography rules, color usage, spacing, table/chart formatting), '
            f'then DISCARD ALL crops — everything on rule pages is instructional, including '
            f'tables, annotated mockups, sample layouts, and the repeated corner logo.\n\n'
            f'For ASSET PAGES or MIXED pages, match each crop to the identified assets.\n\n'
            f'Reply with ONLY a JSON array (no markdown fences):\n'
            f'[{{"index": 0, "name": "brand-aware name", "asset_type": "logo"|"icon"|"image", '
            f'"keep": true|false, "reason": "brief reason"}}]\n\n'
            f'KEEP only: standalone assets a designer would drag from an asset library '
            f'into a new layout — logos, logo lockups, brand icons, hallmark graphics, '
            f'product images (pill/packaging), standalone illustrations.\n\n'
            f'DISCARD:\n'
            f'- EVERYTHING from rule/instructional pages\n'
            f'- Slide/page numbers\n'
            f'- Background or lifestyle photography\n'
            f'- Color swatches or palette blocks\n'
            f'- Font samples or text-only crops\n'
            f'- Annotation lines, callout arrows, measurement markers\n'
            f'- Tables, charts, data visualizations\n'
            f'- Annotated mockups or sample layouts showing rules\n'
            f'- The brand logo that repeats in the corner of every page\n'
            f'- Tiny fragments, decorative lines, page furniture\n\n'
            f'When in doubt, discard.'
        ),
    })

    try:
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=2048,
            messages=[{'role': 'user', 'content': content}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except Exception as e:
        print(f"[ASSETS] Crop review failed: {e}")

    # Fallback: keep everything
    return [{"index": i, "name": "Extracted asset", "asset_type": "image",
             "keep": True, "reason": "fallback"} for i in range(len(crop_images))]


def extract_assets_from_pdf(filepath: str, output_dir: str, brand_guidelines=None) -> list:
    """
    Two-phase Claude pipeline for design system asset extraction:

    1. Docling single pass — extract all PictureItems, group by page
    2. For each page with crops:
       a. Render page → _understand_page() → page understanding text
       b. _review_crops() with all crops + understanding → keep/discard decisions
    3. Upload keepers to Cloudinary
    """
    import anthropic
    import fitz
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import PictureItem
    from collections import defaultdict

    print(f"[ASSETS] Starting docling+Claude pipeline for: {filepath}")

    # Step 1: Docling extraction (no classification needed)
    pipeline_options = PdfPipelineOptions(
        generate_picture_images=True,
        images_scale=2.0,
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )
    doc_result = converter.convert(filepath)

    # Collect all PictureItems, grouped by page
    pages_crops = defaultdict(list)
    for item, _level in doc_result.document.iterate_items():
        if not isinstance(item, PictureItem):
            continue
        img = item.get_image(doc_result.document)
        if img is None:
            continue
        page_num = item.prov[0].page_no if item.prov else 0
        pages_crops[page_num].append(img)

    total_crops = sum(len(crops) for crops in pages_crops.values())
    print(f"[ASSETS] Docling found {total_crops} pictures across {len(pages_crops)} pages")
    for pg, crops in sorted(pages_crops.items()):
        print(f"[ASSETS]   Page {pg}: {len(crops)} crops")

    # Render PDF pages at 1.5x for Claude vision
    pdf_doc = fitz.open(filepath)
    mat = fitz.Matrix(1.5, 1.5)

    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    candidates = []  # pre-dedup assets
    crop_map = {}  # (page_num, crop_idx) -> PIL image for dedup hashing
    asset_idx = 0

    # Step 2: For each page with crops, run the two-call pipeline
    for page_num in sorted(pages_crops.keys()):
        crop_images = pages_crops[page_num]
        print(f"\n[ASSETS] === Page {page_num}: {len(crop_images)} crops ===")

        # 2a. Render page and get Claude's understanding
        fitz_page_idx = page_num - 1  # fitz is 0-indexed
        if fitz_page_idx < 0 or fitz_page_idx >= len(pdf_doc):
            print(f"[ASSETS] Page {page_num}: skipping (out of range)")
            continue

        pix = pdf_doc[fitz_page_idx].get_pixmap(matrix=mat)
        page_b64 = base64.standard_b64encode(pix.tobytes('png')).decode()

        page_understanding = _understand_page(
            client, page_b64, page_num, brand_guidelines
        )

        # Skip pages where Claude found no assets
        if 'no assets' in page_understanding.lower():
            print(f"[ASSETS]   No assets identified on page {page_num}, skipping crop review")
            continue

        # 2b. Review all crops against the page understanding
        verdicts = _review_crops(
            client, crop_images, page_understanding, brand_guidelines
        )

        # Collect keepers as candidates (upload after dedup)
        for verdict in verdicts:
            idx = verdict.get('index', -1)
            if idx < 0 or idx >= len(crop_images):
                continue

            keep = verdict.get('keep', True)
            name = verdict.get('name', f'Asset {asset_idx + 1}')
            asset_type = verdict.get('asset_type', 'image')
            reason = verdict.get('reason', '')
            if asset_type not in ('logo', 'icon', 'image'):
                asset_type = 'image'

            if not keep:
                print(f"[ASSETS]   Crop {idx}: DISCARD '{name}' — {reason}")
                continue

            asset_idx += 1
            print(f"[ASSETS]   Crop {idx}: KEEP '{name}' ({asset_type})")
            crop_map[(page_num, idx)] = crop_images[idx]
            candidates.append({
                'asset_type': asset_type,
                'name': name,
                'source': 'docling',
                'page_number': page_num,
                '_crop_key': idx,
            })

    pdf_doc.close()

    # Step 3: Cross-page deduplication
    print(f"\n[ASSETS] Deduplicating {len(candidates)} candidates...")
    unique_assets = _deduplicate_assets(candidates, crop_map)

    # Step 4: Upload unique keepers to Cloudinary
    assets = []
    for i, asset in enumerate(unique_assets):
        key = (asset['page_number'], asset['_crop_key'])
        img = crop_map[key]
        filename = f"asset_p{asset['page_number']}_{i + 1}.png"
        out_path = os.path.join(output_dir, filename)
        img.save(out_path, format='PNG')

        safe_name = asset['name'].lower().replace(' ', '_')[:40]
        file_url = out_path
        try:
            upload_result = cloudinary.uploader.upload(
                out_path,
                folder='solstice/assets',
                public_id=f'{safe_name}_p{asset["page_number"]}_{i + 1}',
                overwrite=True,
                resource_type='image',
            )
            file_url = upload_result['secure_url']
            print(f"[ASSETS]   Uploaded '{asset['name']}' -> {file_url}")
        except Exception as e:
            print(f"[ASSETS]   '{asset['name']}' (Cloudinary failed: {e})")

        assets.append({
            'filename': filename,
            'filepath': file_url,
            'asset_type': asset['asset_type'],
            'name': asset['name'],
            'source': 'docling',
            'page_number': asset['page_number'],
        })

    print(f"\n[ASSETS] Done. {len(assets)} unique assets from {total_crops} docling extractions")
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
