import os
import json
import time
import threading
import cloudinary
import cloudinary.uploader
from flask import Blueprint, jsonify, request, current_app, Response
from werkzeug.utils import secure_filename
from extensions import db
from models import DesignSystem, DesignSystemAsset
from services.pdf_service import extract_text_from_pdf, extract_assets_from_pdf
from services.claude_service import extract_design_tokens, extract_brand_guidelines, extract_component_patterns

design_system_bp = Blueprint('design_system', __name__, url_prefix='/api/design-system')

ALLOWED_PDF = {'pdf'}
ALLOWED_ASSETS = {'png', 'jpg', 'jpeg', 'svg', 'webp', 'gif'}

EXTRACTION_STEPS = [
    'tokens',
    'brand_guidelines',
    'component_patterns',
    'assets',
]


def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def _run_extraction(app, ds_id, filepath, pdf_text):
    """Background thread: run all extractions sequentially, updating status after each."""
    with app.app_context():
        try:
            ds = db.session.get(DesignSystem, ds_id)

            # Step 1: Design Tokens
            ds.extraction_step = 'tokens'
            db.session.commit()
            tokens = extract_design_tokens(pdf_text)
            ds = db.session.get(DesignSystem, ds_id)
            ds.tokens = tokens
            db.session.commit()

            # Step 2: Brand Guidelines
            ds.extraction_step = 'brand_guidelines'
            db.session.commit()
            brand_guidelines = extract_brand_guidelines(pdf_text, pdf_filepath=filepath)
            ds = db.session.get(DesignSystem, ds_id)
            ds.brand_guidelines = brand_guidelines
            db.session.commit()

            # Step 3: Component Patterns
            ds.extraction_step = 'component_patterns'
            db.session.commit()
            component_patterns = extract_component_patterns(filepath, pdf_text)
            ds = db.session.get(DesignSystem, ds_id)
            ds.component_patterns = component_patterns
            db.session.commit()

            # Step 4: Assets
            ds.extraction_step = 'assets'
            db.session.commit()
            upload_dir = app.config['UPLOAD_FOLDER']
            extracted = extract_assets_from_pdf(filepath, upload_dir)
            ds = db.session.get(DesignSystem, ds_id)
            for asset in extracted:
                db.session.add(DesignSystemAsset(
                    design_system_id=ds_id,
                    name=asset['name'],
                    asset_type=asset['asset_type'],
                    file_url=asset['filepath'],
                    filename=asset['filename'],
                    source=asset.get('source', 'raster'),
                ))
            ds.extraction_status = 'complete'
            ds.extraction_step = None
            db.session.commit()

        except Exception as e:
            print(f"[ERROR] Design system extraction failed for ds {ds_id}: {e}")
            try:
                ds = db.session.get(DesignSystem, ds_id)
                if ds:
                    ds.extraction_status = 'failed'
                    db.session.commit()
            except Exception:
                pass


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

    no_default_exists = not db.session.query(DesignSystem.id).filter_by(is_default=True).scalar()
    ds = DesignSystem(
        name=name,
        pdf_filename=filename,
        extraction_status='extracting',
        extraction_step='tokens',
        is_default=no_default_exists,
    )
    db.session.add(ds)
    db.session.commit()

    # Kick off background extraction
    app = current_app._get_current_object()
    t = threading.Thread(target=_run_extraction, args=(app, ds.id, filepath, pdf_text), daemon=True)
    t.start()

    return jsonify(ds.to_dict()), 201


@design_system_bp.route('/<int:ds_id>/extraction-stream', methods=['GET'])
def extraction_stream(ds_id):
    """SSE endpoint: streams extraction progress by polling the DB."""
    DesignSystem.query.get_or_404(ds_id)
    app = current_app._get_current_object()

    def generate():
        while True:
            with app.app_context():
                ds = db.session.get(DesignSystem, ds_id)
                if not ds:
                    yield f"event: error\ndata: {json.dumps({'error': 'design system not found'})}\n\n"
                    return

                status = ds.extraction_status
                step = ds.extraction_step

                # Calculate completed count
                if status == 'complete':
                    completed = len(EXTRACTION_STEPS)
                elif status == 'failed':
                    completed = EXTRACTION_STEPS.index(step) if step and step in EXTRACTION_STEPS else 0
                elif step and step in EXTRACTION_STEPS:
                    completed = EXTRACTION_STEPS.index(step)
                else:
                    completed = 0

                yield f"event: progress\ndata: {json.dumps({'step': step, 'completed': completed, 'total': len(EXTRACTION_STEPS), 'status': status})}\n\n"

                if status == 'complete':
                    yield f"event: done\ndata: {json.dumps(ds.to_dict())}\n\n"
                    return
                elif status == 'failed':
                    yield f"event: error\ndata: {json.dumps({'error': 'extraction failed', 'step': step})}\n\n"
                    return

            time.sleep(1)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


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

    result = cloudinary.uploader.upload(
        file.stream,
        folder='solstice/assets',
        public_id=filename.rsplit('.', 1)[0],
        overwrite=True,
        resource_type='image',
    )
    file_url = result['secure_url']

    asset = DesignSystemAsset(
        design_system_id=ds_id,
        name=asset_name,
        asset_type=asset_type,
        file_url=file_url,
        filename=filename,
        source='raster',
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
