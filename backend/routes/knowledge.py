import os
import re
import json
import time
import logging
import threading
from flask import Blueprint, jsonify, request, current_app, Response
from werkzeug.utils import secure_filename
from extensions import db
from models import KnowledgeItem, Claim, Chunk
from services.pdf_service import extract_text_from_pdf, extract_text_by_page, parse_document_docling
from services.claim_extractor import extract_claims_streaming, assign_sections_to_claims, _is_verbatim, extract_claims_from_chunks

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


def _run_extraction(app, item_id, pages, docling_tables=None, docling_figures=None,
                    pages_text_only=None, chunks_data=None):
    """Background thread: create chunks, extract claims deterministically, embed both."""
    with app.app_context():
        try:
            item = db.session.get(KnowledgeItem, item_id)
            item.extraction_status = 'extracting'
            db.session.commit()

            if not chunks_data:
                raise ValueError("No chunks produced from document — chunking pipeline required")

            # ── Chunk-based pipeline ──────────────────────────────
            logger.info("Using chunk-based extraction for item %d (%d chunks)", item_id, len(chunks_data))

            # Step 1: Create chunk rows
            for cd in chunks_data:
                existing = db.session.get(Chunk, cd['id'])
                if not existing:
                    db.session.add(Chunk(
                        id=cd['id'],
                        knowledge_id=item_id,
                        headings=cd.get('headings'),
                        serialized_text=cd.get('serialized_text'),
                        element_types=cd.get('element_types'),
                        has_table=cd.get('has_table', False),
                        has_figure=cd.get('has_figure', False),
                        page_start=cd.get('page_start'),
                        page_end=cd.get('page_end'),
                    ))
            db.session.commit()
            logger.info("Created %d chunks for item %d", len(chunks_data), item_id)

            # Step 2: Extract claims from chunks (deterministic, no LLM)
            claim_dicts = extract_claims_from_chunks(chunks_data, item_id)

            # Step 3: Insert claims into DB
            for cd in claim_dicts:
                existing = db.session.get(Claim, cd['id'])
                if not existing:
                    db.session.add(Claim(
                        id=cd['id'],
                        chunk_id=cd.get('chunk_id'),
                        knowledge_id=item_id,
                        text=cd['text'],
                        claim_type=cd['claim_type'],
                        content_format=cd.get('content_format', 'text'),
                        table_markdown=cd.get('table_markdown'),
                        table_json=cd.get('table_json'),
                        figure_url=cd.get('figure_url'),
                        page_number=cd.get('page_number'),
                        numeric_values=cd.get('numeric_values', []),
                        tags=cd.get('tags', []),
                        section=cd.get('section'),
                        section_hierarchy=cd.get('section_hierarchy'),
                        is_approved=True,
                    ))
            db.session.commit()
            logger.info("Created %d claims from chunks for item %d", len(claim_dicts), item_id)

            # Step 4: Embed chunks (serialized_text) and claims (section + text)
            try:
                from services.embedding_service import embed_texts

                # Embed chunks
                all_chunks = Chunk.query.filter_by(knowledge_id=item_id).all()
                chunk_texts = [c.serialized_text or '' for c in all_chunks]
                if chunk_texts:
                    chunk_embeddings = embed_texts(chunk_texts)
                    for chunk_obj, emb in zip(all_chunks, chunk_embeddings):
                        chunk_obj.embedding = emb
                    db.session.commit()
                    logger.info("Embedded %d chunks for item %d", len(chunk_texts), item_id)

                # Embed claims (section hierarchy + claim text)
                all_claims = Claim.query.filter_by(knowledge_id=item_id).order_by(Claim.page_number).all()
                claim_embed_texts = []
                for c in all_claims:
                    parts = []
                    if c.section_hierarchy:
                        parts.append(' > '.join(c.section_hierarchy))
                    parts.append(c.text)
                    claim_embed_texts.append(' | '.join(parts))
                if claim_embed_texts:
                    claim_embeddings = embed_texts(claim_embed_texts)
                    for claim_obj, emb in zip(all_claims, claim_embeddings):
                        claim_obj.embedding = emb
                    db.session.commit()
                    logger.info("Embedded %d claims for item %d", len(claim_embed_texts), item_id)
            except Exception as e:
                logger.warning("Embedding failed (non-fatal) for item %d: %s", item_id, e)

            item = db.session.get(KnowledgeItem, item_id)
            item.extraction_status = 'complete'
            db.session.commit()
            logger.info("Extraction complete for item %d: %d chunks, %d claims",
                        item_id,
                        Chunk.query.filter_by(knowledge_id=item_id).count(),
                        Claim.query.filter_by(knowledge_id=item_id).count())
        except Exception as e:
            logger.error("Extraction failed for item %d: %s", item_id, e)
            import traceback
            traceback.print_exc()
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

    # Single Docling pass: structured text, tables, figures, outline
    docling_result = parse_document_docling(filepath, upload_dir)
    pages = docling_result["pages"]
    doc_outline = docling_result["doc_outline"]
    text_content = "\n\n".join(p["text"] for p in pages)

    item = KnowledgeItem(
        title=title,
        filename=filename,
        file_path=filepath,
        text_content=text_content,
        doc_type=doc_type,
        doc_outline=doc_outline,
        extraction_status='extracting',
        total_pages=docling_result["total_pages"],
    )
    db.session.add(item)
    db.session.commit()

    # Kick off background extraction with chunks (new pipeline)
    app = current_app._get_current_object()
    chunks_data = docling_result.get("chunks", [])
    t = threading.Thread(
        target=_run_extraction,
        args=(app, item.id, pages),
        kwargs={
            'docling_tables': docling_result["tables"],
            'docling_figures': docling_result["figures"],
            'pages_text_only': docling_result.get("pages_text_only"),
            'chunks_data': chunks_data if chunks_data else None,
        },
        daemon=True,
    )
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


@knowledge_bp.route('/purge-non-verbatim', methods=['POST'])
def purge_non_verbatim():
    """Delete all text claims whose text is not found verbatim in the source document."""
    items = KnowledgeItem.query.all()
    total_checked = 0
    total_deleted = 0
    deleted_ids = []

    for item in items:
        if not item.text_content:
            continue
        # Strip markdown table lines from text_content so table-derived claims
        # are correctly identified as non-verbatim
        source_lines = item.text_content.split('\n')
        source_text_no_tables = '\n'.join(
            line for line in source_lines if not line.startswith('|')
        )
        claims = Claim.query.filter_by(knowledge_id=item.id, content_format='text').all()
        for c in claims:
            total_checked += 1
            if not _is_verbatim(c.text, source_text_no_tables):
                deleted_ids.append(c.id)
                db.session.delete(c)
                total_deleted += 1

    db.session.commit()
    logger.info("Purged %d non-verbatim claims out of %d checked", total_deleted, total_checked)
    return jsonify({
        'checked': total_checked,
        'deleted': total_deleted,
        'deleted_ids': deleted_ids,
    })


@knowledge_bp.route('/<int:item_id>/claims/<claim_id>', methods=['DELETE'])
def delete_claim(item_id, claim_id):
    claim = Claim.query.filter_by(id=claim_id, knowledge_id=item_id).first_or_404()
    db.session.delete(claim)
    db.session.commit()
    return jsonify({'deleted': claim_id})
