import re
from flask import Blueprint, request, jsonify
from extensions import db
from models import Message, ChatSession, DesignSystem, DesignSystemAsset, KnowledgeItem, Claim
from services.claude_service import (
    generate_content, chat_response, review_content, orchestrate,
    generate_slide_spec, validate_slide_spec, build_compliance_trace,
)
from services.renderer.renderer import render_deck

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/api/sessions/<int:session_id>/restore', methods=['POST'])
def restore_version(session_id):
    ChatSession.query.get_or_404(session_id)
    data = request.get_json(force=True)
    html_content = data.get('html_content')
    if not html_content:
        return jsonify({'error': 'html_content required'}), 400

    # T0-3: carry original prompt in restore label
    original_prompt = (data.get('original_prompt') or '').strip()
    label = f'Restored to: "{original_prompt[:80]}"' if original_prompt else 'Restored to previous version.'

    msg = Message(
        session_id=session_id,
        role='assistant',
        content=label,
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


# T0-1: Export endpoint
@chat_bp.route('/api/sessions/<int:session_id>/messages/<int:msg_id>/export', methods=['GET'])
def export_message(session_id, msg_id):
    ChatSession.query.get_or_404(session_id)
    msg = Message.query.filter_by(id=msg_id, session_id=session_id).first_or_404()
    return jsonify({
        'html_content':  msg.html_content,
        'review_report': msg.review_report,
        'prompt':        msg.content,
        'generated_at':  msg.created_at.isoformat(),
    })


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
    ds               = None
    if ds_id:
        ds = DesignSystem.query.get(ds_id)
        if ds:
            design_tokens    = ds.tokens
            brand_guidelines = ds.brand_guidelines
            slide_templates  = ds.slide_templates
            audience_rules   = (ds.brand_guidelines or {}).get('audienceRules') if ds else None
            raw_assets = DesignSystemAsset.query.filter_by(design_system_id=ds_id).all()
            ds_assets = [a.to_dict() for a in raw_assets]

    # Build conversation history
    prior_messages = (
        Message.query
        .filter_by(session_id=session_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    history = []
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

    # ── Orchestrator ──────────────────────────────────────────────────────────
    ops = orchestrate(prompt, slim_history, has_kb=bool(kb_texts))

    html_content  = None
    review_report = None
    chat_text     = None

    # ── Generation path (structured, claims-constrained) ──────────────────────
    if 'generate' in ops:
        if kb_doc_ids:
            claims = Claim.query.filter(
                Claim.knowledge_id.in_(kb_doc_ids),
                Claim.is_approved == True,
            ).all()
            claims_list = [c.to_dict() for c in claims]

            if not claims_list:
                chat_text = (
                    "No approved claims found in the selected documents. "
                    "Please review and approve claims on the Knowledge Base page before generating."
                )
            else:
                claims_by_id = {c['id']: c for c in claims_list}
                try:
                    spec = generate_slide_spec(
                        prompt, claims_list, brand_guidelines, slide_templates,
                        target_audience, audience_rules, slim_history,
                    )
                    errors = validate_slide_spec(spec, list(claims_by_id.keys()), brand_guidelines)
                    if errors:
                        # Retry once with errors as feedback
                        spec = generate_slide_spec(
                            prompt + f"\n\nFix these validation errors: {'; '.join(errors)}",
                            claims_list, brand_guidelines, slide_templates,
                            target_audience, audience_rules, slim_history,
                        )
                        errors = validate_slide_spec(spec, list(claims_by_id.keys()), brand_guidelines)

                    if errors:
                        chat_text = f"Could not generate compliant slides: {'; '.join(errors)}"
                    else:
                        html_content = render_deck(
                            spec, claims_by_id, design_tokens, brand_guidelines, ds_assets,
                        )
                        review_report = build_compliance_trace(spec, claims_by_id)
                        # Review Agent still runs as soft check
                        if kb_texts:
                            try:
                                soft = review_content(html_content, kb_texts)
                                review_report['soft_checks'] = soft
                            except Exception:
                                pass
                except Exception as e:
                    chat_text = f"Slide generation failed: {e}"

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

    # ── Summary after generation ──────────────────────────────────────────────
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
