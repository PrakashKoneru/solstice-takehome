import re
from flask import Blueprint, request, jsonify
from extensions import db
from models import Message, ChatSession, DesignSystem, DesignSystemAsset, KnowledgeItem, Claim
from services.claude_service import (
    generate_content, chat_response, review_content, orchestrate,
    generate_slide_spec, validate_slide_spec, build_compliance_trace,
    render_spec_to_html, edit_slide_spec,
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

    design_tokens      = None
    brand_guidelines   = None
    component_patterns = None
    ds_assets          = []
    audience_rules     = None
    ds                 = None
    if ds_id:
        ds = DesignSystem.query.get(ds_id)
        if ds:
            design_tokens      = ds.tokens
            brand_guidelines   = ds.brand_guidelines
            component_patterns = ds.component_patterns
            audience_rules     = (ds.brand_guidelines or {}).get('audienceRules') if ds else None
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

    # Retrieve previous spec and HTML from last generation (if any)
    prev_spec = None
    prev_html = None
    for m in reversed(prior_messages):
        rr = m.review_report
        if rr and isinstance(rr, dict) and 'spec' in rr:
            prev_spec = rr['spec']
            prev_html = m.html_content
            break

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
                    if prev_spec:
                        # Targeted edit path
                        spec = edit_slide_spec(
                            prompt, prev_spec, claims_list, slim_history,
                        )
                        spec_changed = (spec != prev_spec)
                        print(f"[DEBUG] edit_slide_spec: spec_changed={spec_changed}")
                    else:
                        # Fresh generation path
                        print(f"[DEBUG] Using generate_slide_spec path (no prev_spec)")
                        spec = generate_slide_spec(
                            prompt, claims_list, brand_guidelines,
                            target_audience, audience_rules, slim_history,
                        )
                    errors = validate_slide_spec(spec, list(claims_by_id.keys()), brand_guidelines)
                    if errors:
                        print(f"[DEBUG] Validation errors after edit: {errors}")
                        # Retry as fresh generation with errors as feedback
                        spec = generate_slide_spec(
                            prompt + f"\n\nFix these validation errors: {'; '.join(errors)}",
                            claims_list, brand_guidelines,
                            target_audience, audience_rules, slim_history,
                        )
                        errors = validate_slide_spec(spec, list(claims_by_id.keys()), brand_guidelines)

                    if errors:
                        chat_text = f"Could not generate compliant slides: {'; '.join(errors)}"
                    else:
                        # Auto-inject most relevant ISI claim into clinical slides missing one
                        isi_claims = {cid: c for cid, c in claims_by_id.items() if c.get('claim_type') == 'isi'}
                        if isi_claims:
                            clinical = {'big_stat', 'stat_row', 'two_column', 'three_column_cards',
                                        'comparison_table', 'data_table', 'subgroup_forest'}
                            for slide in spec.get('slides', []):
                                if slide.get('layout') in clinical:
                                    footer_ids = {fc.get('claim_id') for fc in slide.get('footer_claims', [])}
                                    if not any(cid in footer_ids for cid in isi_claims):
                                        # Collect tags from all claims referenced on this slide
                                        slide_cids = []
                                        h = slide.get('headline', {}).get('claim_id')
                                        if h:
                                            slide_cids.append(h)
                                        slide_cids += [b['claim_id'] for b in slide.get('body_claims', []) if b.get('claim_id')]
                                        slide_tags = set()
                                        for cid in slide_cids:
                                            slide_tags.update(t.lower() for t in (claims_by_id.get(cid, {}).get('tags') or []))

                                        # Score each ISI by tag overlap with slide content
                                        def isi_relevance(isi_id):
                                            isi_tags = set(t.lower() for t in (isi_claims[isi_id].get('tags') or []))
                                            return len(isi_tags & slide_tags)

                                        best_isi = max(isi_claims.keys(), key=isi_relevance)
                                        slide.setdefault('footer_claims', []).append({'claim_id': best_isi})

                        # Render HTML — reuse previous if spec unchanged
                        is_edit = prev_spec is not None
                        if is_edit and spec == prev_spec and prev_html:
                            print(f"[DEBUG] spec unchanged after edit, reusing previous HTML")
                            html_content = prev_html
                        else:
                            try:
                                html_content = render_spec_to_html(
                                    spec, claims_by_id, design_tokens,
                                    brand_guidelines, ds_assets,
                                    current_html=prev_html if is_edit else None,
                                    component_patterns=component_patterns,
                                )
                            except Exception as e:
                                print(f"[DEBUG] render_spec_to_html FAILED: {e}")
                                html_content = render_deck(
                                    spec, claims_by_id, design_tokens, brand_guidelines, ds_assets,
                                )
                        review_report = build_compliance_trace(spec, claims_by_id)
                        review_report['spec'] = spec
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
            ds_assets=ds_assets,
            target_audience=target_audience,
            audience_rules=audience_rules,
            component_patterns=component_patterns,
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
