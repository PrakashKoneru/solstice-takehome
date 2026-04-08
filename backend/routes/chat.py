import re
from flask import Blueprint, request, jsonify
from extensions import db
from models import Message, ChatSession, DesignSystem, DesignSystemAsset, KnowledgeItem
from services.claude_service import generate_content, chat_response, review_content, orchestrate

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/api/sessions/<int:session_id>/restore', methods=['POST'])
def restore_version(session_id):
    ChatSession.query.get_or_404(session_id)
    data = request.get_json(force=True)
    html_content = data.get('html_content')
    if not html_content:
        return jsonify({'error': 'html_content required'}), 400
    msg = Message(
        session_id=session_id,
        role='assistant',
        content='Restored to previous version.',
        html_content=html_content,
        review_report=data.get('review_report'),
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify(msg.to_dict()), 201


@chat_bp.route('/api/sessions/<int:session_id>/messages', methods=['GET'])
def list_messages(session_id):
    ChatSession.query.get_or_404(session_id)
    messages = (
        Message.query
        .filter_by(session_id=session_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return jsonify([m.to_dict() for m in messages])


@chat_bp.route('/api/sessions/<int:session_id>/messages', methods=['POST'])
def send_message(session_id):
    ChatSession.query.get_or_404(session_id)
    data = request.get_json(force=True)
    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'error': 'prompt is required'}), 400

    current_draft = data.get('current_draft') or None
    ds_id = data.get('design_system_id')
    kb_doc_ids = data.get('kb_doc_ids') or []
    target_audience = data.get('target_audience') or None

    design_tokens    = None
    brand_guidelines = None
    slide_templates  = None
    ds_assets        = []
    audience_rules   = None
    if ds_id:
        ds = DesignSystem.query.get(ds_id)
        if ds:
            design_tokens    = ds.tokens
            brand_guidelines = ds.brand_guidelines
            slide_templates  = ds.slide_templates
            audience_rules   = (ds.brand_guidelines or {}).get('audienceRules') if ds else None
            raw_assets = DesignSystemAsset.query.filter_by(design_system_id=ds_id).all()
            ds_assets = [a.to_dict() for a in raw_assets]

    # Build conversation history from existing session messages (before adding new user msg)
    prior_messages = (
        Message.query
        .filter_by(session_id=session_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    # Full history with HTML — for the Content agent (needs to see existing slides)
    history = []
    # Slim history without HTML — for the Orchestrator and Chat agent
    slim_history = []
    for m in prior_messages:
        if m.role == 'user':
            history.append({'role': 'user', 'content': m.content})
            slim_history.append({'role': 'user', 'content': m.content})
        else:
            if m.html_content:
                history.append({'role': 'assistant', 'content': m.html_content})
                slim_history.append({'role': 'assistant', 'content': m.content or '[slides generated]'})
            else:
                history.append({'role': 'assistant', 'content': m.content})
                slim_history.append({'role': 'assistant', 'content': m.content})

    user_msg = Message(session_id=session_id, role='user', content=prompt)
    db.session.add(user_msg)

    kb_texts = []
    if kb_doc_ids:
        items = KnowledgeItem.query.filter(KnowledgeItem.id.in_(kb_doc_ids)).all()
        kb_texts = [item.text_content for item in items if item.text_content]

    # ── Orchestrator: decide which agents to run ──────────────────────────────
    ops = orchestrate(prompt, slim_history, has_kb=bool(kb_texts))

    html_content = None
    review_report = None
    chat_text     = None

    # ── Content agent ─────────────────────────────────────────────────────────
    if 'generate' in ops:
        raw = generate_content(
            prompt,
            design_tokens=design_tokens,
            brand_guidelines=brand_guidelines,
            slide_templates=slide_templates,
            ds_assets=ds_assets,
            kb_texts=kb_texts,
            current_draft=current_draft,
            history=history,
            target_audience=target_audience,
            audience_rules=audience_rules,
        )
        # Find first HTML tag — model may prepend explanation text despite instructions
        html_match = re.search(r'<(?:div|html|section)', raw, re.IGNORECASE)
        if html_match:
            html_content = raw[html_match.start():]
        else:
            # Content agent returned a plain-text explanation — treat as chat
            chat_text = raw

    # ── Review agent — always runs when slides are produced with KB context ──────
    if html_content and kb_texts:
        review_report = review_content(html_content, kb_texts)

    # ── Chat agent ────────────────────────────────────────────────────────────
    if 'chat' in ops and not chat_text:
        chat_text = chat_response(
            prompt,
            kb_texts=kb_texts or None,
            history=slim_history,
            brand_guidelines=brand_guidelines,
            slide_templates=slide_templates,
            ds_assets=ds_assets,
            target_audience=target_audience,
            audience_rules=audience_rules,
        )

    # ── If generation ran, get a meaningful summary from the chat agent ───────
    if html_content and not chat_text:
        summary_prompt = (
            f"Slides were just generated in response to this request: \"{prompt}\". "
            "In 1–2 sentences, tell the user what was produced and what they should look for in the output panel. "
            "Be specific — mention layout type, key data, or any notable elements if you can infer them from the request."
        )
        try:
            chat_text = chat_response(
                summary_prompt,
                kb_texts=None,
                history=slim_history,
                brand_guidelines=None,
                slide_templates=None,
                ds_assets=None,
            )
        except Exception:
            chat_text = 'Slides generated — check the output panel.'

    # ── Assemble message ──────────────────────────────────────────────────────
    assistant_msg = Message(
        session_id=session_id,
        role='assistant',
        content=chat_text or 'Slides generated — check the output panel.',
        html_content=html_content,
        review_report=review_report,
    )

    db.session.add(assistant_msg)
    db.session.commit()

    return jsonify(assistant_msg.to_dict()), 201
