"""Debug inspection routes for knowledge base: documents, claims, tables, sections."""
from flask import Blueprint, jsonify, request
from extensions import db
from models import KnowledgeItem, Claim, Chunk

kb_debug_bp = Blueprint('kb_debug', __name__, url_prefix='/api/kb-debug')


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
