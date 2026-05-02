"""Debug inspection routes for knowledge base: documents, claims, tables, sections."""
import os
import html as _html
import json
from flask import Blueprint, jsonify, request, Response, current_app
from extensions import db
from models import KnowledgeItem, Claim, Chunk

kb_debug_bp = Blueprint('kb_debug', __name__, url_prefix='/api/knowledge-base/debug')


@kb_debug_bp.route('/documents', methods=['GET'])
def list_documents():
    """List all knowledge items with claim counts."""
    items = KnowledgeItem.query.order_by(KnowledgeItem.created_at.desc()).all()
    result = []
    for item in items:
        claim_count = Claim.query.filter_by(knowledge_id=item.id).count()
        table_count = Claim.query.filter_by(knowledge_id=item.id, content_format='table').count()
        figure_count = Claim.query.filter_by(knowledge_id=item.id, content_format='figure').count()
        d = item.to_dict()
        d['claim_count'] = claim_count
        d['table_count'] = table_count
        d['figure_count'] = figure_count
        result.append(d)
    return jsonify(result)


@kb_debug_bp.route('/documents/<int:doc_id>', methods=['GET'])
def document_detail(doc_id):
    """Full document detail: outline, all claims grouped by section."""
    item = db.session.get(KnowledgeItem, doc_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404

    claims = Claim.query.filter_by(knowledge_id=doc_id).order_by(
        Claim.page_number, Claim.created_at
    ).all()

    # Group claims by section
    by_section = {}
    for c in claims:
        section = c.section or 'No Section'
        by_section.setdefault(section, []).append(c.to_dict())

    return jsonify({
        'document': item.to_dict(),
        'doc_outline': item.doc_outline or [],
        'total_claims': len(claims),
        'claims_by_section': by_section,
    })


@kb_debug_bp.route('/documents/<int:doc_id>/claims', methods=['GET'])
def document_claims(doc_id):
    """All claims for a document, with optional filters."""
    item = db.session.get(KnowledgeItem, doc_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404

    query = Claim.query.filter_by(knowledge_id=doc_id)

    # Optional filters
    claim_type = request.args.get('type')
    if claim_type:
        query = query.filter_by(claim_type=claim_type)

    content_format = request.args.get('format')
    if content_format:
        query = query.filter_by(content_format=content_format)

    section = request.args.get('section')
    if section:
        query = query.filter(Claim.section.ilike(f'%{section}%'))

    page = request.args.get('page', type=int)
    if page is not None:
        query = query.filter_by(page_number=page)

    claims = query.order_by(Claim.page_number, Claim.created_at).all()
    return jsonify({
        'document': item.title,
        'filters': {'type': claim_type, 'format': content_format, 'section': section, 'page': page},
        'count': len(claims),
        'claims': [c.to_dict() for c in claims],
    })


@kb_debug_bp.route('/documents/<int:doc_id>/tables', methods=['GET'])
def document_tables(doc_id):
    """All table claims with full table_json and markdown."""
    item = db.session.get(KnowledgeItem, doc_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404

    tables = Claim.query.filter_by(
        knowledge_id=doc_id, content_format='table'
    ).order_by(Claim.page_number).all()

    result = []
    for t in tables:
        d = t.to_dict()
        d['row_count'] = len(t.table_json.get('rows', [])) if t.table_json else 0
        d['headers'] = t.table_json.get('headers', []) if t.table_json else []
        result.append(d)

    return jsonify({
        'document': item.title,
        'count': len(result),
        'tables': result,
    })


@kb_debug_bp.route('/documents/<int:doc_id>/outline', methods=['GET'])
def document_outline(doc_id):
    """Document outline / section tree."""
    item = db.session.get(KnowledgeItem, doc_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404

    claims = Claim.query.filter_by(knowledge_id=doc_id).all()
    section_counts = {}
    for c in claims:
        s = c.section or 'No Section'
        section_counts[s] = section_counts.get(s, 0) + 1

    return jsonify({
        'document': item.title,
        'outline': item.doc_outline or [],
        'claims_per_section': section_counts,
    })


@kb_debug_bp.route('/documents/<int:doc_id>/chunks', methods=['GET'])
def document_chunks(doc_id):
    """All chunks for a document with their claims."""
    item = db.session.get(KnowledgeItem, doc_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404

    chunks = Chunk.query.filter_by(knowledge_id=doc_id).order_by(Chunk.page_start).all()
    result = []
    for chunk in chunks:
        d = chunk.to_dict()
        d['claim_count'] = Claim.query.filter_by(chunk_id=chunk.id).count()
        d['claims'] = [c.to_dict() for c in Claim.query.filter_by(chunk_id=chunk.id).all()]
        result.append(d)

    return jsonify({
        'document': item.title,
        'count': len(result),
        'chunks': result,
    })


@kb_debug_bp.route('/claims/<string:claim_id>', methods=['GET'])
def claim_detail(claim_id):
    """Single claim full detail."""
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({'error': 'Not found'}), 404
    d = claim.to_dict()
    d['has_embedding'] = bool(claim.embedding)
    d['embedding_dim'] = len(claim.embedding) if claim.embedding else 0
    d['chunk_id'] = claim.chunk_id
    return jsonify(d)


@kb_debug_bp.route('/pipeline/<int:doc_id>', methods=['GET'])
def debug_pipeline(doc_id):
    """Run the real extraction pipeline and render each step's output as HTML. No DB writes."""
    item = db.session.get(KnowledgeItem, doc_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404

    filepath = item.file_path
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'PDF file not found'}), 404

    # Run the actual pipeline
    from services.pdf_service import parse_document_docling
    upload_dir = current_app.config['UPLOAD_FOLDER']
    result = parse_document_docling(filepath, upload_dir)

    debug = result.get('_debug', {})
    all_items = debug.get('all_items', [])
    filtered_items = debug.get('filtered_items', [])
    removed_deterministic = debug.get('removed_deterministic', [])
    kept_items = debug.get('kept_items', [])
    chunk_meta = debug.get('chunk_meta', [])
    orphan_items = debug.get('orphan_items', [])

    steps = []

    # ── Step 1: Docling Parse ──
    steps.append({
        'title': 'Step 1: Docling Parse',
        'description': 'DocumentConverter.convert() → structured document with typed elements',
        'code': 'converter = DocumentConverter()\nresult = converter.convert(filepath)\ndoc = result.document',
        'output': f'{result["total_pages"]} pages, {len(result["doc_outline"])} outline entries, '
                  f'{len(result["tables"])} tables, {len(result["figures"])} figures',
    })

    # ── Step 2: iterate_items() (body only, after TOC) ──
    items_output = []
    for idx, it in enumerate(all_items):
        items_output.append(f'[{idx}] ({it["label"]}) p{it["page_number"]}: {it["text"][:120]}')
    steps.append({
        'title': 'Step 2: Collect Content Items',
        'description': 'doc.iterate_items() → body items only (skips everything before first numbered section heading)',
        'code': 'body_started = False\nfor item, level in doc.iterate_items():\n    if SectionHeaderItem and re.match(r"^\\d+\\.?\\s+", text):\n        body_started = True\n    if not body_started: continue\n    # collect TextItem, ListItem, TableItem, PictureItem',
        'output': f'{len(all_items)} body items collected',
        'items': items_output,
    })

    # ── Step 3a: Deterministic Junk Filter ──
    det_output = []
    det_output.append(f'Removed {len(removed_deterministic)} junk items:')
    det_output.append('')
    for idx, it in removed_deterministic:
        det_output.append(f'  [{idx}] ({it["label"]}) p{it["page_number"]}: {it["text"][:100]}')
    det_output.append('')
    det_output.append(f'Kept {len(filtered_items)} items')
    steps.append({
        'title': 'Step 3a: Deterministic Junk Filter',
        'description': 'Regex-based removal: TOC dots, short fragments, axis labels, page headers, bare section refs',
        'code': 'if re.search(r"\\.{3,}", text): skip  # TOC\nif len(text) < 15 and no digits: skip  # orphan\nif re.match(r"^[\\d\\.\\-\\+]+$"): skip  # axis\nif re.match(r"^Reference ID:"): skip  # footer',
        'output': f'{len(all_items)} → {len(filtered_items)} ({len(removed_deterministic)} removed)',
        'items': det_output,
    })

    # ── Step 3b: LLM Split ──
    split_output = []
    split_output.append(f'{len(filtered_items)} items → {len(kept_items)} claims')
    split_output.append('')
    for i, ki in enumerate(kept_items):
        src_idx = ki.get('_source_index', '?')
        split_output.append(f'  [{i}] (src={src_idx}) ({ki["label"]}) p{ki["page_number"]}: {ki["text"][:120]}')
    steps.append({
        'title': 'Step 3b: LLM Split (Haiku)',
        'description': 'Haiku splits multi-fact items into atomic claims via character positions. Never removes items, never generates text.',
        'code': 'split_claims tool:\n  input: [{i, label, text, page}, ...]\n  output: [{source_index, start, end}, ...]\n  Text sliced at char positions from source',
        'output': f'{len(filtered_items)} → {len(kept_items)} claims',
        'items': split_output,
    })

    # ── Step 4: HierarchicalChunker ──
    chunk_output = []
    for cm in chunk_meta:
        h = ' > '.join(cm['headings']) if cm.get('headings') else '(no headings)'
        chunk_output.append(f'{cm["id"]}: {h} | pages {cm.get("page_start")}-{cm.get("page_end")}')
    steps.append({
        'title': 'Step 4: HierarchicalChunker',
        'description': 'HierarchicalChunker.chunk(doc) → leaf-level section chunks with heading ancestry',
        'code': 'chunker = HierarchicalChunker(\n    merge_list_items=True\n)\nchunks = list(chunker.chunk(doc))\nchunker.serialize(chunk) → embedded text',
        'output': f'{len(chunk_meta)} chunks',
        'items': chunk_output,
    })

    # ── Step 5: Map Claims to Chunks ──
    chunks_data = result.get('chunks', [])
    map_output = []
    mapped_count = 0
    for cm in chunks_data:
        items = cm.get('items', [])
        if not items:
            continue
        mapped_count += len(items)
        h = ' > '.join(cm['headings']) if cm.get('headings') else '?'
        map_output.append(f'--- {cm["id"]} ({h}) ---')
        for ki in items:
            map_output.append(f'  ({ki.get("label","?")}) {ki["text"][:100]}')
    if orphan_items:
        map_output.append(f'--- ORPHANS ({len(orphan_items)}) ---')
        for ki in orphan_items:
            map_output.append(f'  ({ki.get("label","?")}) p{ki.get("page_number","?")}: {ki["text"][:100]}')
    steps.append({
        'title': 'Step 5: Map Claims to Chunks',
        'description': 'Match self_ref from iterate_items to chunk.meta.doc_items refs',
        'code': 'for item in kept_items:\n    chunk_id = ref_to_chunk[item.self_ref]\n    # item belongs to this chunk',
        'output': f'{mapped_count} mapped, {len(orphan_items)} orphans',
        'items': map_output,
    })

    # ── Render HTML ──
    html_parts = [
        '<!DOCTYPE html><html><head>',
        '<meta charset="utf-8">',
        f'<title>Pipeline Debug: {_html.escape(item.title)}</title>',
        '<style>',
        'body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }',
        'h1 { color: #1a1a2e; margin-bottom: 30px; }',
        '.step { background: #fff; border-radius: 8px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }',
        '.step-header { background: #1a1a2e; color: #fff; padding: 12px 20px; }',
        '.step-header h2 { margin: 0; font-size: 16px; }',
        '.step-header p { margin: 4px 0 0; font-size: 13px; opacity: 0.8; }',
        '.step-body { display: flex; gap: 0; }',
        '.step-code { flex: 0 0 35%; padding: 16px 20px; background: #f8f9fa; border-right: 1px solid #e0e0e0; }',
        '.step-code pre { margin: 0; font-size: 12px; white-space: pre-wrap; color: #333; }',
        '.step-output { flex: 1; padding: 16px 20px; overflow-x: auto; }',
        '.step-output .summary { font-weight: 600; color: #1a1a2e; margin-bottom: 8px; }',
        '.step-output pre { margin: 0; font-size: 12px; white-space: pre-wrap; color: #444; max-height: 500px; overflow-y: auto; }',
        '</style></head><body>',
        f'<h1>Pipeline Debug: {_html.escape(item.title)}</h1>',
    ]

    for step in steps:
        items_text = '\n'.join(step.get('items', []))
        html_parts.append(f'''
        <div class="step">
            <div class="step-header">
                <h2>{_html.escape(step['title'])}</h2>
                <p>{_html.escape(step['description'])}</p>
            </div>
            <div class="step-body">
                <div class="step-code"><pre>{_html.escape(step['code'])}</pre></div>
                <div class="step-output">
                    <div class="summary">{_html.escape(step['output'])}</div>
                    <pre>{_html.escape(items_text)}</pre>
                </div>
            </div>
        </div>
        ''')

    html_parts.append('</body></html>')
    return Response('\n'.join(html_parts), mimetype='text/html')
