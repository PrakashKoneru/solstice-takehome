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

BRAND GUIDELINES — strict sourcing rule:
When answering questions about brand guidelines, design rules, or what is/isn't allowed:
- ONLY cite rules that are explicitly present in the <brand_guidelines> JSON provided to you.
- Quote or paraphrase the exact field values. Do not invent, extrapolate, or add rules that are not in the JSON.
- If a specific rule is NOT in the JSON, say "That isn't captured in the loaded brand guidelines" — never guess or infer.
- Never fabricate prohibited elements, required elements, or personality traits not listed in the JSON.
- When answering correctly from the guidelines, be concise — quote the relevant rule once, don't expand it into bullet lists of inferred sub-rules.

Keep responses concise. When the user asks what they can create, reference the loaded Knowledge Base documents and brand assets specifically. Guide them toward actionable next steps."""


BRAND_GUIDELINES_SYSTEM_PROMPT = """You are a brand analyst. Extract brand guidelines from the provided style guide and return ONLY a valid JSON object. Leave fields as empty strings or empty arrays if not found — do not invent values.

The top-level shape is fixed. The keys inside "audienceRules" and "otherRelevantGuidelines" are dynamic — use the exact names found in the document.

Fixed schema (top-level keys are always present):
{
  "supportedAudiences": [],
  "audienceRules": {},
  "otherRelevantGuidelines": {},
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
}

"audienceRules" — populate dynamically:
Identify every audience type the document explicitly addresses. For each, add a key using the audience's exact name from the document. Under that key, add "rules": [] containing every directive the brand defines for that audience — tone, visual treatment, copy style, required elements, prohibited content, CTA guidance, content depth, or anything else stated. Each rule is a plain string capturing the brand's intent. Only include audiences and rules explicitly present in the document — never infer or invent.

Example shape (names and rules are illustrative only — use what is in the document):
"audienceRules": {
  "Healthcare Professionals": {
    "rules": ["Lead with clinical data", "Use approved indication language in all headers"]
  }
}

"otherRelevantGuidelines" — populate dynamically:
If the document has a table of contents, use it to identify every named section. For every section that is not one of the fixed fields above, add it here — even if some of its rules partially overlap with prohibited or requiredElements. Overlap is fine; completeness is the priority. This includes — but is not limited to — ADA compliance, digital best practices, accessibility standards, microsites, HCP applications, patient applications, print specifications, animation rules, co-branding rules, regulatory copy requirements, sign-off rules, ISI usage, and any other named section. For each section, add a key using the section's exact name from the document. Under that key, add "rules": [] containing every directive in that section as a plain string. Do not discard any section or any rule within a section.

Example shape (names and rules are illustrative only — use what is in the document):
"otherRelevantGuidelines": {
  "ADA Compliance": {
    "rules": ["Minimum contrast ratio 4.5:1 for all body text", "All images require descriptive alt text"]
  }
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


CONTENT_SYSTEM_PROMPT = """You are a pharma slide generation assistant producing professional branded slides for the intended audience.

OUTPUT FORMAT — non-negotiable:
- Output ONLY raw HTML. Zero explanation, zero markdown, zero code fences, zero text of any kind outside the HTML.
- Each slide is a <div data-slide> with these exact inline styles: width:1024px; height:576px; overflow:hidden; position:relative; box-sizing:border-box;
- For ONE slide: output that single <div data-slide> element.
- For MULTIPLE slides: output each <div data-slide> one after another, no outer wrapper.
- No <html>, <head>, <body>, or <script> tags. All styles must be inline EXCEPT: you may emit one <style> block before the first <div data-slide> solely to load the brand font via Google Fonts @import (e.g. @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;700&display=swap');). No other external URLs anywhere.

BRAND GUIDELINES — primary source of truth:
When <brand_guidelines> is present, every field is a hard constraint that overrides any default below:

1. PRODUCT NAME / HALLMARK: The `hallmark` field defines the brand's foundational graphic and naming identity. Render the product name EXACTLY as it appears in the guidelines — including exact capitalisation, punctuation, and any registered marks. Never paraphrase or reformat it.

2. FONTS: Use `primaryFont` for all headlines, product name, and key callouts. Use `secondaryFont` for body and captions when copy is dense. Apply `fontUsageRule` literally. Load the font via the @import rule described in OUTPUT FORMAT — never fall back to Arial, Helvetica, or system fonts.

3. COLORS: Apply `colorHierarchy` exactly. Use the primary brand color for accent bars, key stat numbers, header accents. Use secondary colors only as accents. Never use colors outside the approved palette. Use exact hex values from `<design_tokens>` when available.

4. BRAND VISUAL LANGUAGE — applies to every element you create:
The `hallmark` and `layoutPrinciples` define a visual language that must cascade to every design decision on every slide — not just icons. If the brand calls for circular shapes, soft curves, and flowing gradients, then every container, card, border, divider, background element, and frame must express that same language. Before placing any element, ask: does this shape, edge, and color feel like it belongs in this brand's world? If the `prohibited` list bans sharp edges, that ban applies to layout containers, data cards, image frames, and every div you create — not just decorative elements. There are no exceptions for "structural" elements.

5. LAYOUT: Apply `layoutPrinciples` literally — generous whitespace, structural elements (accent bars, gradient strokes, violators) placed correctly. Do not invent decorative patterns — colored card borders, side accents, divider lines, or any other visual element — that are not explicitly described in `brand_guidelines`, `slide_templates`, or `<design_tokens>`. If the brand does not specify card border colors, cards have no colored border. Every decoration must have a source in the guidelines.

POSITIONING — non-negotiable:
- Use CSS flexbox or grid for ALL content layout. Never use position:absolute for content blocks, text, icons, cards, or any element that contains readable content — absolute positioning causes overlapping when content height varies.
- position:absolute is permitted ONLY for purely decorative background elements (gradient overlays, hallmark arcs, background shapes) that sit behind content and contain no text.
- The slide is exactly 576px tall. Reserve the footer (approx 60px) before laying out body content. The remaining ~516px must contain all body content without overflow. If content doesn't fit, reduce font sizes or cut lower-priority content — never let elements overlap.

6. TONE: Every word of copy must match the `tone` field. Scientific/direct = no colloquialisms. Confident/energetic = frame data as practice-changing outcomes.

7. REQUIRED ELEMENTS: Every item in `requiredElements` must appear on every slide — no exceptions. When the logo is required, it must appear as a standalone <img> sourced from <brand_assets> — never assumed to be contained within another image.

8. PROHIBITED ELEMENTS: No item in `prohibited` may appear anywhere in the output — check before choosing any color, shape, font, or element.

9. PERSONALITY: The `personality` array guides visual tone — weight, formality, energy, and copy density.

DESIGN TOKENS — use exact values, no approximations:
- Apply all values from <design_tokens> to their corresponding elements.
- Hex colors, font families, sizes, weights, line heights — use exactly as specified.

BRAND ASSETS:
- <brand_assets> lists available brand icons and logos with their Cloudinary URLs.
- Logos: scan <brand_assets> for an asset with type "logo" whose name most closely matches the product wordmark. Place it as a standalone <img style="object-fit:contain;" alt="logo"> in the header. Do not substitute any other asset — a product box, page screenshot, or approval image is not the logo. If no logo asset exists, you MUST still satisfy the required element by rendering the `hallmark` value as a text lockup in the header: product name in primaryFont, bold, brand primary color, with the generic name in secondaryFont below it at a smaller size. Omitting the logo entirely is not an option.
- Icons: use in content areas only when the icon type semantically matches the content being illustrated.
- Never invent, guess, or hotlink image URLs not explicitly listed in <brand_assets>.

CTAs — strict rule:
Never generate a call-to-action, button, or link of any kind unless the user has explicitly provided a destination URL in their request. Slides are static presentation assets — a CTA with no real destination is a design error. If no URL is provided, omit the CTA entirely and use the space for content.

SLIDE TEMPLATES:
- Use the closest matching template from <slide_templates> for each slide's content type.
- Follow the template's layout structure, not just its name.

LAYOUT OPTIONS — choose based on content type:
When no specific template is available, pick the layout that best fits the content:
- BIG STAT: one dominant number (large, bold, brand primary color) + descriptor — for single KPIs
- STAT ROW: 2–3 callouts side by side — for comparative data points
- 2-COLUMN: text/bullets left (~55%), visual or stat panel right (~45%)
- 3-COLUMN CARDS: equal cards with icon + label + content — for feature comparisons
- COMPARISON TABLE: structured comparison across rows/columns
- DATA TABLE: for clinical numbers with clear headers
- FLOW DIAGRAM: left-to-right connected boxes — for study designs or mechanisms

FALLBACK DEFAULTS (only when no design system is loaded):
- Background: white (#ffffff). Clinical and airy — not dark.
- Accent bar: 6px, top, purple (#7c3aed). Header: bold headline left, product name right.
- Footer: 28px strip, dark navy (#002855), 9px disclaimer text in white.
- Typography: Arial, Helvetica, sans-serif. Body 12–13px.
- Whitespace: 20px side padding, 12px between sections.

DECK MANAGEMENT — critical rules:
- The conversation history contains every slide previously generated in this session as HTML.
- <current_draft> (if provided) is the current state of the deck — it may include user inline edits.
- When ADDING a slide: output the full updated deck — all existing <div data-slide> elements PLUS the new one.
- When REORDERING: output all slides in the new order, content unchanged.
- When EDITING one slide: output the full deck with only that slide modified.
- NEVER silently drop an existing slide unless the user explicitly says to remove it.
- If there are no prior slides, generate only what was asked.

AUDIENCE — hard constraint when <target_audience> is set:
- Apply ONLY the rules from the matching entry in <audience_rules>. Rules defined for other audiences are irrelevant and must not influence this slide.
- Every item in the selected audience's rules is a hard constraint on copy, layout, color choices, gradient direction, icon vs chart preference, and visual style.
- GRADIENT: if the audience rules specify a gradient sequence (e.g. "begins with purple, progresses to blue, then green, then yellow"), implement it as a CSS linear-gradient in exactly that color order using the brand hex values from <design_tokens>. This overrides everything else — layoutPrinciples, defaults, and any other gradient description.
- If no audience rules exist for the selected audience, apply general brand guidelines and adapt tone and complexity to the audience type.

OTHER GUIDELINES — apply when <brand_guidelines> contains "otherRelevantGuidelines":
- Treat every rule in every section as an additional hard constraint — accessibility, ADA compliance, digital best practices, regulatory copy, sign-off format, and all others.
- The sign-off/footer section defines the exact format for the footer on every slide — follow it precisely.

CONTENT RULES:
- Use ONLY facts explicitly present in <knowledge_base>. No outside knowledge.
- If content cannot be grounded in KB, output one plain-text sentence explaining what is missing — no HTML.
- Every claim must be traceable to KB."""


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
    target_audience: Optional[str] = None,
    audience_rules: Optional[dict] = None,
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
    if target_audience:
        context_parts.append(f"<target_audience>\n{target_audience}\n</target_audience>")
    if audience_rules and target_audience and target_audience in audience_rules:
        context_parts.append(f"<audience_rules>\n{json.dumps({target_audience: audience_rules[target_audience]}, indent=2)}\n</audience_rules>")
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
    target_audience: Optional[str] = None,
    audience_rules: Optional[dict] = None,
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
        embeddable = [a for a in ds_assets if a.get('source') != 'page_render']
        if embeddable:
            asset_list = [{'name': a['name'], 'type': a['asset_type'], 'url': a['file_url']} for a in embeddable]
            context_parts.append(f"<brand_assets>\n{json.dumps(asset_list, indent=2)}\n</brand_assets>")
    if kb_texts:
        combined = "\n\n---\n\n".join(kb_texts)
        context_parts.append(f"<knowledge_base>\n{combined}\n</knowledge_base>")
    if current_draft:
        context_parts.append(f"<current_draft>\n{current_draft}\n</current_draft>")
    if target_audience:
        context_parts.append(f"<target_audience>\n{target_audience}\n</target_audience>")
    if audience_rules and target_audience and target_audience in audience_rules:
        context_parts.append(f"<audience_rules>\n{json.dumps({target_audience: audience_rules[target_audience]}, indent=2)}\n</audience_rules>")

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
    try:
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=8192,
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
