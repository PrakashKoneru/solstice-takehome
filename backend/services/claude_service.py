import os
import json
import anthropic
from typing import Optional

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    return _client


EMPTY_TOKENS = {
    "colors": {
        "palette":  {"primary": "", "secondary": ""},
        "fill":     {"default": "", "subtle": ""},
        "border":   {"default": "", "strong": ""},
        "text":     {"default": "", "muted": "", "inverse": ""},
        "brand":    {"primary": "", "secondary": ""},
        "state":    {"success": "", "error": "", "warning": "", "highlight": ""},
    },
    "fonts":        {"hero": "", "h1": "", "h2": "", "body": "", "caption": ""},
    "fontSizes":    {"hero": "", "h1": "", "h2": "", "body": "", "caption": ""},
    "fontWeights":  {"hero": "", "h1": "", "h2": "", "body": "", "caption": ""},
    "lineHeight":   {"hero": "", "h1": "", "h2": "", "body": "", "caption": ""},
    "grid":         {"columns": 12, "gutter": "", "margin": ""},
    "spacing":      {"xs": "", "sm": "", "md": "", "lg": "", "xl": "", "2xl": ""},
    "breakpoints":  {"sm": "", "md": "", "lg": "", "xl": ""},
    "shadows":      {"sm": "", "md": "", "lg": ""},
    "borderRadius": {"sm": "", "md": "", "lg": "", "full": ""},
    "components":   {"cta": {"background": "", "text": "", "borderRadius": "", "border": ""}},
}

SYSTEM_PROMPT = """You are a design token extraction assistant. Extract design tokens from the provided style guide text and return ONLY a valid JSON object matching this exact schema. Leave fields as empty strings if not found — do not invent values. Do not add keys outside the schema.

Schema:
{
  "colors": {
    "palette":  { "primary": "", "secondary": "" },
    "fill":     { "default": "", "subtle": "" },
    "border":   { "default": "", "strong": "" },
    "text":     { "default": "", "muted": "", "inverse": "" },
    "brand":    { "primary": "", "secondary": "" },
    "state":    { "success": "", "error": "", "warning": "", "highlight": "" }
  },
  "fonts":        { "hero": "", "h1": "", "h2": "", "body": "", "caption": "" },
  "fontSizes":    { "hero": "", "h1": "", "h2": "", "body": "", "caption": "" },
  "fontWeights":  { "hero": "", "h1": "", "h2": "", "body": "", "caption": "" },
  "lineHeight":   { "hero": "", "h1": "", "h2": "", "body": "", "caption": "" },
  "grid":         { "columns": 12, "gutter": "", "margin": "" },
  "spacing":      { "xs": "", "sm": "", "md": "", "lg": "", "xl": "", "2xl": "" },
  "breakpoints":  { "sm": "", "md": "", "lg": "", "xl": "" },
  "shadows":      { "sm": "", "md": "", "lg": "" },
  "borderRadius": { "sm": "", "md": "", "lg": "", "full": "" },
  "components":   { "cta": { "background": "", "text": "", "borderRadius": "", "border": "" } }
}"""


CHAT_SYSTEM_PROMPT = """You are a pharma slide creation assistant embedded in a content studio tool.

SESSION PURPOSE:
Each session exists to build a branded slide deck for HCP audiences. Every slide produced in this session must:
- Be grounded exclusively in the approved Knowledge Base documents selected for this session
- Apply the brand design system (colors, fonts, spacing, layout) configured for this session
- Follow the brand guidelines (tone, required elements, prohibited elements) of the selected design system
- Be compliant in tone and accurate for healthcare professional audiences

YOUR ROLE IN THIS MODE:
You help the user plan, refine, and discuss their slide deck. You MUST NEVER output HTML, CSS, or code of any kind — not in code blocks, not inline, not as examples. Slide generation is handled automatically by a separate agent the moment the user sends a creation command. Your job is only conversation.

CONTEXT AWARENESS:
You have full visibility into this session's conversation history. The history shows "[slides generated]" wherever a slide was produced — that means slides exist in the output panel. When a user references "the current slide" or "slide 2", acknowledge what has been built. Never tell the user you cannot see their slides or documents.

Keep responses concise. When the user asks what they can create, reference the loaded Knowledge Base documents and brand assets specifically. Guide them toward actionable next steps."""


BRAND_GUIDELINES_SYSTEM_PROMPT = """You are a brand analyst. Extract brand guidelines from the provided style guide text and return ONLY a valid JSON object matching this exact schema. Leave fields as empty strings or empty arrays if not found — do not invent values.

Schema:
{
  "personality": [],
  "primaryFont": "",
  "secondaryFont": "",
  "fontUsageRule": "",
  "colorHierarchy": "",
  "layoutPrinciples": "",
  "tone": "",
  "requiredElements": [],
  "prohibited": [],
  "hallmark": ""
}"""

SLIDE_TEMPLATES_SYSTEM_PROMPT = """You are a slide designer. Based on the provided style guide, define 4-6 recommended slide template layouts as a JSON array. Each template should be practical for pharma HCP content.

Return ONLY a valid JSON array matching this schema:
[
  {
    "name": "",
    "description": "",
    "layout": "",
    "bestFor": ""
  }
]

Examples of good templates: 3-column data cards, 2-column comparison, key stat + supporting cards, full-width data table, efficacy summary with hero number."""


CONTENT_SYSTEM_PROMPT = """You are a pharma slide generation assistant producing professional visual aid slides for HCP audiences.

OUTPUT FORMAT — non-negotiable:
- Output ONLY raw HTML. Zero explanation, zero markdown, zero code fences, zero text of any kind outside the HTML.
- Each slide is a <div data-slide> with these exact inline styles: width:1024px; height:576px; overflow:hidden; position:relative; background:#ffffff; box-sizing:border-box;
- For ONE slide: output that single <div data-slide> element.
- For MULTIPLE slides: output each <div data-slide> one after another, no outer wrapper.
- No <html>, <head>, <body>, <style>, or <script> tags. All styles inline. No external URLs or web fonts.

SLIDE AESTHETIC — professional pharma visual aid:
- Background: white (#ffffff) or very light grey (#f5f6f8). Slides are clinical and airy — NOT dark PowerPoint-style.
- Structure top-to-bottom:
    1. Thin accent bar at very top: height 6px, full width, brand primary color (default #7c3aed if no tokens).
    2. Header row (height ~70px): bold headline left (font-size 24–30px, dark navy #1e1b4b or brand color), product identity right (product name + strength, 11px, brand color).
    3. Optional thin subtitle / indication line (font-size 11px, muted color, full-width strip with light background).
    4. Content area: remaining height. Choose the layout that best fits:
       • BIG STAT: one giant number (64–80px bold, brand color) + descriptor — for single KPI slides
       • STAT ROW: 2–3 large callouts side by side (number + label, colored accent)
       • 2-COLUMN: text/bullets left (~55%), visual or stat panel right (~45%)
       • 3-COLUMN CARDS: white cards with border #e2e8f0, subtle shadow, icon + label + content
       • COMPARISON: left column dark (competitor), center highlight (brand), right column — always horizontal
       • DATA TABLE: striped rows, header band in brand primary, for clinical numbers
       • FLOW DIAGRAM: left-to-right boxes connected by arrows, for study designs
    5. Footer strip (height 28px, background #1e1b4b): small disclaimer text in white, 9px.
- Typography: Arial, Helvetica, sans-serif throughout. Bold for headlines, regular for body. Body 12–13px.
- Color: use accent/brand color on numbers, borders, chip labels — not as full-bleed section backgrounds.
- Generous whitespace: padding 20px sides, 12px between sections. Slides feel open, not cramped.
- Everything fits within 576px. overflow:hidden clips anything that doesn't.

CONTEXT:
- Apply <design_tokens> colors/fonts. Let them override the defaults above.
- Respect <brand_guidelines>: personality, prohibited elements, required elements.
- Use closest <slide_templates> layout when provided.
- <brand_assets> lists available brand icons/logos with their URLs. Use <img src="[url]" style="..."> to embed them. Prefer logos on title slides, icons in content areas.

DECK MANAGEMENT — critical rules:
- The conversation history contains every slide previously generated in this session as HTML.
- <current_draft> (if provided) is the current state of the deck — it may include user inline edits.
- When ADDING a slide: output the full updated deck — all existing <div data-slide> elements PLUS the new one in the correct position.
- When REORDERING: output all slides in the new order, content unchanged.
- When EDITING one slide: output the full deck with only that slide modified.
- NEVER silently drop an existing slide. If a slide exists in <current_draft> or the conversation history, it must appear in your output unless the user explicitly says to remove it.
- If there are no prior slides, generate only what was asked.

CONTENT RULES:
- Use ONLY facts explicitly present in <knowledge_base>. No outside knowledge.
- If content cannot be grounded in KB, output one plain-text sentence explaining what is missing — no HTML.
- Compliant HCP tone. Every claim traceable to KB."""


ORCHESTRATOR_SYSTEM_PROMPT = """You are the orchestrator for a pharma content studio. Your job is to read the user's message and conversation history, then decide which operations to run for this turn.

Available operations:
- "generate"  — run the slide content agent (creates/edits/reorders slides)
- "review"    — run the compliance review agent (always paired with generate when KB docs exist)
- "chat"      — run the conversational agent (answers questions, guides the user, explains what was done)

Rules:
- If the user uses ANY word indicating slide creation or editing (create, build, generate, make, add, edit, update, reorder, move, fix, change) AND has_kb is true → return ["generate", "review"].
- If the user is asking a question, planning, or exploring options (what, how, which, can you, tell me, show me, list) → return ["chat"].
- If has_kb is false and the user wants to generate → return ["chat"] only.
- When unsure → return ["chat"].
- Never return ["generate", "review", "chat"] together — generation and chat are separate turns.

Respond with ONLY valid JSON — no explanation:
{"ops": ["chat"]} or {"ops": ["generate", "review"]}"""


def orchestrate(prompt: str, history: list, has_kb: bool) -> list:
    """Returns list of operations to run: subset of ['generate', 'review', 'chat']"""
    client = _get_client()
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=40,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            messages=history + [{'role': 'user', 'content': f'has_kb: {str(has_kb).lower()}\n\nUser message: {prompt}'}],
        )
        raw = _parse_json_response(msg.content[0].text)
        result = json.loads(raw)
        return result.get('ops', ['chat'])
    except Exception:
        return ['chat']


def chat_response(
    prompt: str,
    kb_texts: Optional[list] = None,
    history: Optional[list] = None,
    brand_guidelines: Optional[dict] = None,
    slide_templates: Optional[list] = None,
    ds_assets: Optional[list] = None,
) -> str:
    client = _get_client()
    context_parts = []
    if brand_guidelines:
        context_parts.append(f"<brand_guidelines>\n{json.dumps(brand_guidelines, indent=2)}\n</brand_guidelines>")
    if slide_templates:
        context_parts.append(f"<slide_templates>\n{json.dumps(slide_templates, indent=2)}\n</slide_templates>")
    if ds_assets:
        asset_list = [{'name': a['name'], 'type': a['asset_type']} for a in ds_assets]
        context_parts.append(f"<brand_assets>\n{json.dumps(asset_list, indent=2)}\n</brand_assets>")
    if kb_texts:
        combined = "\n\n---\n\n".join(kb_texts)
        context_parts.append(f"<knowledge_base>\n{combined}\n</knowledge_base>")
    user_content = "\n\n".join(context_parts + [prompt]) if context_parts else prompt
    messages = list(history or []) + [{'role': 'user', 'content': user_content}]
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=512,
        system=CHAT_SYSTEM_PROMPT,
        messages=messages,
    )
    return message.content[0].text.strip()


def generate_content(
    prompt: str,
    design_tokens: Optional[dict] = None,
    brand_guidelines: Optional[dict] = None,
    slide_templates: Optional[list] = None,
    ds_assets: Optional[list] = None,
    kb_texts: Optional[list] = None,
    current_draft: Optional[str] = None,
    history: Optional[list] = None,
) -> str:
    client = _get_client()

    context_parts = []
    if design_tokens:
        context_parts.append(f"<design_tokens>\n{json.dumps(design_tokens, indent=2)}\n</design_tokens>")
    if brand_guidelines:
        context_parts.append(f"<brand_guidelines>\n{json.dumps(brand_guidelines, indent=2)}\n</brand_guidelines>")
    if slide_templates:
        context_parts.append(f"<slide_templates>\n{json.dumps(slide_templates, indent=2)}\n</slide_templates>")
    if ds_assets:
        asset_list = [{'name': a['name'], 'type': a['asset_type'], 'url': a['file_url']} for a in ds_assets]
        context_parts.append(f"<brand_assets>\n{json.dumps(asset_list, indent=2)}\n</brand_assets>")
    if kb_texts:
        combined = "\n\n---\n\n".join(kb_texts)
        context_parts.append(f"<knowledge_base>\n{combined}\n</knowledge_base>")
    if current_draft:
        context_parts.append(f"<current_draft>\n{current_draft}\n</current_draft>")

    user_content = prompt
    if context_parts:
        user_content = "\n\n".join(context_parts) + "\n\n" + prompt

    messages = list(history or []) + [{'role': 'user', 'content': user_content}]

    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=4096,
        system=CONTENT_SYSTEM_PROMPT,
        messages=messages,
    )
    return message.content[0].text.strip()


REVIEW_SYSTEM_PROMPT = """You are a pharmaceutical compliance reviewer. Your job is to audit AI-generated HTML content against a provided knowledge base.

Rules:
- Extract every factual claim from the HTML draft (statistics, efficacy data, safety statements, dosing info, study references)
- For each claim, check whether it is explicitly supported by the provided knowledge base documents
- Output ONLY a valid JSON object matching this exact schema — no explanation, no markdown, no code fences:

{
  "verdict": "approved" | "flagged" | "blocked",
  "confidence": <float 0.0-1.0>,
  "flags": [
    {
      "claim": "<exact claim text>",
      "status": "verified" | "unsupported" | "inferred",
      "note": "<source reference or reason>"
    }
  ],
  "summary": "<one sentence summary>"
}

Verdict rules:
- "approved" — all claims are verified against KB
- "flagged" — some claims are unsupported or inferred; content usable but requires human review
- "blocked" — majority of claims are unsupported or content contradicts KB

Do not generate or add any new content. Only evaluate what is in the draft."""


def review_content(html: str, kb_texts: list) -> dict:
    client = _get_client()
    kb_combined = "\n\n---\n\n".join(kb_texts)
    user_content = f"<draft_html>\n{html}\n</draft_html>\n\n<knowledge_base>\n{kb_combined}\n</knowledge_base>\n\nAudit the draft HTML against the knowledge base. Return only the JSON review report."
    try:
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=1024,
            system=REVIEW_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': user_content}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        return json.loads(raw)
    except Exception:
        return {
            'verdict': 'flagged',
            'confidence': 0.0,
            'flags': [],
            'summary': 'Review could not be completed. Manual verification required.',
        }


def _parse_json_response(raw: str):
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
    return raw.strip()


def extract_brand_guidelines(pdf_text: str, pdf_filepath: Optional[str] = None) -> dict:
    client = _get_client()

    # Vision-based extraction: render pages and pass to Claude
    if pdf_filepath:
        from services.pdf_service import render_pdf_pages_as_images
        pages = render_pdf_pages_as_images(pdf_filepath, max_pages=15)
        if pages:
            content: list = []
            for b64, mime in pages:
                content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': mime, 'data': b64}})
            content.append({
                'type': 'text',
                'text': (
                    'These are pages from a pharma brand style guide. '
                    'Extract ALL brand guidelines you can find across every page — personality traits, fonts, colors, tone, layout rules, required elements, prohibited elements, brand hallmark. '
                    'Return only the JSON object.'
                ),
            })
            try:
                message = client.messages.create(
                    model='claude-sonnet-4-6',
                    max_tokens=2048,
                    system=BRAND_GUIDELINES_SYSTEM_PROMPT,
                    messages=[{'role': 'user', 'content': content}],
                )
                raw = _parse_json_response(message.content[0].text)
                return json.loads(raw)
            except Exception:
                pass  # fall through to text-based

    # Text-based fallback
    try:
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=2048,
            system=BRAND_GUIDELINES_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': f'Extract brand guidelines from this style guide:\n---\n{pdf_text}\n---\nReturn only the JSON object.'}],
        )
        raw = _parse_json_response(message.content[0].text)
        return json.loads(raw)
    except Exception:
        return {}


def extract_slide_templates(pdf_text: str, pdf_filepath: Optional[str] = None) -> list:
    client = _get_client()

    # Vision-based extraction
    if pdf_filepath:
        from services.pdf_service import render_pdf_pages_as_images
        pages = render_pdf_pages_as_images(pdf_filepath, max_pages=15)
        if pages:
            content: list = []
            for b64, mime in pages:
                content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': mime, 'data': b64}})
            content.append({
                'type': 'text',
                'text': (
                    'These are pages from a pharma brand style guide. '
                    'Identify all slide/page layout templates shown or described. '
                    'Return only the JSON array.'
                ),
            })
            try:
                message = client.messages.create(
                    model='claude-sonnet-4-6',
                    max_tokens=2048,
                    system=SLIDE_TEMPLATES_SYSTEM_PROMPT,
                    messages=[{'role': 'user', 'content': content}],
                )
                raw = _parse_json_response(message.content[0].text)
                return json.loads(raw)
            except Exception:
                pass

    # Text-based fallback
    try:
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=2048,
            system=SLIDE_TEMPLATES_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': f'Based on this style guide, define recommended slide templates:\n---\n{pdf_text}\n---\nReturn only the JSON array.'}],
        )
        raw = _parse_json_response(message.content[0].text)
        return json.loads(raw)
    except Exception:
        return []


def extract_design_tokens(pdf_text: str) -> dict:
    client = _get_client()
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{
            'role': 'user',
            'content': f'Extract all design tokens from this style guide:\n---\n{pdf_text}\n---\nReturn only the JSON object, no explanation.',
        }],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return EMPTY_TOKENS
