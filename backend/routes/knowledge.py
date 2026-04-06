import os
from flask import Blueprint, jsonify, request, current_app
from werkzeug.utils import secure_filename
from extensions import db
from models import KnowledgeItem
from services.pdf_service import extract_text_from_pdf

knowledge_bp = Blueprint('knowledge', __name__, url_prefix='/api/knowledge')

ALLOWED_PDF = {'pdf'}


def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


@knowledge_bp.route('/', methods=['GET'])
def list_knowledge():
    items = KnowledgeItem.query.order_by(KnowledgeItem.created_at.desc()).all()
    return jsonify([item.to_dict() for item in items])


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

    item = KnowledgeItem(
        title=title,
        filename=filename,
        file_path=filepath,
        text_content=text_content,
        doc_type=doc_type,
    )
    db.session.add(item)
    db.session.commit()

    return jsonify(item.to_dict()), 201


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
