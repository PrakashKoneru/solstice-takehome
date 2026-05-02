import base64
import os
import re as _re
import cloudinary
import cloudinary.uploader

def _parse_markdown_table(md: str) -> dict:
    """Parse a markdown table into structured JSON.

    Returns {"headers": ["col1", ...], "rows": [["val1", ...], ...]}.
    Returns None if parsing fails.
    """
    lines = [l.strip() for l in md.strip().split('\n') if l.strip()]
    if len(lines) < 2:
        return None

    def _split_row(line):
        # Strip leading/trailing pipes, split on pipe
        return [c.strip() for c in line.strip('|').split('|')]

    headers = _split_row(lines[0])
    rows = []
    for line in lines[1:]:
        stripped = line.strip('|').strip()
        # Skip separator rows (e.g. |---|---|)
        if stripped and all(c in '-|: ' for c in stripped):
            continue
        cells = _split_row(line)
        # Pad or truncate to match header count
        if len(cells) < len(headers):
            cells.extend([''] * (len(headers) - len(cells)))
        elif len(cells) > len(headers):
            cells = cells[:len(headers)]
        rows.append(cells)

    if not headers:
        return None

    return {"headers": headers, "rows": rows}


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


# Regex to detect section numbering like "1.", "2.1.", "12.3.", "5.12."
_SECTION_NUM_RE = _re.compile(r'^(\d+(?:\.\d+)*)\.?\s')


def _infer_heading_level(title: str, docling_level) -> int:
    """Infer heading level from section numbering in the title.

    Examples:
        "1. INDICATIONS AND USAGE"           → level 1
        "2.1.  Recommended Dosage"           → level 2
        "12.3. Pharmacokinetics"             → level 2
        "HIGHLIGHTS OF PRESCRIBING INFO"     → level 1  (no number, top-level)
        "FRESCO-2 Study"                     → level 3  (no number, unnumbered sub-heading)
        "Table 1: Recommended Dose..."       → level 3  (table reference)
    """
    # If Docling returned a real level > 1, trust it
    if isinstance(docling_level, int) and docling_level > 1:
        return docling_level

    # Strip decorative dashes from prescribing info highlights
    clean = _re.sub(r'-{2,}', '', title).strip()

    # Try to extract section number
    m = _SECTION_NUM_RE.match(clean)
    if m:
        num = m.group(1)
        # Count dots to determine depth: "5" → 1, "5.1" → 2, "5.1.1" → 3
        return num.count('.') + 1

    # ALL-CAPS titles without numbers are top-level sections
    # e.g. "FULL PRESCRIBING INFORMATION", "CONTRAINDICATIONS"
    alpha = _re.sub(r'[^a-zA-Z]', '', clean)
    if alpha and alpha == alpha.upper() and len(alpha) > 3:
        return 1

    # Everything else (unnumbered mixed-case like "FRESCO-2 Study",
    # "Table 1: ...", "Moderate CYP3A Inducers") is a sub-heading
    return 3


def parse_document_docling(filepath: str, upload_dir: str) -> dict:
    """
    Full Docling parse of a KB document. Returns structured text, tables, figures,
    and document outline in a single pass.

    Returns:
        {
            "pages": [{"page_number": 1, "text": "## Header\n\nParagraph...\n\n| col | col |..."}],
            "doc_outline": [{"title": "Efficacy", "page": 3, "level": 1}],
            "tables": [{"page_number": 5, "markdown": "| ... |", "caption": "Table 2: OS Results"}],
            "figures": [{"page_number": 5, "image": <PIL.Image>, "caption": "...", "figure_url": "..."}],
            "total_pages": 50,
        }
    """
    import io
    import json
    import anthropic
    from collections import defaultdict
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import (
        SectionHeaderItem, TextItem, ListItem, TableItem, PictureItem,
    )

    print(f"[DOCLING-KB] Starting full document parse for: {filepath}")

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

    # Accumulators
    page_texts = defaultdict(list)  # page_number -> list of text chunks (includes table markdown)
    page_texts_no_tables = defaultdict(list)  # same but without table markdown (for claim extraction)
    doc_outline = []
    tables = []
    figures = []
    current_section = None
    tbl_idx = 0

    for item, _level in doc_result.document.iterate_items():
        page_no = item.prov[0].page_no if item.prov else 0

        if isinstance(item, SectionHeaderItem):
            title = item.text.strip()
            if title:
                level = _infer_heading_level(title, _level)
                doc_outline.append({"title": title, "page": page_no, "level": level})
                current_section = title
                page_texts[page_no].append(f"## {title}")
                page_texts_no_tables[page_no].append(f"## {title}")

        elif isinstance(item, TextItem):
            text = item.text.strip()
            if text:
                page_texts[page_no].append(text)
                page_texts_no_tables[page_no].append(text)

        elif isinstance(item, ListItem):
            text = item.text.strip()
            if text:
                page_texts[page_no].append(f"- {text}")
                page_texts_no_tables[page_no].append(f"- {text}")

        elif isinstance(item, TableItem):
            tbl_idx += 1
            try:
                md = item.export_to_markdown()
                caption = f"Table {tbl_idx}"
                context_lines = []
                # Gather up to 3 preceding text lines for context
                page_content = page_texts.get(page_no, [])
                if page_content:
                    for line in page_content[-3:]:
                        line = line.strip()
                        if line and len(line) > 10:
                            context_lines.append(line)
                    # Pick the best caption: prefer lines mentioning "table N"
                    for line in reversed(context_lines):
                        if _re.search(r'table\s*' + str(tbl_idx), line, _re.IGNORECASE):
                            caption = line
                            break
                        elif line.lower().startswith("table") or len(line) < 120:
                            caption = line
                table_json = _parse_markdown_table(md)
                tables.append({
                    "page_number": page_no,
                    "markdown": md,
                    "table_json": table_json,
                    "caption": caption,
                    "context": " ".join(context_lines),
                    "section": current_section,
                })
                if table_json:
                    print(f"[DOCLING-KB] Table {tbl_idx} parsed to JSON: {len(table_json['headers'])} cols, {len(table_json['rows'])} rows")
                else:
                    print(f"[DOCLING-KB] Table {tbl_idx} JSON parse failed, will use markdown fallback")
                # Embed table in page text too
                page_texts[page_no].append(md)
                print(f"[DOCLING-KB] Table {tbl_idx} from page {page_no}: {len(md)} chars")
            except Exception as e:
                print(f"[DOCLING-KB] Error exporting table {tbl_idx}: {e}")

        elif isinstance(item, PictureItem):
            img = item.get_image(doc_result.document)
            if img is None:
                continue
            figures.append({
                "page_number": page_no,
                "image": img,
                "caption": "",
                "section": current_section,
            })

    # Merge consecutive table fragments with identical headers (multi-page tables)
    if len(tables) > 1:
        merged = [tables[0]]
        for tbl in tables[1:]:
            prev = merged[-1]
            prev_json = prev.get('table_json')
            curr_json = tbl.get('table_json')
            # If both have parsed JSON and headers match, merge rows
            if (prev_json and curr_json
                    and prev_json.get('headers') == curr_json.get('headers')):
                prev_json['rows'].extend(curr_json['rows'])
                # Append markdown too
                # Strip header row from current markdown before appending
                curr_lines = tbl['markdown'].strip().split('\n')
                # Skip header row and separator (first 2 lines)
                body_lines = [l for l in curr_lines[2:] if l.strip()]
                if body_lines:
                    prev['markdown'] += '\n' + '\n'.join(body_lines)
                # Update context if richer
                if tbl.get('context') and len(tbl['context']) > len(prev.get('context', '')):
                    prev['context'] = tbl['context']
                print(f"[DOCLING-KB] Merged table fragment from page {tbl['page_number']} into table on page {prev['page_number']} ({len(prev_json['rows'])} total rows)")
            else:
                merged.append(tbl)
        print(f"[DOCLING-KB] Table merge: {len(tables)} fragments → {len(merged)} tables")
        tables = merged

    # Label figures with Haiku vision and upload to Cloudinary
    if figures:
        print(f"[DOCLING-KB] Labeling and uploading {len(figures)} figures...")
        try:
            client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
        except Exception:
            client = None

        for i, fig in enumerate(figures):
            img = fig["image"]
            # Upload to Cloudinary
            fig_filename = f"kb_figure_p{fig['page_number']}_{i + 1}.png"
            fig_path = os.path.join(upload_dir, fig_filename)
            img.save(fig_path, format='PNG')

            figure_url = fig_path
            try:
                upload_result = cloudinary.uploader.upload(
                    fig_path,
                    folder='solstice/kb_figures',
                    public_id=f'kb_fig_p{fig["page_number"]}_{i + 1}',
                    overwrite=True,
                    resource_type='image',
                )
                figure_url = upload_result['secure_url']
                print(f"[DOCLING-KB] Figure {i + 1} uploaded -> {figure_url}")
            except Exception as e:
                print(f"[DOCLING-KB] Figure {i + 1} Cloudinary upload failed: {e}")

            fig["figure_url"] = figure_url

            # Label with Haiku vision
            if client:
                try:
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    b64 = base64.standard_b64encode(buf.getvalue()).decode()
                    resp = client.messages.create(
                        model='claude-haiku-4-5-20251001',
                        max_tokens=128,
                        messages=[{
                            'role': 'user',
                            'content': [
                                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': b64}},
                                {'type': 'text', 'text': (
                                    'What is this figure? Reply with ONLY a short label, e.g. '
                                    '"Kaplan-Meier OS Curve, FRESCO-2" or "Waterfall Plot, Tumor Reduction". '
                                    'No explanation.'
                                )},
                            ],
                        }],
                    )
                    label = resp.content[0].text.strip()
                    fig["caption"] = label
                    print(f"[DOCLING-KB] Figure {i + 1} labeled: {label}")
                except Exception as e:
                    print(f"[DOCLING-KB] Figure {i + 1} labeling failed: {e}")

    # Build pages list
    total_pages = doc_result.document.num_pages() if hasattr(doc_result.document, 'num_pages') else max(page_texts.keys(), default=0)
    pages = []
    for pg in sorted(page_texts.keys()):
        pages.append({
            "page_number": pg,
            "text": "\n\n".join(page_texts[pg]),
        })

    # Build table-free pages for claim extraction (tables handled separately as content_format='table')
    pages_text_only = []
    for pg in sorted(page_texts_no_tables.keys()):
        pages_text_only.append({
            "page_number": pg,
            "text": "\n\n".join(page_texts_no_tables[pg]),
        })

    # Embed doc_outline heading titles for semantic search
    if doc_outline:
        try:
            from services.embedding_service import embed_texts
            heading_titles = [entry['title'] for entry in doc_outline]
            heading_embeddings = embed_texts(heading_titles)
            for entry, emb in zip(doc_outline, heading_embeddings):
                entry['embedding'] = emb
            print(f"[DOCLING-KB] Embedded {len(heading_embeddings)} outline headings")
        except Exception as e:
            print(f"[DOCLING-KB] Heading embedding failed (non-fatal): {e}")

    # Step 2: Collect all content items from iterate_items()
    all_items = []
    last_caption = None  # track captions for figure labeling
    body_started = False  # track TOC boundary
    for item, _level in doc_result.document.iterate_items():
        if isinstance(item, SectionHeaderItem):
            # Detect body start: first numbered section heading (e.g. "1 INDICATIONS AND USAGE")
            if not body_started and hasattr(item, 'text') and item.text:
                heading_text = item.text.strip()
                if _re.match(r'^\d+\.?\s+\S', heading_text):
                    body_started = True
                    print(f"[DOCLING-KB] Body starts at: '{heading_text}' (page {item.prov[0].page_no if item.prov else '?'})")
            continue  # headers are structural, not claims

        # Skip everything before the body (highlights, TOC)
        if not body_started:
            continue

        label = item.label.value if hasattr(item.label, 'value') else str(item.label)
        page_no = item.prov[0].page_no if item.prov else 0
        self_ref = item.self_ref if hasattr(item, 'self_ref') else None

        # Track captions for figure labeling
        if label == 'caption':
            last_caption = item.text.strip() if hasattr(item, 'text') and item.text else None

        if isinstance(item, TableItem):
            try:
                md = item.export_to_markdown()
                tj = _parse_markdown_table(md)
                all_items.append({
                    'self_ref': self_ref,
                    'label': label,
                    'text': md[:120] if md else 'Table',
                    'content_format': 'table',
                    'table_markdown': md,
                    'table_json': tj,
                    'page_number': page_no,
                })
            except Exception:
                pass
        elif isinstance(item, PictureItem):
            caption = last_caption or current_section or f'Figure (page {page_no})'
            fig_url = None
            for fig in figures:
                if fig.get('page_number') == page_no:
                    fig_url = fig.get('figure_url')
                    break
            all_items.append({
                'self_ref': self_ref,
                'label': 'picture',
                'text': caption,
                'content_format': 'figure',
                'figure_url': fig_url,
                'page_number': page_no,
            })
        else:
            text = item.text if hasattr(item, 'text') and item.text else None
            if text and text.strip():
                all_items.append({
                    'self_ref': self_ref,
                    'label': label,
                    'text': text.strip(),
                    'content_format': 'text',
                    'page_number': page_no,
                })

    print(f"[DOCLING-KB] Collected {len(all_items)} content items (body only, after TOC)")

    # Step 3a: Deterministic junk filter — regex-based, no LLM
    filtered_items = []
    removed_deterministic = []
    for idx, item in enumerate(all_items):
        text = item.get('text', '')
        is_junk = False

        # Always keep tables and figures
        if item['content_format'] in ('table', 'figure'):
            filtered_items.append(item)
            continue

        # TOC lines with dots
        if _re.search(r'\.{3,}', text):
            is_junk = True
        # Very short fragments with no numbers (orphans like "Capsules:", "None.", "Placebo")
        elif len(text) < 15 and not _re.search(r'\d', text):
            is_junk = True
        # Chart axis labels: just a number with optional dash/dot
        elif _re.match(r'^[\d\.\-\+\}\s]+$', text) and len(text) < 10:
            is_junk = True
        # Page header/footer patterns
        elif _re.match(r'^Reference ID:', text, _re.IGNORECASE):
            is_junk = True
        # Bare section ref without content: "Dosage and Administration (2.2)" and nothing else
        elif _re.match(r'^[\w\s,]+\(\d+[\.\d]*\)\s*$', text) and len(text) < 60:
            is_junk = True

        if is_junk:
            removed_deterministic.append((idx, item))
        else:
            filtered_items.append(item)

    print(f"[DOCLING-KB] Deterministic filter: {len(all_items)} → {len(filtered_items)} "
          f"(removed {len(removed_deterministic)} junk items)")

    # Step 3b: LLM split — Haiku splits multi-fact items into atomic claims
    kept_items = filtered_items  # fallback: keep as-is if LLM fails
    try:
        import anthropic
        import json as _json
        split_client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

        # Build compact item list for the LLM — only text items need splitting
        item_list = []
        for idx, item in enumerate(filtered_items):
            if item['content_format'] in ('table', 'figure'):
                item_list.append({'i': idx, 'label': item['label'], 'text': '[KEEP WHOLE]', 'page': item['page_number']})
            else:
                item_list.append({'i': idx, 'label': item['label'], 'text': item['text'], 'page': item['page_number']})

        split_tool = {
            "name": "split_claims",
            "description": "Split multi-fact text items into atomic claims using character positions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_index": {
                                    "type": "integer",
                                    "description": "Index of the source item in the input list"
                                },
                                "start": {
                                    "type": "integer",
                                    "description": "Start character position (0-based). Use 0 for items kept whole."
                                },
                                "end": {
                                    "type": "integer",
                                    "description": "End character position (exclusive). Use -1 for items kept whole or to mean end of text."
                                }
                            },
                            "required": ["source_index", "start", "end"]
                        }
                    }
                },
                "required": ["claims"]
            }
        }

        split_response = split_client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=16384,
            system=(
                "You are a pharma document analyst. You receive pre-filtered text elements from a pharmaceutical document. "
                "ALL items are real content — do NOT remove any. Your ONLY job is to split items into atomic claims.\n\n"
                "PROCESS:\n"
                "1. Read and understand each item's content fully\n"
                "2. Identify distinct facts, data points, or statements within the item\n"
                "3. Return character positions to split at natural fact boundaries\n\n"
                "For each item, return {source_index, start, end}:\n"
                "- Items marked [KEEP WHOLE]: always return start=0, end=-1\n"
                "- Items with 1-3 sentences that form one fact: return start=0, end=-1 (keep whole)\n"
                "- Items with multiple facts: return multiple entries with character positions\n\n"
                "SPLITTING RULES:\n"
                "- Each resulting claim must be MAX 3 sentences. A claim can be 1, 2, or 3 sentences.\n"
                "- Split at natural fact boundaries — where the topic or data point changes\n"
                "- Do NOT split mechanically every 3 sentences. Understand the content first, then decide where facts naturally separate.\n"
                "- Each split must align to real sentence boundaries in the source text\n"
                "- A claim should be a self-contained piece of information\n\n"
                "EXAMPLES:\n"
                "- 'OS was 7.4 months (95% CI: 6.7, 8.2). PFS was 2.7 months (95% CI: 1.5, 3.7).' → two claims (different endpoints)\n"
                "- A paragraph describing study design (enrollment, eligibility, stratification) → split by: design, eligibility, stratification\n"
                "- 'FRUZAQLA can cause serious hemorrhagic events, which may be fatal.' → one claim (keep whole, cohesive warning)\n\n"
                "IMPORTANT: Return EVERY item. Do not skip any. Every source_index must appear at least once."
            ),
            tools=[split_tool],
            tool_choice={"type": "tool", "name": "split_claims"},
            messages=[{'role': 'user', 'content': f"Split these items into atomic claims:\n{_json.dumps(item_list)}"}],
        )

        for block in split_response.content:
            if block.type == 'tool_use' and block.name == 'split_claims':
                raw_claims = block.input.get('claims', [])
                kept_items = []
                for rc in raw_claims:
                    src_idx = rc.get('source_index', 0)
                    if src_idx >= len(filtered_items):
                        continue
                    src = filtered_items[src_idx]
                    start = rc.get('start', 0)
                    end = rc.get('end', -1)

                    new_item = dict(src)
                    new_item['_source_index'] = src_idx

                    if src['content_format'] == 'text' and not (start == 0 and end == -1):
                        full_text = src['text']
                        if end == -1:
                            end = len(full_text)
                        sliced = full_text[start:end].strip()
                        if sliced:
                            new_item['text'] = sliced
                        else:
                            continue
                    kept_items.append(new_item)

                from collections import Counter
                idx_counts = Counter(rc['source_index'] for rc in raw_claims)
                split_count = sum(1 for v in idx_counts.values() if v > 1)
                print(f"[DOCLING-KB] LLM split: {len(filtered_items)} items → {len(kept_items)} claims "
                      f"({split_count} items were split)")
                break
    except Exception as e:
        print(f"[DOCLING-KB] LLM split failed (keeping filtered items as-is): {e}")
        import traceback
        traceback.print_exc()

    # Step 4: Chunk with HierarchicalChunker for section grouping
    chunks_data = []
    ref_to_chunk = {}
    chunk_meta = []
    orphan_items = []
    try:
        from docling.chunking import HierarchicalChunker
        chunker = HierarchicalChunker(merge_list_items=True)
        raw_chunks = list(chunker.chunk(doc_result.document))
        print(f"[DOCLING-KB] HierarchicalChunker produced {len(raw_chunks)} chunks")

        # Build self_ref → chunk mapping from doc_items
        ref_to_chunk = {}  # self_ref → (chunk_id, headings, chunk_index)
        chunk_meta = []    # list of chunk metadata dicts

        for i, chunk in enumerate(raw_chunks):
            headings = chunk.meta.headings or []
            serialized = chunker.serialize(chunk)

            # Build chunk ID
            if headings:
                slug_parts = []
                for h in headings[-2:]:
                    words = _re.sub(r'[^a-z0-9\s]', '', str(h).lower()).split()[:3]
                    slug_parts.extend(words)
                slug = '_'.join(slug_parts) if slug_parts else f'chunk_{i}'
            else:
                slug = f'chunk_{i}'
            chunk_id = f"chunk_{slug}_{i:03d}"

            # Extract page range and element types
            element_types = []
            pages_in_chunk = []
            for di in (chunk.meta.doc_items or []):
                label = di.label.value if hasattr(di.label, 'value') else str(di.label)
                if label not in element_types:
                    element_types.append(label)
                for prov in (di.prov or []):
                    if hasattr(prov, 'page_no'):
                        pages_in_chunk.append(prov.page_no)
                # Map self_ref to this chunk
                if hasattr(di, 'self_ref') and di.self_ref:
                    ref_to_chunk[di.self_ref] = chunk_id

            has_table = 'table' in element_types
            has_figure = 'picture' in element_types or 'chart' in element_types
            page_start = min(pages_in_chunk) if pages_in_chunk else None
            page_end = max(pages_in_chunk) if pages_in_chunk else None

            chunk_meta.append({
                'id': chunk_id,
                'headings': headings,
                'serialized_text': serialized,
                'text': chunk.text,
                'element_types': element_types,
                'has_table': has_table,
                'has_figure': has_figure,
                'page_start': page_start,
                'page_end': page_end,
            })

        # Step 5: Assign filtered items to chunks via self_ref mapping
        chunk_items = {}  # chunk_id → list of item dicts
        orphan_items = []
        for item in kept_items:
            ref = item.get('self_ref')
            cid = ref_to_chunk.get(ref) if ref else None
            if cid:
                chunk_items.setdefault(cid, []).append(item)
            else:
                orphan_items.append(item)

        if orphan_items:
            print(f"[DOCLING-KB] {len(orphan_items)} items not mapped to any chunk (orphans)")

        # Build final chunks_data with their items
        for cm in chunk_meta:
            cm['items'] = chunk_items.get(cm['id'], [])
            chunks_data.append(cm)

        mapped_count = sum(len(cm['items']) for cm in chunks_data)
        print(f"[DOCLING-KB] Mapped {mapped_count} items to {len(chunks_data)} chunks")

        for i, cm in enumerate(chunks_data):
            if cm['items']:
                print(f"[DOCLING-KB] Chunk {i}: {' > '.join(cm['headings']) if cm['headings'] else '(no headings)'} "
                      f"| {len(cm['items'])} items | pages={cm['page_start']}-{cm['page_end']}")

    except Exception as e:
        print(f"[DOCLING-KB] HierarchicalChunker failed: {e}")
        import traceback
        traceback.print_exc()

    print(f"[DOCLING-KB] Done. {len(pages)} pages, {len(doc_outline)} outline entries, "
          f"{len(tables)} tables, {len(figures)} figures, {len(chunks_data)} chunks, "
          f"{len(kept_items)} filtered items")

    return {
        "pages": pages,
        "pages_text_only": pages_text_only,
        "doc_outline": doc_outline,
        "tables": tables,
        "figures": figures,
        "chunks": chunks_data,
        "total_pages": total_pages if isinstance(total_pages, int) else len(pages),
        # Debug intermediates
        "_debug": {
            "all_items": all_items,
            "filtered_items": filtered_items,
            "removed_deterministic": removed_deterministic,
            "kept_items": kept_items,
            "chunk_meta": chunk_meta,
            "ref_to_chunk": ref_to_chunk,
            "orphan_items": orphan_items,
        },
    }


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
