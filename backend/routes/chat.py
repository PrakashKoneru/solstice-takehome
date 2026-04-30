import re
import json
import queue
import threading
from flask import Blueprint, request, jsonify, Response, current_app
from extensions import db, socketio
from models import Message, ChatSession, DesignSystem, DesignSystemAsset, KnowledgeItem, Claim
from services.claude_service import (
    generate_content, chat_response, review_content, orchestrate,
    generate_slide_spec, validate_slide_spec, build_compliance_trace,
    render_spec_to_html, edit_slide_spec,
)
from services.renderer.renderer import render_deck

chat_bp = Blueprint('chat', __name__)


def _strip_outline_embeddings(outlines):
    return [{k: v for k, v in entry.items() if k != 'embedding'} for entry in outlines]


def _filter_claims_by_embedding(prompt: str, claims_list: list, doc_outlines: list,
                                heading_top_k: int = 5, claim_top_k: int = 20) -> list:
    """Use embedding similarity to select only relevant claims for a prompt.

    Strategy:
    1. Embed the prompt
    2. Match against heading embeddings → expand via section_hierarchy (children only)
    3. Match against claim embeddings directly
    4. Union of both sets

    Returns filtered claims list. Falls back to all claims if embeddings are missing.
    """
    try:
        from services.embedding_service import embed_texts, search_embeddings
    except Exception:
        return claims_list

    def _strip_embeddings(cl):
        return [{k: v for k, v in c.items() if k != 'embedding'} for c in cl]

    # Check if any claims/headings have embeddings
    claims_with_emb = [c for c in claims_list if c.get('embedding')]
    headings_with_emb = [h for h in doc_outlines if h.get('embedding')]

    if not claims_with_emb and not headings_with_emb:
        print(f"[EMBED-FILTER] No embeddings found, passing all {len(claims_list)} claims")
        return _strip_embeddings(claims_list)

    try:
        query_emb = embed_texts([prompt])[0]
    except Exception as e:
        print(f"[EMBED-FILTER] Failed to embed prompt: {e}")
        return _strip_embeddings(claims_list)

    selected_ids = set()

    # Match headings → expand to child claims via section_hierarchy
    if headings_with_emb:
        top_headings = search_embeddings(query_emb, headings_with_emb, top_k=heading_top_k)
        matched_titles = [(h['title'], h.get('level', 1), h['similarity']) for h in top_headings
                          if h['similarity'] > 0.3]
        print(f"[EMBED-FILTER] Top heading matches: {[(t, f'{s:.3f}') for t, _, s in matched_titles]}")

        for title, level, sim in matched_titles:
            for claim in claims_list:
                hierarchy = claim.get('section_hierarchy') or []
                section = claim.get('section') or ''
                # Check if this claim falls under the matched heading
                if title in hierarchy or title == section:
                    selected_ids.add(claim['id'])

    # Direct claim matches
    if claims_with_emb:
        top_claims = search_embeddings(query_emb, claims_with_emb, top_k=claim_top_k)
        for c in top_claims:
            if c['similarity'] > 0.3:
                selected_ids.add(c['id'])
                print(f"[EMBED-FILTER] Direct claim match: {c['id']} (sim={c['similarity']:.3f})")

    if not selected_ids:
        print(f"[EMBED-FILTER] No matches above threshold, passing all {len(claims_list)} claims")
        return _strip_embeddings(claims_list)

    filtered = [{k: v for k, v in c.items() if k != 'embedding'}
                for c in claims_list if c['id'] in selected_ids]
    print(f"[EMBED-FILTER] Filtered {len(claims_list)} → {len(filtered)} claims for prompt: \"{prompt[:80]}\"")
    return filtered


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


_CLAIM_SPAN_RE = re.compile(
    r'<span[^>]*data-claim-id="([^"]+)"[^>]*>(.*?)</span>',
    re.DOTALL,
)
_CLAIM_DIV_RE = re.compile(
    r'<div[^>]*data-claim-id="([^"]+)"[^>]*>',
)
_CLAIM_IMG_RE = re.compile(
    r'<img[^>]*data-claim-id="([^"]+)"[^>]*src="([^"]*)"[^>]*/?>',
)
_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')


def _normalize_claim_text(s: str) -> str:
    """Strip tags, decode common HTML entities, collapse whitespace."""
    s = _TAG_RE.sub('', s)
    s = (s.replace('&amp;', '&')
           .replace('&lt;', '<')
           .replace('&gt;', '>')
           .replace('&quot;', '"')
           .replace('&#39;', "'")
           .replace('&nbsp;', ' '))
    return _WS_RE.sub(' ', s).strip()


def _detect_claim_drift(html: str, claims_by_id: dict) -> list:
    """Walk the HTML for claim-locked elements and compare to the
    authoritative claim catalog. Returns a list of drift flags."""
    flags = []
    seen = set()

    # Check text claims (spans)
    for match in _CLAIM_SPAN_RE.finditer(html):
        cid = match.group(1)
        if cid in seen:
            continue
        seen.add(cid)
        if cid not in claims_by_id:
            flags.append({
                'claim': cid,
                'status': 'unsupported',
                'note': f'Claim ID "{cid}" not found in approved catalog.',
            })
            continue
        claim = claims_by_id[cid]
        content_format = claim.get('content_format', 'text')
        if content_format == 'text':
            rendered = _normalize_claim_text(match.group(2))
            expected = _normalize_claim_text(claim.get('text', ''))
            if rendered != expected:
                flags.append({
                    'claim': cid,
                    'status': 'unsupported',
                    'note': (
                        f'Rendered text diverged from approved claim. '
                        f'Expected: "{expected[:120]}". Got: "{rendered[:120]}".'
                    ),
                })

    # Check table claims (divs with data-claim-id) — presence check only
    for match in _CLAIM_DIV_RE.finditer(html):
        cid = match.group(1)
        if cid in seen:
            continue
        seen.add(cid)
        if cid not in claims_by_id:
            flags.append({
                'claim': cid,
                'status': 'unsupported',
                'note': f'Claim ID "{cid}" not found in approved catalog.',
            })

    # Check figure claims (imgs with data-claim-id) — verify src matches figure_url
    for match in _CLAIM_IMG_RE.finditer(html):
        cid = match.group(1)
        rendered_src = match.group(2)
        if cid in seen:
            continue
        seen.add(cid)
        if cid not in claims_by_id:
            flags.append({
                'claim': cid,
                'status': 'unsupported',
                'note': f'Claim ID "{cid}" not found in approved catalog.',
            })
            continue
        claim = claims_by_id[cid]
        expected_url = claim.get('figure_url', '')
        if expected_url and rendered_src != expected_url:
            flags.append({
                'claim': cid,
                'status': 'unsupported',
                'note': f'Figure src diverged. Expected: "{expected_url[:120]}". Got: "{rendered_src[:120]}".',
            })

    return flags


_VISUAL_TOKEN_RE = re.compile(r'\{\{\s*(?:VISUAL|visual)[_\-\s]*\d+\s*\}\}', re.IGNORECASE)


def _verify_visual_injections(html: str, spec: dict, claims_by_id: dict) -> list:
    """Verify all visual claims were properly injected into the final HTML."""
    issues = []

    # Check for unreplaced {{VISUAL_N}} tokens
    leftover = _VISUAL_TOKEN_RE.findall(html)
    for token in leftover:
        issues.append({
            'type': 'unreplaced_token',
            'detail': f'Visual placeholder {token} was not replaced in final HTML.',
        })

    # Check each visual claim in the spec has its data-claim-id in the HTML
    for slide in spec.get('slides', []):
        for bc in slide.get('body_claims', []):
            fmt = bc.get('content_format', 'text')
            cid = bc.get('claim_id', '')
            if fmt != 'visual_placeholder' and cid:
                claim = claims_by_id.get(cid, {})
                if claim.get('content_format') in ('table', 'figure'):
                    # This was a visual claim — verify it landed in the HTML
                    if f'data-claim-id="{cid}"' not in html:
                        issues.append({
                            'type': 'missing_visual',
                            'claim_id': cid,
                            'detail': f'Visual claim {cid} not found in final HTML.',
                        })
                    elif claim.get('figure_url') and claim['figure_url'] not in html:
                        issues.append({
                            'type': 'wrong_src',
                            'claim_id': cid,
                            'detail': f'Visual claim {cid} present but figure_url not in img src.',
                        })

    return issues


@chat_bp.route('/api/sessions/<int:session_id>/review', methods=['POST'])
def rerun_review(session_id):
    """Recompute the compliance review for the current HTML without touching
    the deck spec. Used by the frontend after manual edits to refresh the
    verdict badge. The spec is resolved from the session's most recent
    assistant message that has one attached."""
    session = ChatSession.query.get_or_404(session_id)
    data = request.get_json(force=True)
    html = data.get('html') or ''
    if not html:
        return jsonify({'error': 'html required'}), 400

    # Find the most recent spec in this session
    prior_messages = (
        Message.query.filter_by(session_id=session_id)
        .order_by(Message.created_at.asc()).all()
    )
    prev_spec = None
    for m in reversed(prior_messages):
        rr = m.review_report
        if rr and isinstance(rr, dict) and 'spec' in rr:
            prev_spec = rr['spec']
            break

    if not prev_spec:
        return jsonify({'error': 'no deck to review'}), 400

    # Load claims from the session's selected docs
    kb_doc_ids = session.selected_doc_ids or []
    claims_by_id = {}
    kb_texts = []
    if kb_doc_ids:
        claims = Claim.query.filter(
            Claim.knowledge_id.in_(kb_doc_ids),
            Claim.is_approved == True,
        ).all()
        claims_by_id = {c.to_dict()['id']: c.to_dict() for c in claims}

        items = KnowledgeItem.query.filter(KnowledgeItem.id.in_(kb_doc_ids)).all()
        kb_texts = [item.text_content for item in items if item.text_content]

    # Build the baseline compliance trace from the spec
    review_report = build_compliance_trace(prev_spec, claims_by_id)
    review_report['spec'] = prev_spec

    # HTML-drift detection: manual edits may have altered claim-locked text
    # without updating the spec. Walk the HTML for data-claim-id spans and
    # compare each to the authoritative claim catalog.
    drift_flags = _detect_claim_drift(html, claims_by_id)
    if drift_flags:
        review_report['flags'] = drift_flags
        review_report['verdict'] = 'flagged'
        review_report['summary'] = (
            f'{len(drift_flags)} claim(s) in the rendered HTML have been '
            f'edited and no longer match the approved claim text.'
        )
        review_report['confidence'] = 0.5

    # Optional soft checks against the current HTML
    if kb_texts:
        try:
            review_report['soft_checks'] = review_content(html, kb_texts)
        except Exception:
            pass

    return jsonify(review_report), 200


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
    doc_outlines = []
    if kb_doc_ids:
        items = KnowledgeItem.query.filter(KnowledgeItem.id.in_(kb_doc_ids)).all()
        kb_texts = [item.text_content for item in items if item.text_content]
        for item in items:
            if item.doc_outline:
                doc_outlines.extend(item.doc_outline)
    combined_outline = _strip_outline_embeddings(doc_outlines) if doc_outlines else None

    # Retrieve previous spec and HTML from last generation (if any)
    prev_spec = None
    prev_html = None
    for m in reversed(prior_messages):
        rr = m.review_report
        if rr and isinstance(rr, dict) and 'spec' in rr:
            prev_spec = rr['spec']
            prev_html = m.html_content
            break

    # ── Orchestrator ──────────────────────────────────────────────────────────
    print(f"[PIPELINE:{session_id}] Incoming prompt: \"{prompt[:120]}\"")
    print(f"[PIPELINE:{session_id}] selected_docs={kb_doc_ids}, has_deck={bool(prev_spec)}, has_kb={bool(kb_texts)}")
    ops = orchestrate(prompt, slim_history, has_kb=bool(kb_texts), has_deck=bool(prev_spec))
    print(f"[PIPELINE:{session_id}] Orchestrator decision: {ops}")

    html_content  = None
    review_report = None
    chat_text     = None

    # Helper: shared finalization pipeline (ISI injection → validation → render → compliance)
    def _finalize_spec(spec, claims_by_id, claims_list, is_edit=False):
        nonlocal html_content, review_report, chat_text

        errors = validate_slide_spec(spec, list(claims_by_id.keys()), brand_guidelines)
        if errors:
            print(f"[DEBUG] Validation errors: {errors}")
            retry_spec = generate_slide_spec(
                prompt + f"\n\nFix these validation errors: {'; '.join(errors)}",
                claims_list, brand_guidelines,
                target_audience, audience_rules, slim_history,
                component_patterns=component_patterns,
                doc_outline=combined_outline,
            )
            retry_errors = validate_slide_spec(retry_spec, list(claims_by_id.keys()), brand_guidelines)
            if retry_errors:
                chat_text = f"Could not generate compliant slides: {'; '.join(retry_errors)}"
                return
            spec = retry_spec

        # Auto-inject most relevant ISI claim into clinical slides missing one
        isi_claims = {cid: c for cid, c in claims_by_id.items() if c.get('claim_type') == 'isi'}
        if isi_claims:
            clinical = {'big_stat', 'stat_row', 'two_column', 'three_column_cards',
                        'comparison_table', 'data_table', 'subgroup_forest'}
            for slide in spec.get('slides', []):
                if slide.get('layout') in clinical:
                    footer_ids = {fc.get('claim_id') for fc in slide.get('footer_claims', [])}
                    if not any(cid in footer_ids for cid in isi_claims):
                        slide_cids = []
                        h = slide.get('headline', {}).get('claim_id')
                        if h:
                            slide_cids.append(h)
                        slide_cids += [b['claim_id'] for b in slide.get('body_claims', []) if b.get('claim_id')]
                        slide_tags = set()
                        for cid in slide_cids:
                            slide_tags.update(t.lower() for t in (claims_by_id.get(cid, {}).get('tags') or []))

                        def isi_relevance(isi_id):
                            isi_tags = set(t.lower() for t in (isi_claims[isi_id].get('tags') or []))
                            return len(isi_tags & slide_tags)

                        best_isi = max(isi_claims.keys(), key=isi_relevance)
                        slide.setdefault('footer_claims', []).append({'claim_id': best_isi})

        # Render HTML
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
        # Verify visual injections
        visual_issues = _verify_visual_injections(html_content, spec, claims_by_id)
        if visual_issues:
            review_report.setdefault('visual_issues', []).extend(visual_issues)
            print(f"[WARN] Visual injection issues: {visual_issues}")
        if kb_texts:
            try:
                soft = review_content(html_content, kb_texts)
                review_report['soft_checks'] = soft
            except Exception:
                pass

    # ── Edit path ─────────────────────────────────────────────────────────────
    print(f"[PIPELINE:{session_id}] Executing path: {'edit' if 'edit' in ops else 'generate' if 'generate' in ops else 'chat'}")
    if 'edit' in ops:
        if not prev_spec:
            chat_text = "There's no existing deck to edit yet. Try asking me to generate a new deck first."
        else:
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
                        spec = edit_slide_spec(
                            prompt, prev_spec, claims_list, slim_history,
                            brand_guidelines=brand_guidelines,
                        )
                        spec_changed = (spec != prev_spec)
                        print(f"[DEBUG] edit_slide_spec: spec_changed={spec_changed}")
                        if not spec_changed and prev_html:
                            print(f"[DEBUG] spec unchanged after edit, reusing previous HTML")
                            html_content = prev_html
                            review_report = build_compliance_trace(spec, claims_by_id)
                            review_report['spec'] = spec
                        else:
                            _finalize_spec(spec, claims_by_id, claims_list, is_edit=True)
                    except Exception as e:
                        chat_text = f"Slide edit failed: {e}"

    # ── Generation path (structured, claims-constrained) ──────────────────────
    elif 'generate' in ops:
        if kb_doc_ids:
            claims = Claim.query.filter(
                Claim.knowledge_id.in_(kb_doc_ids),
                Claim.is_approved == True,
            ).all()
            claims_list = [c.to_dict() for c in claims]
            # Attach embeddings for filtering (not included in to_dict)
            emb_map = {c.id: c.embedding for c in claims if c.embedding}
            for cd in claims_list:
                if cd['id'] in emb_map:
                    cd['embedding'] = emb_map[cd['id']]

            if not claims_list:
                chat_text = (
                    "No approved claims found in the selected documents. "
                    "Please review and approve claims on the Knowledge Base page before generating."
                )
            else:
                claims_by_id = {c['id']: c for c in claims_list}
                # Filter claims by embedding similarity
                filtered_claims = _filter_claims_by_embedding(
                    prompt, claims_list, doc_outlines,
                )
                try:
                    print(f"[DEBUG] Using generate_slide_spec path (fresh generation)")
                    spec = generate_slide_spec(
                        prompt, filtered_claims, brand_guidelines,
                        target_audience, audience_rules, slim_history,
                        component_patterns=component_patterns,
                        doc_outline=combined_outline,
                    )
                    _finalize_spec(spec, claims_by_id, claims_list, is_edit=False)
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
            doc_outline=combined_outline,
            current_spec=prev_spec,
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

    print(f"[PIPELINE:{session_id}] Result: html={'yes' if html_content else 'no'} ({len(html_content) if html_content else 0} chars), chat={'yes' if chat_text else 'no'}")
    if review_report and 'spec' in review_report:
        spec_slides = review_report['spec'].get('slides', [])
        print(f"[PIPELINE:{session_id}] Spec: {len(spec_slides)} slides, layouts={[s.get('layout') for s in spec_slides]}")

    assistant_msg = Message(
        session_id=session_id,
        role='assistant',
        content=chat_text or 'Slides generated — check the output panel.',
        html_content=html_content,
        review_report=review_report,
    )
    db.session.add(assistant_msg)
    db.session.commit()

    # Broadcast slide content update to other users in the session room
    if html_content:
        socketio.emit('presence:content_updated', {
            'session_id': session_id,
            'html': html_content,
            'message': chat_text or 'Slides generated — check the output panel.',
        }, room=f'session:{session_id}')

    return jsonify(assistant_msg.to_dict()), 201


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@chat_bp.route('/api/sessions/<int:session_id>/messages/stream', methods=['POST'])
def send_message_stream(session_id):
    """SSE streaming endpoint — sends progress events as slides are generated."""
    ChatSession.query.get_or_404(session_id)
    data = request.get_json(force=True)
    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'error': 'prompt is required'}), 400

    current_draft = data.get('current_draft') or None
    ds_id = data.get('design_system_id')
    kb_doc_ids = data.get('kb_doc_ids') or []
    target_audience = data.get('target_audience') or None

    # Capture Flask app for thread-safe DB access
    app = current_app._get_current_object()

    # Pre-load all data we need inside the request context
    design_tokens = None
    brand_guidelines = None
    component_patterns = None
    ds_assets = []
    audience_rules = None
    if ds_id:
        ds = DesignSystem.query.get(ds_id)
        if ds:
            design_tokens = ds.tokens
            brand_guidelines = ds.brand_guidelines
            component_patterns = ds.component_patterns
            audience_rules = (ds.brand_guidelines or {}).get('audienceRules')
            raw_assets = DesignSystemAsset.query.filter_by(design_system_id=ds_id).all()
            ds_assets = [a.to_dict() for a in raw_assets]

    prior_messages = (
        Message.query.filter_by(session_id=session_id)
        .order_by(Message.created_at.asc()).all()
    )
    slim_history = []
    for m in prior_messages:
        if m.role == 'user':
            slim_history.append({'role': 'user', 'content': m.content})
        else:
            slim_history.append({'role': 'assistant', 'content': m.content or '[slides generated]'})

    kb_texts = []
    stream_doc_outlines = []
    if kb_doc_ids:
        items = KnowledgeItem.query.filter(KnowledgeItem.id.in_(kb_doc_ids)).all()
        kb_texts = [item.text_content for item in items if item.text_content]
        for item in items:
            if item.doc_outline:
                stream_doc_outlines.extend(item.doc_outline)
    stream_outline = _strip_outline_embeddings(stream_doc_outlines) if stream_doc_outlines else None

    prev_spec = None
    prev_html = None
    for m in reversed(prior_messages):
        rr = m.review_report
        if rr and isinstance(rr, dict) and 'spec' in rr:
            prev_spec = rr['spec']
            prev_html = m.html_content
            break

    # Save user message
    user_msg = Message(session_id=session_id, role='user', content=prompt)
    db.session.add(user_msg)
    db.session.commit()

    print(f"[PIPELINE:{session_id}] [stream] Incoming prompt: \"{prompt[:120]}\"")
    print(f"[PIPELINE:{session_id}] [stream] selected_docs={kb_doc_ids}, has_deck={bool(prev_spec)}, has_kb={bool(kb_texts)}")
    ops = orchestrate(prompt, slim_history, has_kb=bool(kb_texts), has_deck=bool(prev_spec))
    print(f"[PIPELINE:{session_id}] [stream] Orchestrator decision: {ops}")

    # Event queue for cross-thread communication
    eq = queue.Queue()

    def _run_pipeline():
        """Runs the generation pipeline in a background thread, pushing SSE events."""
        with app.app_context():
            html_content = None
            review_report = None
            chat_text = None
            spec = None

            claims_list = []
            claims_by_id = {}

            if kb_doc_ids:
                claims = Claim.query.filter(
                    Claim.knowledge_id.in_(kb_doc_ids),
                    Claim.is_approved == True,
                ).all()
                claims_list = [c.to_dict() for c in claims]
                # Attach embeddings for filtering (not included in to_dict)
                emb_map = {c.id: c.embedding for c in claims if c.embedding}
                for cd in claims_list:
                    if cd['id'] in emb_map:
                        cd['embedding'] = emb_map[cd['id']]
                claims_by_id = {c['id']: c for c in claims_list}

            if not claims_list and ('generate' in ops or 'edit' in ops):
                eq.put(('chat', {
                    'text': 'No approved claims found in the selected documents. '
                            'Please review and approve claims on the Knowledge Base page before generating.'
                }))
                eq.put(('done', {}))
                return

            try:
                # ── Edit path ─────────────────────────────────
                if 'edit' in ops:
                    if not prev_spec:
                        eq.put(('chat', {'text': "There's no existing deck to edit yet. Try asking me to generate a new deck first."}))
                        eq.put(('done', {}))
                        return

                    eq.put(('status', {'step': 'Editing slide spec...'}))
                    spec = edit_slide_spec(
                        prompt, prev_spec, claims_list, slim_history,
                        brand_guidelines=brand_guidelines,
                    )
                    spec_changed = (spec != prev_spec)
                    if not spec_changed and prev_html:
                        html_content = prev_html
                        review_report = build_compliance_trace(spec, claims_by_id)
                        review_report['spec'] = spec
                        eq.put(('html_complete', {'html': html_content}))
                    else:
                        eq.put(('status', {'step': 'Rendering slides...'}))

                        def _on_edit_chunk(text):
                            eq.put(('html_chunk', {'chunk': text}))

                        # Finalize (validate + render)
                        errors = validate_slide_spec(spec, list(claims_by_id.keys()), brand_guidelines)
                        if errors:
                            spec = generate_slide_spec(
                                prompt + f"\n\nFix these validation errors: {'; '.join(errors)}",
                                claims_list, brand_guidelines,
                                target_audience, audience_rules, slim_history,
                                component_patterns=component_patterns,
                                doc_outline=stream_outline,
                            )
                        try:
                            html_content = render_spec_to_html(
                                spec, claims_by_id, design_tokens,
                                brand_guidelines, ds_assets,
                                current_html=prev_html,
                                component_patterns=component_patterns,
                                on_chunk=_on_edit_chunk,
                            )
                        except Exception:
                            html_content = render_deck(
                                spec, claims_by_id, design_tokens, brand_guidelines, ds_assets,
                            )
                        review_report = build_compliance_trace(spec, claims_by_id)
                        review_report['spec'] = spec
                        eq.put(('html_complete', {'html': html_content}))

                # ── Generation path ───────────────────────────
                elif 'generate' in ops:
                    eq.put(('status', {'step': 'Planning narrative...'}))

                    # Filter claims by embedding similarity
                    filtered_claims = _filter_claims_by_embedding(
                        prompt, claims_list, stream_doc_outlines,
                    )

                    def _on_slide_ready(idx, slide):
                        eq.put(('slide_ready', {'index': idx, 'layout': slide.get('layout', ''), 'title': slide.get('slide_title', '')}))

                    spec = generate_slide_spec(
                        prompt, filtered_claims, brand_guidelines,
                        target_audience, audience_rules, slim_history,
                        component_patterns=component_patterns,
                        on_slide_ready=_on_slide_ready,
                        doc_outline=stream_outline,
                    )

                    # Validate
                    errors = validate_slide_spec(spec, list(claims_by_id.keys()), brand_guidelines)
                    if errors:
                        eq.put(('status', {'step': 'Fixing validation errors...'}))
                        retry_spec = generate_slide_spec(
                            prompt + f"\n\nFix these validation errors: {'; '.join(errors)}",
                            claims_list, brand_guidelines,
                            target_audience, audience_rules, slim_history,
                            component_patterns=component_patterns,
                            doc_outline=stream_outline,
                        )
                        retry_errors = validate_slide_spec(retry_spec, list(claims_by_id.keys()), brand_guidelines)
                        if retry_errors:
                            eq.put(('chat', {'text': f"Could not generate compliant slides: {'; '.join(retry_errors)}"}))
                            eq.put(('done', {}))
                            return
                        spec = retry_spec

                    # ISI injection (same logic as _finalize_spec)
                    isi_claims = {cid: c for cid, c in claims_by_id.items() if c.get('claim_type') == 'isi'}
                    if isi_claims:
                        clinical = {'big_stat', 'stat_row', 'two_column', 'three_column_cards',
                                    'comparison_table', 'data_table', 'subgroup_forest'}
                        for slide in spec.get('slides', []):
                            if slide.get('layout') in clinical:
                                footer_ids = {fc.get('claim_id') for fc in slide.get('footer_claims', [])}
                                if not any(cid in footer_ids for cid in isi_claims):
                                    slide_cids = []
                                    h = slide.get('headline', {}).get('claim_id')
                                    if h:
                                        slide_cids.append(h)
                                    slide_cids += [b['claim_id'] for b in slide.get('body_claims', []) if b.get('claim_id')]
                                    slide_tags = set()
                                    for cid in slide_cids:
                                        slide_tags.update(t.lower() for t in (claims_by_id.get(cid, {}).get('tags') or []))

                                    def isi_relevance(isi_id):
                                        isi_tags = set(t.lower() for t in (isi_claims[isi_id].get('tags') or []))
                                        return len(isi_tags & slide_tags)

                                    best_isi = max(isi_claims.keys(), key=isi_relevance)
                                    slide.setdefault('footer_claims', []).append({'claim_id': best_isi})

                    # Render HTML with streaming chunks
                    eq.put(('status', {'step': 'Rendering slides...'}))

                    def _on_render_chunk(text):
                        eq.put(('html_chunk', {'chunk': text}))

                    try:
                        html_content = render_spec_to_html(
                            spec, claims_by_id, design_tokens,
                            brand_guidelines, ds_assets,
                            component_patterns=component_patterns,
                            on_chunk=_on_render_chunk,
                        )
                    except Exception:
                        html_content = render_deck(
                            spec, claims_by_id, design_tokens, brand_guidelines, ds_assets,
                        )

                    eq.put(('html_complete', {'html': html_content}))

                    # Compliance (non-blocking — user already has HTML)
                    review_report = build_compliance_trace(spec, claims_by_id)
                    review_report['spec'] = spec
                    visual_issues = _verify_visual_injections(html_content, spec, claims_by_id)
                    if visual_issues:
                        review_report.setdefault('visual_issues', []).extend(visual_issues)
                        print(f"[WARN] Visual injection issues: {visual_issues}")
                    if kb_texts:
                        try:
                            soft = review_content(html_content, kb_texts)
                            review_report['soft_checks'] = soft
                        except Exception:
                            pass
                    eq.put(('review', {'review_report': review_report}))

                # ── Chat-only path ────────────────────────────
                if 'chat' in ops and not chat_text and not html_content:
                    eq.put(('status', {'step': 'Thinking...'}))
                    chat_text = chat_response(
                        prompt,
                        kb_texts=kb_texts or None,
                        history=slim_history,
                        brand_guidelines=brand_guidelines,
                        ds_assets=ds_assets,
                        target_audience=target_audience,
                        audience_rules=audience_rules,
                        component_patterns=component_patterns,
                        doc_outline=stream_outline,
                        current_spec=prev_spec,
                    )

                # Build summary (LLM-based, matches non-streaming path)
                if html_content and not chat_text:
                    eq.put(('status', {'step': 'Summarizing...'}))
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

                chat_text = chat_text or 'Slides generated — check the output panel.'
                eq.put(('chat', {'text': chat_text}))

                # Save assistant message
                assistant_msg = Message(
                    session_id=session_id,
                    role='assistant',
                    content=chat_text,
                    html_content=html_content,
                    review_report=review_report,
                )
                db.session.add(assistant_msg)
                db.session.commit()

                eq.put(('done', {'message': assistant_msg.to_dict() if assistant_msg else {}}))

                if html_content:
                    socketio.emit('presence:content_updated', {
                        'session_id': session_id,
                        'html': html_content,
                        'message': chat_text,
                    }, room=f'session:{session_id}')

            except Exception as e:
                eq.put(('chat', {'text': f'Generation failed: {e}'}))
                # Save error message
                err_msg = Message(session_id=session_id, role='assistant', content=f'Generation failed: {e}')
                db.session.add(err_msg)
                db.session.commit()
                eq.put(('done', {'message': err_msg.to_dict()}))

    def generate_sse():
        thread = threading.Thread(target=_run_pipeline, daemon=True)
        thread.start()

        while True:
            try:
                event, payload = eq.get(timeout=120)
            except queue.Empty:
                yield _sse_event('done', {'error': 'timeout'})
                return
            yield _sse_event(event, payload)
            if event == 'done':
                return

    return Response(
        generate_sse(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
