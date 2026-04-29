import os
import json
import time
import logging
import threading
from flask import Blueprint, jsonify, request, current_app, Response
from werkzeug.utils import secure_filename
from extensions import db
from models import KnowledgeItem, Claim
from services.pdf_service import extract_text_from_pdf, extract_text_by_page, extract_document_outline
from services.claim_extractor import extract_claims_streaming, assign_sections_to_claims

logger = logging.getLogger(__name__)

knowledge_bp = Blueprint('knowledge', __name__, url_prefix='/api/knowledge')

ALLOWED_PDF = {'pdf'}


def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


@knowledge_bp.route('/', methods=['GET'])
def list_knowledge():
    items = KnowledgeItem.query.order_by(KnowledgeItem.created_at.desc()).all()
    result = []
    for item in items:
        d = item.to_dict()
        d['claim_count'] = Claim.query.filter_by(knowledge_id=item.id, is_approved=True).count()
        result.append(d)
    return jsonify(result)


def _run_extraction(app, item_id, pages):
    """Background thread: extract claims page-by-page and write to DB."""
    with app.app_context():
        try:
            item = db.session.get(KnowledgeItem, item_id)
            item.extraction_status = 'extracting'
            db.session.commit()

            # Get doc_outline for section assignment
            doc_outline = item.doc_outline or []

            def on_page_done(page_num, page_claims):
                """Insert each page's claims into DB as they arrive."""
                # Assign sections before writing to DB
                if doc_outline:
                    assign_sections_to_claims(page_claims, doc_outline)
                with app.app_context():
                    for seq_offset, c in enumerate(page_claims):
                        # Generate unique ID using page_num to avoid collisions
                        from services.claim_extractor import _make_id
                        claim_id = _make_id(c['text'], c['claim_type'], page_num * 1000 + seq_offset)
                        existing = db.session.get(Claim, claim_id)
                        if not existing:
                            db.session.add(Claim(
                                id=claim_id,
                                knowledge_id=item_id,
                                text=c['text'],
                                claim_type=c['claim_type'],
                                source_citation=c.get('source_citation'),
                                page_number=c.get('page_number'),
                                numeric_values=c.get('numeric_values', []),
                                tags=c.get('tags', []),
                                section=c.get('section'),
                                is_approved=True,
                            ))
                    db.session.commit()
                    logger.info("Page %d: wrote %d claims to DB for item %d", page_num, len(page_claims), item_id)

            claims_data = extract_claims_streaming(pages, item_id, app, on_page_done=on_page_done)

            item = db.session.get(KnowledgeItem, item_id)
            item.extraction_status = 'complete'
            db.session.commit()
            logger.info("Extraction complete for item %d: %d total claims", item_id,
                        Claim.query.filter_by(knowledge_id=item_id).count())
        except Exception as e:
            logger.error("Extraction failed for item %d: %s", item_id, e)
            try:
                item = db.session.get(KnowledgeItem, item_id)
                if item:
                    item.extraction_status = 'failed'
                    db.session.commit()
            except Exception:
                pass


@knowledge_bp.route('/upload', methods=['POST'])
def upload_knowledge():
    title = request.form.get('title', '').strip()
    if not title:
        return jsonify({'error': 'title is required'}), 400

    file = request.files.get('file')
    if not file or _ext(file.filename) not in ALLOWED_PDF:
        return jsonify({'error': 'PDF file required'}), 400

    doc_type = request.form.get('doc_type', 'general').strip()

    filename = secure_filename(file.filename)
    if KnowledgeItem.query.filter_by(filename=filename).first():
        return jsonify({'error': f'"{filename}" has already been uploaded'}), 409

    upload_dir = current_app.config['UPLOAD_FOLDER']
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)

    text_content = extract_text_from_pdf(filepath)
    pages = extract_text_by_page(filepath)
    doc_outline = extract_document_outline(filepath)

    item = KnowledgeItem(
        title=title,
        filename=filename,
        file_path=filepath,
        text_content=text_content,
        doc_type=doc_type,
        doc_outline=doc_outline,
        extraction_status='extracting',
        total_pages=len(pages),
    )
    db.session.add(item)
    db.session.commit()

    # Kick off background extraction
    app = current_app._get_current_object()
    t = threading.Thread(target=_run_extraction, args=(app, item.id, pages), daemon=True)
    t.start()

    result = item.to_dict()
    result['claim_count'] = 0
    return jsonify(result), 201


@knowledge_bp.route('/<int:item_id>/extraction-stream', methods=['GET'])
def extraction_stream(item_id):
    """SSE endpoint: streams extraction progress by polling the DB."""
    item = KnowledgeItem.query.get_or_404(item_id)
    app = current_app._get_current_object()

    def generate():
        last_count = 0
        while True:
            with app.app_context():
                item = db.session.get(KnowledgeItem, item_id)
                if not item:
                    yield f"event: error\ndata: {json.dumps({'error': 'item not found'})}\n\n"
                    return

                current_count = Claim.query.filter_by(knowledge_id=item_id).count()
                status = item.extraction_status
                total_pages = item.total_pages or 0

                # Emit progress
                yield f"event: progress\ndata: {json.dumps({'claims_so_far': current_count, 'total_pages': total_pages, 'status': status})}\n\n"

                # Emit new claims if count increased
                if current_count > last_count:
                    new_claims = (Claim.query
                                 .filter_by(knowledge_id=item_id)
                                 .order_by(Claim.created_at.asc())
                                 .offset(last_count)
                                 .limit(current_count - last_count)
                                 .all())
                    yield f"event: claims\ndata: {json.dumps([c.to_dict() for c in new_claims])}\n\n"
                    last_count = current_count

                if status in ('complete', 'failed'):
                    yield f"event: done\ndata: {json.dumps({'total_claims': current_count, 'status': status})}\n\n"
                    return

            time.sleep(1)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@knowledge_bp.route('/<int:item_id>', methods=['PATCH'])
def update_knowledge(item_id):
    item = KnowledgeItem.query.get_or_404(item_id)

    title = request.form.get('title', '').strip()
    if title:
        item.title = title

    doc_type = request.form.get('doc_type', '').strip()
    if doc_type:
        item.doc_type = doc_type

    file = request.files.get('file')
    if file and _ext(file.filename) in ALLOWED_PDF:
        filename = secure_filename(file.filename)
        upload_dir = current_app.config['UPLOAD_FOLDER']
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        item.filename = filename
        item.file_path = filepath
        item.text_content = extract_text_from_pdf(filepath)

    db.session.commit()
    return jsonify(item.to_dict())


@knowledge_bp.route('/<int:item_id>', methods=['DELETE'])
def delete_knowledge(item_id):
    item = KnowledgeItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'deleted': item_id})


# ── Claims endpoints ──────────────────────────────────────────────────────────

@knowledge_bp.route('/<int:item_id>/claims', methods=['GET'])
def list_claims(item_id):
    KnowledgeItem.query.get_or_404(item_id)
    claim_type = request.args.get('claim_type')
    is_approved = request.args.get('is_approved')

    q = Claim.query.filter_by(knowledge_id=item_id)
    if claim_type:
        q = q.filter_by(claim_type=claim_type)
    if is_approved is not None:
        q = q.filter_by(is_approved=(is_approved.lower() == 'true'))

    claims = q.order_by(Claim.created_at.asc()).all()
    return jsonify([c.to_dict() for c in claims])


@knowledge_bp.route('/<int:item_id>/claims/<claim_id>', methods=['PATCH'])
def update_claim(item_id, claim_id):
    claim = Claim.query.filter_by(id=claim_id, knowledge_id=item_id).first_or_404()
    data = request.get_json(force=True)

    if 'text' in data:
        claim.text = data['text']
    if 'is_approved' in data:
        claim.is_approved = bool(data['is_approved'])
    if 'claim_type' in data:
        claim.claim_type = data['claim_type']
    if 'tags' in data:
        claim.tags = data['tags']

    db.session.commit()
    return jsonify(claim.to_dict())


@knowledge_bp.route('/<int:item_id>/claims/<claim_id>', methods=['DELETE'])
def delete_claim(item_id, claim_id):
    claim = Claim.query.filter_by(id=claim_id, knowledge_id=item_id).first_or_404()
    db.session.delete(claim)
    db.session.commit()
    return jsonify({'deleted': claim_id})
