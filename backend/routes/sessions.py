from flask import Blueprint, jsonify, request
from extensions import db
from models import ChatSession

sessions_bp = Blueprint('sessions', __name__, url_prefix='/api/sessions')


@sessions_bp.route('/', methods=['GET'])
def list_sessions():
    sessions = ChatSession.query.order_by(ChatSession.created_at.desc()).all()
    return jsonify([s.to_dict() for s in sessions])


@sessions_bp.route('/', methods=['POST'])
def create_session():
    data = request.get_json(silent=True) or {}
    title = data.get('title', 'New Session').strip() or 'New Session'

    session = ChatSession(title=title)
    db.session.add(session)
    db.session.commit()

    return jsonify(session.to_dict()), 201


@sessions_bp.route('/<int:session_id>', methods=['PATCH'])
def update_session(session_id):
    session = ChatSession.query.get_or_404(session_id)
    data = request.get_json(silent=True) or {}

    if 'title' in data:
        session.title = data['title'].strip() or session.title

    db.session.commit()
    return jsonify(session.to_dict())


@sessions_bp.route('/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    session = ChatSession.query.get_or_404(session_id)
    db.session.delete(session)
    db.session.commit()
    return jsonify({'deleted': session_id})
