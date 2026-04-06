import os
from flask import Blueprint, jsonify, request, current_app
from werkzeug.utils import secure_filename
from extensions import db
from models import DesignSystem, DesignSystemAsset
from services.pdf_service import extract_text_from_pdf, extract_assets_from_pdf
from services.claude_service import extract_design_tokens, extract_brand_guidelines, extract_slide_templates

design_system_bp = Blueprint('design_system', __name__, url_prefix='/api/design-system')

ALLOWED_PDF = {'pdf'}
ALLOWED_ASSETS = {'png', 'jpg', 'jpeg', 'svg', 'webp', 'gif'}


def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


# ── Design System CRUD ──────────────────────────────────────────────────────

@design_system_bp.route('/', methods=['GET'])
def list_design_systems():
    systems = DesignSystem.query.order_by(DesignSystem.created_at.desc()).all()
    return jsonify([s.to_dict() for s in systems])


@design_system_bp.route('/upload', methods=['POST'])
def upload_design_system():
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400

    file = request.files.get('file')
    if not file or _ext(file.filename) not in ALLOWED_PDF:
        return jsonify({'error': 'PDF file required'}), 400

    filename = secure_filename(file.filename)
    upload_dir = current_app.config['UPLOAD_FOLDER']
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)

    pdf_text = extract_text_from_pdf(filepath)
    tokens           = extract_design_tokens(pdf_text)
    brand_guidelines = extract_brand_guidelines(pdf_text, pdf_filepath=filepath)
    slide_templates  = extract_slide_templates(pdf_text, pdf_filepath=filepath)

    no_default_exists = not db.session.query(DesignSystem.id).filter_by(is_default=True).scalar()
    ds = DesignSystem(
        name=name,
        pdf_filename=filename,
        tokens=tokens,
        brand_guidelines=brand_guidelines,
        slide_templates=slide_templates,
        is_default=no_default_exists,
    )
    db.session.add(ds)
    db.session.flush()  # get ds.id before commit

    # Auto-extract logos and icons from the PDF
    extracted = extract_assets_from_pdf(filepath, upload_dir)
    for asset in extracted:
        db.session.add(DesignSystemAsset(
            design_system_id=ds.id,
            name=asset['name'],
            asset_type=asset['asset_type'],
            file_url=asset['filepath'],
            filename=asset['filename'],
        ))

    db.session.commit()
    return jsonify(ds.to_dict()), 201


@design_system_bp.route('/<int:ds_id>', methods=['GET'])
def get_design_system(ds_id):
    ds = DesignSystem.query.get_or_404(ds_id)
    return jsonify(ds.to_dict())


@design_system_bp.route('/<int:ds_id>/set-default', methods=['PATCH'])
def set_default(ds_id):
    DesignSystem.query.update({'is_default': False})
    ds = DesignSystem.query.get_or_404(ds_id)
    ds.is_default = True
    db.session.commit()
    return jsonify(ds.to_dict())


@design_system_bp.route('/<int:ds_id>', methods=['DELETE'])
def delete_design_system(ds_id):
    ds = DesignSystem.query.get_or_404(ds_id)
    db.session.delete(ds)
    db.session.commit()
    return jsonify({'deleted': ds_id})


# ── Assets ──────────────────────────────────────────────────────────────────

@design_system_bp.route('/<int:ds_id>/assets', methods=['GET'])
def list_assets(ds_id):
    DesignSystem.query.get_or_404(ds_id)
    assets = DesignSystemAsset.query.filter_by(design_system_id=ds_id).order_by(DesignSystemAsset.created_at.desc()).all()
    return jsonify([a.to_dict() for a in assets])


@design_system_bp.route('/<int:ds_id>/assets', methods=['POST'])
def upload_asset(ds_id):
    DesignSystem.query.get_or_404(ds_id)

    asset_name = request.form.get('name', '').strip()
    asset_type = request.form.get('asset_type', 'image').strip()
    if not asset_name:
        return jsonify({'error': 'name is required'}), 400
    if asset_type not in ('icon', 'logo', 'image'):
        return jsonify({'error': 'asset_type must be icon, logo, or image'}), 400

    file = request.files.get('file')
    if not file or _ext(file.filename) not in ALLOWED_ASSETS:
        return jsonify({'error': 'PNG, JPG, SVG, or WebP file required'}), 400

    filename = secure_filename(file.filename)
    upload_dir = current_app.config['UPLOAD_FOLDER']
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)

    asset = DesignSystemAsset(
        design_system_id=ds_id,
        name=asset_name,
        asset_type=asset_type,
        file_url=filepath,
        filename=filename,
    )
    db.session.add(asset)
    db.session.commit()
    return jsonify(asset.to_dict()), 201


@design_system_bp.route('/<int:ds_id>/assets/<int:asset_id>', methods=['DELETE'])
def delete_asset(ds_id, asset_id):
    asset = DesignSystemAsset.query.filter_by(id=asset_id, design_system_id=ds_id).first_or_404()
    db.session.delete(asset)
    db.session.commit()
    return jsonify({'deleted': asset_id})
