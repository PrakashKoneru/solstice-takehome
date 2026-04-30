import copy
import os
import re
import json
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable

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

DOCUMENT NAVIGATION — strict sourcing rule:
When <document_outline> is provided, it is the ONLY source of truth for what content the document contains.
- When describing available content, list the EXACT heading titles from the outline. Do NOT rename, regroup, paraphrase, or summarize headings into your own categories.
- When the user asks "what can I build" or "what content is available", respond with the actual section headings organized by their hierarchy in the outline — not by your own interpretation of the document.
- Do NOT invent section names like "Clinical Efficacy" or "Safety Profile" unless those exact words appear as headings in the outline.
- When suggesting slides, reference the exact heading the slide would draw from.
- If <document_outline> is not provided, say "No document structure is available — please re-upload the document."

ASSET AWARENESS:
When <brand_assets> is provided, reference available logos, icons, and graphics by name when discussing layouts or design options.

DECK AWARENESS:
When <current_deck> is provided, you know what slides exist. Reference them by title and layout type. Suggest improvements to specific slides.

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

COMPONENT_PATTERNS_SYSTEM_PROMPT = """You are a design system analyst. You will receive rendered pages from a design system / style guide document as images.

Your job: identify every distinct visual pattern, component, rule, and styling specification this document defines. Extract each one into a structured JSON description that another AI can consume to produce pixel-accurate HTML/CSS output matching this brand.

APPROACH:
1. Look at every page. Determine what the document is trying to teach you — what visual rules is it establishing?
2. For each distinct pattern you identify, give it a descriptive name and extract every visual property you can see.
3. Describe visual properties in whatever terms are most precise for faithful reproduction. Use CSS-compatible syntax where applicable (hex colors, px/rem values, font-family names, border shorthand, linear-gradient() syntax, box-shadow syntax, border-radius values — including but not limited to these) but use plain geometric or spatial descriptions when CSS cannot capture the property (e.g. arc sweep angles, shape relationships, layering order, proportional sizing, animation behavior).
4. Be precise: "2px solid #8C4799" not "thin purple border". "#002855" not "dark blue". "arc sweeping 180deg from top-left, stroke 2px #8C4799, no fill" not "purple curved line". NEVER use color names like "light blue", "dark blue", "purple" — ALWAYS resolve to the exact hex value from the document's color palette. If the document defines light blue as #59CBE8, every reference to that color must use #59CBE8.
5. When a page shows annotated examples (arrows or lines pointing to elements with descriptions), extract both the visual property AND the rule being taught.
6. When a page shows multiple variants of the same element (e.g. logo on white vs dark background, hover states, responsive versions), capture all variants.
7. When a page shows a complete layout example (a full slide or page mockup), decompose it into its constituent patterns — header, body regions, footer — and describe how they're assembled.
8. Extract what you SEE. Do not invent, assume, or generalize beyond what the document shows.

OUTPUT FORMAT:
Return ONLY a valid JSON object with this structure:

{
  "patterns": {
    "<descriptive_name>": {
      "description": "What this pattern is and when to use it",
      "properties": {
        // Visual properties that define this pattern
        // Nest as deeply as needed to capture the full specification
        // Use CSS values where possible, plain descriptions otherwise
      },
      "variants": [],
      "rules": []
    }
  },
  "slideLayouts": [
    {
      "name": "",
      "description": "What this layout looks like and what content it's designed for",
      "structure": "Describe the spatial arrangement: regions, columns, proportions, spacing",
      "components": ["which patterns from above are used in this layout"]
    }
  ],
  "colorSystem": {
    "colors": [
      { "hex": "", "name": "", "role": "", "usage": "" }
    ],
    "hierarchy": "",
    "gradients": [],
    "tintShadeRules": ""
  },
  "typographySystem": {
    "fonts": [
      { "family": "", "role": "", "weights": [], "usage": "" }
    ],
    "contextualRules": [
      { "context": "", "fontFamily": "", "weight": "", "color": "", "case": "", "size": "" }
    ]
  }
}

The "patterns" object should contain AS MANY entries as the document defines. Do NOT force categories — only extract what the document actually defines. If the document defines 20 distinct patterns, return 20. If it defines 5, return 5.

For "slideLayouts": identify every DISTINCT page/slide layout shown in the document. Two pages with different spatial arrangements are different layouts even if they share some components. A data table page, a chart page, a three-column card page, and a hero stat page are all separate layouts. Extract at minimum every layout the document explicitly demonstrates.

For all gradient and color properties: express gradients as CSS linear-gradient() or radial-gradient() syntax using exact hex values. For example: "linear-gradient(to bottom, #59CBE8, #FFFFFF)" not "light blue to white".

"colorSystem" and "typographySystem" are separated because they are cross-cutting — they apply across all patterns. Extract the FULL color palette with roles and hierarchy, and the FULL typography system with contextual rules that specify how styling varies by content role."""


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

5. LAYOUT: Apply `layoutPrinciples` literally — generous whitespace, structural elements (accent bars, gradient strokes, violators) placed correctly. Do not invent decorative patterns — colored card borders, side accents, divider lines, or any other visual element — that are not explicitly described in `brand_guidelines`, `<component_patterns>`, or `<design_tokens>`. If the brand does not specify card border colors, cards have no colored border. Every decoration must have a source in the guidelines.

VISUAL BALANCE & ALIGNMENT — non-negotiable:
- Every slide must read as visually balanced. No single region should carry significantly more visual weight than the others.

COLUMNS:
- All sibling columns in a row must have identical width — use `flex:1` or explicit equal percentages. Never give one column more width than another unless the layout explicitly calls for a sidebar ratio (e.g. 30/70).
- All sibling columns must be equal height — set the row container to `align-items:stretch` and each column to `display:flex; flex-direction:column`.
- When a column acts as a visual anchor (sidebar with an icon + label, or a support panel), center its content both horizontally and vertically within the full column height: `justify-content:center; align-items:center; text-align:center`.

ICON + LABEL PAIRS:
- An icon and its associated label text are always a single unit. Render them as `display:flex; flex-direction:column; align-items:center; text-align:center; gap:[consistent value]`. Never let the icon be left-aligned while the label is centered, or vice versa.
- When this unit sits inside a column or panel, center the entire unit within that container using `justify-content:center`.

CARDS:
- Cards in a row must have identical width, identical padding, and identical border styling. Use `flex:1` on each card. Never hardcode different pixel widths for sibling cards.
- Text inside cards must align consistently — all card titles share the same alignment, all card body text shares the same alignment.

SPACING:
- Use one gap value for all sibling spacing within a container. Never mix gap values (e.g. 12px between some items and 16px between others in the same row).

CENTERING:
- Never eyeball a center. Use `margin:0 auto`, `text-align:center`, `align-items:center`, or `justify-content:center` explicitly.

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

COMPONENT PATTERNS — visual source of truth (highest priority):
When <component_patterns> is present, it contains the brand's complete visual specification extracted from their style guide via vision analysis. It overrides <design_tokens> for all visual decisions.
- "patterns": every named visual component the brand defines. Before building any element (header, footer, chart, table, card, icon, callout), check if a matching pattern exists. If it does, apply its properties exactly.
- "colorSystem": the full palette with roles and hierarchy. Use the right color for the right context — drug data in the drug color, placebo in the placebo color, headlines in the headline color. Use gradients exactly as specified in CSS syntax.
- "typographySystem.contextualRules": font styling varies by content role, not just heading level. Apply the exact font, weight, color, and case for each context (headlines, chart heads, body copy, drug data, placebo data, bullet points, etc).
- "slideLayouts": available layout patterns with their spatial structure and component references. Use the closest matching layout for the content type.
- If a pattern has "rules", those are hard constraints from the brand — follow them literally.
- If a pattern has "variants", select the appropriate variant for the context.

BRAND ASSETS:
- <brand_assets> lists available brand icons and logos with their Cloudinary URLs.
- Logos: scan <brand_assets> for an asset with type "logo" whose name most closely matches the product wordmark. Place it as a standalone <img style="object-fit:contain;" alt="logo"> in the header. Do not substitute any other asset — a product box, page screenshot, or approval image is not the logo. If no logo asset exists, you MUST still satisfy the required element by rendering the `hallmark` value as a text lockup in the header: product name in primaryFont, bold, brand primary color, with the generic name in secondaryFont below it at a smaller size. Omitting the logo entirely is not an option.
- Icons: use in content areas only when the icon type semantically matches the content being illustrated.
- Never invent, guess, or hotlink image URLs not explicitly listed in <brand_assets>.

CTAs — strict rule:
Never generate a call-to-action, button, or link of any kind unless the user has explicitly provided a destination URL in their request. Slides are static presentation assets — a CTA with no real destination is a design error. If no URL is provided, omit the CTA entirely and use the space for content.

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
- <current_draft> contains the COMPLETE current state of the deck including all user edits. Treat it as the ground truth for what slides exist right now.
- When ADDING a slide (user says "add", "create another", "make a second slide", or any wording that implies a new slide alongside existing ones): copy every <div data-slide> from <current_draft> verbatim into your output, then append the new <div data-slide> at the end. The output MUST contain N+1 slides where N is the number of slides in <current_draft>. Outputting only the new slide is WRONG.
- When REORDERING: output all slides in the new order, content unchanged.
- When EDITING one slide: output every slide from <current_draft>, replacing only the one being edited.
- NEVER drop or omit an existing slide unless the user explicitly says "remove slide X" or "delete slide X".
- If <current_draft> is empty or absent, generate only what was asked.

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


ORCHESTRATOR_SYSTEM_PROMPT = """You are the orchestrator for a pharma content studio. Your job is to read the user's message and conversation history, then decide which operation to run for this turn.

Available operations:
- "edit"      — modify specific aspects of an existing deck (change headlines, swap claims, add/remove slides, change layouts)
- "generate"  — create a brand-new deck from scratch
- "chat"      — answer questions, guide the user, explain what was done

Classification rules (apply in order):
1. If has_kb is false → return ["chat"] regardless of intent.
2. If the user explicitly wants a fresh start ("build me a deck", "start over", "rebuild from scratch", "create new slides", "new deck", "generate a deck") → return ["generate"].
3. If has_deck is true AND the user references modifying specific aspects of existing slides ("change slide 3 headline", "swap the claim", "add a slide about dosing", "remove slide 2", "update the title", "move slide 4", "edit the layout") → return ["edit"].
4. If the user wants slides but has_deck is false → return ["generate"].
5. Questions, exploration, or ambiguous requests → return ["chat"].
6. When unsure → return ["chat"].

Never return more than one operation.

Respond with ONLY valid JSON — no explanation:
{"ops": ["chat"]} or {"ops": ["generate"]} or {"ops": ["edit"]}"""


_RESET_PHRASES = (
    'start over', 'from scratch', 'throw this out', 'scrap this',
    'rebuild', 'new deck', 'redo the deck', 'redo the whole deck',
    'discard', 'wipe', 'clear the deck',
)


def orchestrate(prompt: str, history: list, has_kb: bool, has_deck: bool = False) -> list:
    """Returns list of operations to run: one of ['generate'], ['edit'], or ['chat']"""
    client = _get_client()
    try:
        context = f"has_kb: {str(has_kb).lower()}\nhas_deck: {str(has_deck).lower()}\n\nUser message: {prompt}"
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=256,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            messages=history + [{'role': 'user', 'content': context}],
        )
        raw = _parse_json_response(msg.content[0].text)
        result = json.loads(raw)
        ops = result.get('ops', ['chat'])
    except Exception:
        ops = ['chat']

    # Deterministic guard: when a deck already exists, only explicit reset
    # phrases should route to generate. Otherwise, a generate verdict from
    # the LLM (e.g. triggered by "create slide 3") is forcibly converted to
    # edit so the existing deck is never silently wiped.
    if has_deck and 'generate' in ops:
        p = (prompt or '').lower()
        if not any(phrase in p for phrase in _RESET_PHRASES):
            print(f"[ORCHESTRATE] overriding generate → edit (has_deck=true, no reset phrase)")
            ops = ['edit']

    return ops


def chat_response(
    prompt: str,
    kb_texts: Optional[list] = None,
    history: Optional[list] = None,
    brand_guidelines: Optional[dict] = None,
    ds_assets: Optional[list] = None,
    target_audience: Optional[str] = None,
    audience_rules: Optional[dict] = None,
    component_patterns: Optional[dict] = None,
    doc_outline: Optional[list] = None,
    current_spec: Optional[dict] = None,
) -> str:
    client = _get_client()
    context_parts = []
    if doc_outline:
        context_parts.append(f"<document_outline>\n{json.dumps(doc_outline, indent=2)}\n</document_outline>")
    if current_spec:
        deck_summary = [{"title": s.get("slide_title", ""), "layout": s.get("layout", "")}
                        for s in current_spec.get("slides", [])]
        context_parts.append(f"<current_deck>\n{json.dumps(deck_summary, indent=2)}\n</current_deck>")
    if brand_guidelines:
        context_parts.append(f"<brand_guidelines>\n{json.dumps(brand_guidelines, indent=2)}\n</brand_guidelines>")
    if component_patterns:
        context_parts.append(f"<component_patterns>\n{json.dumps(component_patterns, indent=2)}\n</component_patterns>")
    if ds_assets:
        asset_list = [{'name': a['name'], 'type': a['asset_type'], 'url': a['file_url']} for a in ds_assets]
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
        model='claude-opus-4-6',
        max_tokens=8192,
        system=CHAT_SYSTEM_PROMPT,
        messages=messages,
    )
    return message.content[0].text.strip()


def generate_content(
    prompt: str,
    design_tokens: Optional[dict] = None,
    brand_guidelines: Optional[dict] = None,
    ds_assets: Optional[list] = None,
    kb_texts: Optional[list] = None,
    current_draft: Optional[str] = None,
    history: Optional[list] = None,
    target_audience: Optional[str] = None,
    audience_rules: Optional[dict] = None,
    component_patterns: Optional[dict] = None,
) -> str:
    client = _get_client()

    context_parts = []
    if design_tokens:
        context_parts.append(f"<design_tokens>\n{json.dumps(design_tokens, indent=2)}\n</design_tokens>")
    if brand_guidelines:
        context_parts.append(f"<brand_guidelines>\n{json.dumps(brand_guidelines, indent=2)}\n</brand_guidelines>")
    if component_patterns:
        context_parts.append(f"<component_patterns>\n{json.dumps(component_patterns, indent=2)}\n</component_patterns>")
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

    message = client.beta.messages.create(
        model='claude-opus-4-6',
        max_tokens=64000,
        betas=['output-128k-2025-02-19'],
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
            model='claude-opus-4-6',
            max_tokens=8192,
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



def extract_brand_guidelines(pdf_text: str, pdf_filepath: Optional[str] = None, tables: list = None) -> dict:
    client = _get_client()
    try:
        prompt = f'Extract brand guidelines from this style guide:\n---\n{pdf_text}\n---\n'
        if tables:
            table_text = '\n\n'.join(
                f'Table {t["index"]} (page {t["page_no"]}):\n{t["markdown"]}' for t in tables
            )
            prompt += f'\nStructured tables extracted from the PDF:\n---\n{table_text}\n---\n'
        prompt += 'Return only the JSON object.'
        message = client.messages.create(
            model='claude-opus-4-6',
            max_tokens=8192,
            system=BRAND_GUIDELINES_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = _parse_json_response(message.content[0].text)
        return json.loads(raw)
    except Exception:
        return {}


def extract_component_patterns(pdf_filepath: str, pdf_text: str = "") -> dict:
    """
    Vision-based extraction of component patterns from a style guide PDF.
    Sends rendered pages as images to Claude Vision for structural analysis.
    Falls back to text-based extraction if vision fails.
    """
    client = _get_client()

    from services.pdf_service import render_pdf_pages_as_images
    pages = render_pdf_pages_as_images(pdf_filepath, max_pages=25)

    if not pages:
        return _extract_component_patterns_fallback(client, pdf_text)

    content = []
    for i, (b64, mime) in enumerate(pages):
        content.append({'type': 'text', 'text': f'Page {i + 1}:'})
        content.append({
            'type': 'image',
            'source': {'type': 'base64', 'media_type': mime, 'data': b64},
        })

    content.append({
        'type': 'text',
        'text': (
            'These are all pages from a design system / style guide document. '
            'Extract every reusable visual component pattern you can identify. '
            'Pay special attention to annotated examples where the document is teaching specific visual rules. '
            'Use exact CSS-compatible values for every property you can identify. '
            'For properties that CSS cannot express, use precise geometric or spatial descriptions.'
        ),
    })

    # Also send text for context (annotations reference visual elements)
    if pdf_text:
        content.append({
            'type': 'text',
            'text': f'\n\nFor reference, here is the extracted text from the same PDF:\n\n{pdf_text[:6000]}',
        })

    try:
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=16384,
            system=COMPONENT_PATTERNS_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': content}],
        )
        raw = _parse_json_response(message.content[0].text)
        return json.loads(raw)
    except Exception as e:
        print(f"[WARN] Vision-based component extraction failed: {e}")
        return _extract_component_patterns_fallback(client, pdf_text)


def _extract_component_patterns_fallback(client, pdf_text: str) -> dict:
    """Text-only fallback when vision extraction fails."""
    try:
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=16384,
            system=COMPONENT_PATTERNS_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': f'Extract component patterns from this style guide text:\n---\n{pdf_text}\n---'}],
        )
        raw = _parse_json_response(message.content[0].text)
        return json.loads(raw)
    except Exception:
        return {"patterns": {}, "slideLayouts": [], "colorSystem": {}, "typographySystem": {}}


# ── Structured generation (claims-constrained) ────────────────────────────────

SLIDE_SPEC_TOOL = {
    "name": "generate_slide_deck",
    "description": "Generate a slide deck as a structured spec. Every factual text element must reference an approved claim ID. Only slide_title and cta_text may be written freely.",
    "input_schema": {
        "type": "object",
        "properties": {
            "slides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "layout": {
                            "type": "string",
                            "enum": [
                                "hero", "big_stat", "stat_row", "two_column",
                                "three_column_cards", "comparison_table",
                                "data_table", "subgroup_forest", "title_only"
                            ]
                        },
                        "slide_title": {
                            "type": "string",
                            "description": (
                                "Creative framing headline with NO numbers, NO percentages, "
                                "NO comparative outcomes. Pure brand/context copy only. "
                                "Examples: 'Reimagine Survival', 'Proven in a Phase 3 Trial'."
                            )
                        },
                        "headline": {
                            "type": "object",
                            "properties": {
                                "claim_id": {"type": "string", "enum": []},
                                "emphasis": {
                                    "type": "object",
                                    "properties": {
                                        "numeric_value_index": {"type": "integer"},
                                        "style": {
                                            "type": "string",
                                            "enum": ["hero_number", "bold", "color_accent"]
                                        }
                                    }
                                }
                            },
                            "required": ["claim_id"]
                        },
                        "body_claims": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "claim_id": {"type": "string", "enum": []},
                                    "role": {
                                        "type": "string",
                                        "enum": ["supporting", "comparison", "context", "subgroup"]
                                    }
                                },
                                "required": ["claim_id", "role"]
                            }
                        },
                        "footer_claims": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "claim_id": {"type": "string", "enum": []}
                                },
                                "required": ["claim_id"]
                            }
                        },
                        "cta_text": {
                            "type": "string",
                            "description": "Optional CTA button label. Short, no clinical data."
                        }
                    },
                    "required": ["layout", "headline"]
                }
            }
        },
        "required": ["slides"]
    }
}

SPEC_SYSTEM_PROMPT = """You are a pharma slide deck architect. Your job is to select the right claims and layouts — not to write clinical copy.

You receive a <claim_catalog> listing approved claims by ID, type, and tags. You must build a deck by selecting claim IDs from that catalog. You never write factual text — you only reference claim IDs.

LAYOUT SELECTION:
- big_stat: one dominant KPI stat (e.g. median OS number)
- stat_row: 2–4 stats side by side (e.g. OS + PFS + HR together)
- two_column: primary claim left, supporting claims right
- three_column_cards: 3 parallel facts (e.g. 3 safety stats)
- comparison_table: head-to-head data (e.g. FRUZAQLA vs placebo)
- data_table: multi-row clinical data
- subgroup_forest: subgroup consistency data
- hero: cover/title slide
- title_only: section divider

SLIDE TITLE (the only text you write):
- Must be a framing headline with ZERO numbers, ZERO percentages, ZERO comparative language
- Good: "Proven Survival Benefit", "Manageable Safety Profile", "Study Design"
- Bad: "34% reduction in OS risk" (contains a number — use a claim_id instead)

REQUIRED ELEMENTS:
- Every slide MUST include at least one ISI or boilerplate claim in footer_claims when available in the catalog.
- Choose ISI claims (type "isi") for the footer on every clinical data slide.

EMPHASIS:
- Use emphasis.numeric_value_index to visually highlight a specific number from the claim's numeric_values array.
- Use hero_number style for the primary KPI on big_stat slides.

EDITING AN EXISTING SPEC:
When <current_spec> is provided, it is the current slide deck. The user's message describes a targeted change (swap a claim, change layout, add/remove a slide). Apply ONLY the requested change:
- Keep every slide, claim reference, layout, and ordering that the user did NOT ask to change.
- Only modify the specific element(s) the user mentioned.
- Output the full deck spec with the minimal diff applied.
- If <current_spec> is absent, generate from scratch as usual."""


def _inject_enum(tool: dict, enum_values: list) -> dict:
    """Walk the tool schema and set every claim_id enum to the provided list."""
    def _walk(obj):
        if isinstance(obj, dict):
            if obj.get('type') == 'string' and 'enum' in obj and obj['enum'] == []:
                obj['enum'] = enum_values
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
    _walk(tool)
    return tool


def _tag_filter(catalog: list, prompt: str, max_claims: int = 60) -> list:
    """Return up to max_claims claims most relevant to the prompt based on tag overlap."""
    if len(catalog) <= max_claims:
        return catalog

    prompt_tokens = set(re.sub(r'[^a-z0-9\s]', '', prompt.lower()).split())

    def score(claim):
        tags = set(t.lower().replace('-', '_') for t in (claim.get('tags') or []))
        return len(tags & prompt_tokens)

    ranked = sorted(catalog, key=score, reverse=True)
    # Always include ISI/boilerplate claims
    priority = [c for c in catalog if c.get('type') in ('isi', 'boilerplate')]
    rest = [c for c in ranked if c.get('type') not in ('isi', 'boilerplate')]
    merged = priority + rest
    # Deduplicate preserving order
    seen = set()
    result = []
    for c in merged:
        if c['id'] not in seen:
            seen.add(c['id'])
            result.append(c)
    return result[:max_claims]


# Match standalone numbers (e.g. "34%", "7.4 months") but NOT digits embedded in
# study names like "FRESCO-2", "NCT04322539", or "Phase 3".
_FREE_TEXT_RE = re.compile(
    r'(?<![A-Za-z-])\d+\.?\d*\s*%'           # percentages: "34%", "7.4%"
    r'|(?<![A-Za-z-])\d+\.?\d*\s+(?:months|years|days|mg|patients)'  # numbers with units
    r'|(\bvs\b|\bcompared\b|\bhigher\b|\blower\b|\bgreater\b|\breduction\b|\bincrease\b)',
    re.IGNORECASE,
)


def validate_slide_spec(spec: dict, available_ids: list, brand_guidelines: Optional[dict] = None) -> list:
    """
    Validate the structured slide spec.
    Returns list of error strings (empty = valid).
    """
    errors = []
    available = set(available_ids)

    for i, slide in enumerate(spec.get('slides', [])):
        slide_num = i + 1

        # Collect all claim_id references on this slide
        refs = []
        if slide.get('headline', {}).get('claim_id'):
            refs.append(slide['headline']['claim_id'])
        refs += [c['claim_id'] for c in slide.get('body_claims', []) if c.get('claim_id')]
        refs += [c['claim_id'] for c in slide.get('footer_claims', []) if c.get('claim_id')]

        for ref in refs:
            if ref not in available:
                errors.append(f"Slide {slide_num}: claim_id '{ref}' not in approved claims")

        # Free-text constraint: slide_title and cta_text must not contain numbers/comparative words
        for field in ('slide_title', 'cta_text'):
            value = slide.get(field, '') or ''
            if value and _FREE_TEXT_RE.search(value):
                errors.append(
                    f"Slide {slide_num}: '{field}' contains numbers or comparative language: \"{value}\""
                )

    return errors


def build_compliance_trace(spec: dict, claims_by_id: dict) -> dict:
    """
    Build a deterministic compliance trace from the slide spec.
    Every factual element traces back to an approved claim.
    """
    trace = []
    for i, slide in enumerate(spec.get('slides', [])):
        slide_num = i + 1
        headline_id = slide.get('headline', {}).get('claim_id')
        if headline_id and headline_id in claims_by_id:
            c = claims_by_id[headline_id]
            trace.append({
                'slide': slide_num,
                'element': 'headline',
                'claim_id': headline_id,
                'claim_text': c['text'],
                'source': c.get('source_citation', ''),
            })
        for body in slide.get('body_claims', []):
            cid = body.get('claim_id')
            if cid and cid in claims_by_id:
                c = claims_by_id[cid]
                trace.append({
                    'slide': slide_num,
                    'element': f"body ({body.get('role', '')})",
                    'claim_id': cid,
                    'claim_text': c['text'],
                    'source': c.get('source_citation', ''),
                })
        for footer in slide.get('footer_claims', []):
            cid = footer.get('claim_id')
            if cid and cid in claims_by_id:
                c = claims_by_id[cid]
                trace.append({
                    'slide': slide_num,
                    'element': 'footer',
                    'claim_id': cid,
                    'claim_text': c['text'],
                    'source': c.get('source_citation', ''),
                })

    total = len(spec.get('slides', []))
    return {
        'verdict': 'approved',
        'guarantee': 'structural',
        'confidence': 1.0,
        'summary': (
            f"All {len(trace)} factual text elements traced to approved claims "
            f"across {total} slide(s). Exact text match guaranteed."
        ),
        'flags': [],
        'trace': trace,
    }


RENDER_SPEC_SYSTEM_PROMPT = (
    CONTENT_SYSTEM_PROMPT
    + "\n\n"
    + """RENDERING MODE — you are rendering a pre-approved slide spec:
You receive a <slide_spec> containing the exact slide structure and resolved claim text. Your job is to render it as production-quality HTML using the full brand visual language.

HARD RULES:
- Do NOT change, rephrase, add to, or remove ANY factual text in the spec. Render every claim's text VERBATIM.
- slide_title and cta_text may be rendered with creative typography but their wording is also fixed.
- You MUST apply the brand's full visual language: gradients, decorative elements, icons, typography hierarchy, color treatments — everything that makes the brand come alive.
- Follow the layout type specified for each slide but express it through the brand's design language, not a generic template.
- IMPORTANT: Every claim text element MUST be wrapped in a span with data-claim-id and contenteditable="false": <span data-claim-id="CLAIM_ID" contenteditable="false" class="claim-locked">CLAIM TEXT</span>. This applies to headline text, body claim text, and footer claim text. The claim_id is provided alongside each text field in the spec.

VISUAL CONTENT:
Tables and figures are injected automatically AFTER you return your HTML. You will NOT see them in the spec.
- If a body_claim says "(visual content will be placed here automatically)", render an empty div with class="visual-inject-target" and style="width:100%;" at that position. Do NOT add min-height, padding, or any other sizing — the visual will fill it.
- Do NOT create placeholder text, fake tables, or dummy images. Just place the empty target div.
- IMPORTANT: slide content areas MUST NOT have overflow:hidden or fixed heights that would clip injected content. Let content expand naturally.

TEXT CLAIMS:
Body claims with content_format "text" are rendered normally:
- Wrap in <span data-claim-id="CLAIM_ID" contenteditable="false" class="claim-locked">CLAIM TEXT</span>
- Render the text VERBATIM — do not alter, rephrase, or summarize.

BRAND ASSET USAGE:
- If a slide has logo_url, place it per brand guidelines positioning rules (typically top-right or top-left of the header area).
- Use exact asset URLs from the spec — never construct or guess URLs.

DESIGN TOKEN APPLICATION:
- Use <design_tokens> colors for ALL color values — never hardcode hex values that aren't from the token palette.
- Use <design_tokens> fonts for ALL font-family values.
- Apply typography contextual rules from <component_patterns> when available.

LAYOUT FIDELITY:
- If matched_pattern is provided on a slide, follow its spatial structure exactly — regions, columns, proportions, spacing.
- Cross-reference component_patterns.patterns for exact CSS properties when rendering individual elements."""
)


def _table_json_to_html(table_json: dict, claim_id: str) -> str:
    """Render table_json ({"headers": [...], "rows": [...]}) as a deterministic HTML table."""
    headers = table_json.get('headers', [])
    rows = table_json.get('rows', [])

    # Scale font and padding for large tables
    row_count = len(rows)
    if row_count > 12:
        font_size = '0.65em'
        cell_pad = '3px 6px'
    elif row_count > 6:
        font_size = '0.75em'
        cell_pad = '4px 8px'
    else:
        font_size = '0.9em'
        cell_pad = '8px 12px'

    html_parts = [
        f'<div data-claim-id="{claim_id}" contenteditable="false" class="claim-locked" '
        f'style="overflow-x:auto;overflow-y:auto;margin:8px 0;max-height:70vh;">',
        f'<table style="width:100%;border-collapse:collapse;font-size:{font_size};">',
        '  <thead>',
        '    <tr style="background:#f0f4f8;">',
    ]
    th_style = f'padding:{cell_pad};border-bottom:2px solid #cbd5e0;text-align:left;font-weight:600;'
    for h in headers:
        html_parts.append(f'      <th style="{th_style}">{h}</th>')
    html_parts.append('    </tr>')
    html_parts.append('  </thead>')
    html_parts.append('  <tbody>')
    td_style = f'padding:{cell_pad};border-bottom:1px solid #e2e8f0;text-align:left;'
    for row in rows:
        html_parts.append('    <tr>')
        for cell in row:
            html_parts.append(f'      <td style="{td_style}">{cell}</td>')
        html_parts.append('    </tr>')
    html_parts.append('  </tbody>')
    html_parts.append('</table>')
    html_parts.append('</div>')
    return '\n'.join(html_parts)


def _markdown_table_to_html(md: str, claim_id: str) -> str:
    """Fallback: convert a markdown table to branded HTML when table_json is unavailable."""
    lines = [l.strip() for l in md.strip().split('\n') if l.strip()]
    if not lines:
        return f'<div data-claim-id="{claim_id}" contenteditable="false" class="claim-locked">{md}</div>'

    html_parts = [
        f'<div data-claim-id="{claim_id}" contenteditable="false" class="claim-locked" style="overflow-x:auto;margin:16px 0;">',
        '<table style="width:100%;border-collapse:collapse;font-size:0.9em;">',
    ]

    for i, line in enumerate(lines):
        # Skip separator rows (e.g. |---|---|)
        stripped = line.strip('|').strip()
        if stripped and all(c in '-|: ' for c in stripped):
            continue

        cells = [c.strip() for c in line.strip('|').split('|')]
        tag = 'th' if i == 0 else 'td'
        style_row = ' style="background:#f0f4f8;font-weight:600;"' if i == 0 else ''
        style_cell = 'padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:left;'
        if i == 0:
            style_cell += 'font-weight:600;'

        html_parts.append(f'  <tr{style_row}>')
        for cell in cells:
            html_parts.append(f'    <{tag} style="{style_cell}">{cell}</{tag}>')
        html_parts.append('  </tr>')

    html_parts.append('</table>')
    html_parts.append('</div>')
    return '\n'.join(html_parts)


def render_spec_to_html(
    spec: dict,
    claims_by_id: dict,
    design_tokens: Optional[dict] = None,
    brand_guidelines: Optional[dict] = None,
    ds_assets: Optional[list] = None,
    current_html: Optional[str] = None,
    component_patterns: Optional[dict] = None,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Send validated slide spec to Claude for rich HTML rendering.
    Claims are resolved to verbatim text so Claude styles but cannot alter content.
    """
    client = _get_client()

    # Pre-resolve logo URL from brand assets
    logo_url = None
    if ds_assets:
        for a in ds_assets:
            if a.get('asset_type') == 'logo':
                logo_url = a.get('file_url')
                break

    # Match slide layouts to component_patterns slideLayouts
    layout_patterns = {}
    if component_patterns and component_patterns.get('slideLayouts'):
        for sl in component_patterns['slideLayouts']:
            layout_patterns[sl.get('name', '').lower()] = sl

    # Resolve claim IDs to verbatim text inline
    # Per-slide visual injection list: [(slide_index, html_str), ...]
    # These are injected AFTER Claude returns — Claude never sees them.
    _slide_visual_injections = []  # list of (slide_idx, inject_html)
    resolved = {"slides": []}
    for slide in spec.get("slides", []):
        s = {
            "layout": slide.get("layout"),
            "slide_title": slide.get("slide_title", ""),
            "cta_text": slide.get("cta_text", ""),
        }
        if logo_url:
            s["logo_url"] = logo_url
        # Match layout to component pattern
        layout_name = (slide.get("layout") or "").lower().replace("_", " ")
        for pattern_name, pattern_data in layout_patterns.items():
            if layout_name in pattern_name.lower() or pattern_name.lower() in layout_name:
                s["matched_pattern"] = pattern_data
                break
        h = slide.get("headline", {})
        hid = h.get("claim_id")
        s["headline"] = {
            "claim_id": hid or "",
            "text": claims_by_id[hid]["text"] if hid and hid in claims_by_id else "",
            "emphasis": h.get("emphasis"),
        }
        # Resolve body claims: visual claims (tables/figures) are NOT sent to Claude.
        # They are pre-rendered as HTML and injected after Claude returns.
        slide_idx = len(resolved["slides"])  # current slide index
        resolved_body = []
        has_visuals = False
        for b in slide.get("body_claims", []):
            cid = b.get("claim_id", "")
            claim_data = claims_by_id.get(cid, {}) if cid else {}
            fmt = claim_data.get("content_format", "text")
            role = b.get("role", "supporting")

            if fmt == "table" and claim_data.get("table_json"):
                inject_html = _table_json_to_html(claim_data["table_json"], cid)
                _slide_visual_injections.append((slide_idx, inject_html))
                has_visuals = True
                print(f"[DEBUG] Table (JSON) queued for slide {slide_idx}: {cid}")
            elif fmt == "table" and claim_data.get("table_markdown"):
                from services.pdf_service import _parse_markdown_table
                parsed = _parse_markdown_table(claim_data["table_markdown"])
                if parsed:
                    inject_html = _table_json_to_html(parsed, cid)
                else:
                    inject_html = _markdown_table_to_html(claim_data["table_markdown"], cid)
                _slide_visual_injections.append((slide_idx, inject_html))
                has_visuals = True
                print(f"[DEBUG] Table (markdown) queued for slide {slide_idx}: {cid}")
            elif fmt == "figure" and claim_data.get("figure_url"):
                fig_url = claim_data["figure_url"]
                fig_alt = claim_data.get("text", "")
                inject_html = (
                    f'<div data-claim-id="{cid}" contenteditable="false" class="claim-locked" '
                    f'style="text-align:center;margin:16px 0;">'
                    f'<img src="{fig_url}" alt="{fig_alt}" '
                    f'style="max-width:100%;height:auto;border-radius:4px;" />'
                    f'<p style="font-size:0.85em;color:#666;margin-top:8px;">{fig_alt}</p>'
                    f'</div>'
                )
                _slide_visual_injections.append((slide_idx, inject_html))
                has_visuals = True
                print(f"[DEBUG] Figure queued for slide {slide_idx}: {cid}")
            else:
                resolved_body.append({
                    "claim_id": cid,
                    "text": claim_data.get("text", ""),
                    "content_format": "text",
                    "role": role,
                })

        # If this slide has visuals, tell Claude to leave space but send no data
        if has_visuals and not resolved_body:
            # Visual-only slide — give Claude a hint about the layout
            resolved_body.append({
                "content_format": "text",
                "text": "(visual content will be placed here automatically)",
                "role": "supporting",
            })

        s["body_claims"] = resolved_body
        s["footer_claims"] = [
            {
                "claim_id": f.get("claim_id", ""),
                "text": claims_by_id[f["claim_id"]]["text"] if f.get("claim_id") and f["claim_id"] in claims_by_id else "",
            }
            for f in slide.get("footer_claims", [])
        ]
        resolved["slides"].append(s)

    # Build context (same pattern as generate_content)
    context_parts = []
    if design_tokens:
        context_parts.append(f"<design_tokens>\n{json.dumps(design_tokens, indent=2)}\n</design_tokens>")
    if brand_guidelines:
        context_parts.append(f"<brand_guidelines>\n{json.dumps(brand_guidelines, indent=2)}\n</brand_guidelines>")
    if component_patterns:
        context_parts.append(f"<component_patterns>\n{json.dumps(component_patterns, indent=2)}\n</component_patterns>")
    if ds_assets:
        embeddable = [a for a in ds_assets if a.get('source') != 'page_render']
        if embeddable:
            asset_list = [{'name': a['name'], 'type': a['asset_type'], 'url': a['file_url']} for a in embeddable]
            context_parts.append(f"<brand_assets>\n{json.dumps(asset_list, indent=2)}\n</brand_assets>")

    context_parts.append(f"<slide_spec>\n{json.dumps(resolved, indent=2)}\n</slide_spec>")

    if current_html:
        context_parts.append(f"<current_html>\n{current_html}\n</current_html>")
        user_content = (
            "\n\n".join(context_parts)
            + "\n\nThe <current_html> is the existing rendered slide deck. The <slide_spec> contains updated content. "
            "Find the text that changed between the current HTML and the new spec, and update ONLY that text in the HTML. "
            "Preserve the EXACT same layout, styling, CSS, structure, icons, gradients, and decorative elements. "
            "Output the complete HTML with only the changed text swapped in."
        )
    else:
        user_content = "\n\n".join(context_parts) + "\n\nRender this slide spec as production HTML. Apply the brand's full visual language."

    result_chunks = []
    with client.beta.messages.stream(
        model='claude-opus-4-6',
        max_tokens=64000,
        betas=['output-128k-2025-02-19'],
        system=RENDER_SPEC_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_content}],
    ) as stream:
        for text in stream.text_stream:
            result_chunks.append(text)
            if on_chunk:
                on_chunk(text)
    html_result = ''.join(result_chunks).strip()

    # Log slide structure for debugging injection
    section_count = len(re.findall(r'</section>', html_result, re.IGNORECASE))
    div_slide_count = len(re.findall(r'class="[^"]*slide[^"]*"', html_result, re.IGNORECASE))
    print(f"[DEBUG] Claude HTML: {len(html_result)} chars, {section_count} </section> tags, {div_slide_count} slide-class divs")

    # Inject pre-rendered visual content (tables/figures) into slides.
    # Claude never saw these — we inject by finding slide boundaries in the HTML.
    if _slide_visual_injections:
        # Group injections by slide index
        injections_by_slide = {}
        for slide_idx, inject_html in _slide_visual_injections:
            injections_by_slide.setdefault(slide_idx, []).append(inject_html)

        # Strategy 1: Replace visual-inject-target divs (preferred — precise placement)
        target_pattern = re.compile(r'<div[^>]*class="visual-inject-target"[^>]*>\s*</div>', re.IGNORECASE)
        targets = list(target_pattern.finditer(html_result))
        if targets:
            print(f"[DEBUG] Found {len(targets)} visual-inject-target divs")
            # Match targets to slide indices: nth target → nth slide with visuals
            visual_slide_indices = sorted(injections_by_slide.keys())
            for i in range(min(len(targets), len(visual_slide_indices)) - 1, -1, -1):
                slide_idx = visual_slide_indices[i]
                combined_html = '\n'.join(injections_by_slide[slide_idx])
                match = targets[i]
                html_result = html_result[:match.start()] + combined_html + html_result[match.end():]
                print(f"[DEBUG] Replaced visual-inject-target {i} with {len(injections_by_slide[slide_idx])} visual(s) for slide {slide_idx}")
                del injections_by_slide[slide_idx]

        # Strategy 2: Fall back to section boundaries for any remaining injections
        if injections_by_slide:
            section_ends = [m.start() for m in re.finditer(r'</section>', html_result, re.IGNORECASE)]
            if not section_ends:
                section_ends = [m.start() for m in re.finditer(r'</div>\s*(?=<div|$)', html_result)]
            print(f"[DEBUG] Found {len(section_ends)} slide boundaries for {len(injections_by_slide)} remaining slides with visuals")

            for slide_idx in sorted(injections_by_slide.keys(), reverse=True):
                combined_html = '\n'.join(injections_by_slide[slide_idx])
                if slide_idx < len(section_ends):
                    pos = section_ends[slide_idx]
                    html_result = html_result[:pos] + '\n' + combined_html + '\n' + html_result[pos:]
                    print(f"[DEBUG] Injected {len(injections_by_slide[slide_idx])} visual(s) into slide {slide_idx}")
                else:
                    insert_pos = None
                    for tag in ['</section>', '</main>', '</body>']:
                        p = html_result.rfind(tag)
                        if p > 0:
                            insert_pos = p
                            break
                    if insert_pos is None:
                        insert_pos = html_result.rfind('</div>')
                    if insert_pos and insert_pos > 0:
                        html_result = html_result[:insert_pos] + '\n' + combined_html + '\n' + html_result[insert_pos:]
                    print(f"[WARN] Slide {slide_idx} boundary not found (only {len(section_ends)} found), appended visuals at end")

    return html_result


EDIT_SPEC_TOOL = {
    "name": "edit_slide_spec",
    "description": "Apply targeted edits to an existing slide spec. Return only the changes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "slide_index": {
                            "type": "integer",
                            "description": "0-based index of the slide to edit"
                        },
                        "action": {
                            "type": "string",
                            "enum": ["replace_headline", "replace_body_claim", "add_body_claim",
                                     "remove_body_claim", "change_layout", "change_title",
                                     "add_slide", "remove_slide"]
                        },
                        "body_claim_index": {
                            "type": "integer",
                            "description": "0-based index within body_claims (for replace/remove_body_claim)"
                        },
                        "new_claim_id": {
                            "type": "string",
                            "enum": [],
                            "description": "The claim ID to use for replacement or addition"
                        },
                        "new_role": {
                            "type": "string",
                            "enum": ["supporting", "comparison", "context", "subgroup"]
                        },
                        "new_layout": {
                            "type": "string",
                            "enum": [
                                "hero", "big_stat", "stat_row", "two_column",
                                "three_column_cards", "comparison_table",
                                "data_table", "subgroup_forest", "title_only"
                            ]
                        },
                        "new_title": {
                            "type": "string",
                            "description": "New slide_title text (no numbers/percentages)"
                        },
                        "new_slide": {
                            "type": "object",
                            "description": "Full slide object for add_slide action",
                            "properties": {
                                "layout": {"type": "string"},
                                "slide_title": {"type": "string"},
                                "headline": {"type": "object", "properties": {"claim_id": {"type": "string"}}},
                                "body_claims": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "claim_id": {"type": "string"},
                                            "role": {"type": "string"}
                                        }
                                    }
                                },
                                "footer_claims": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"claim_id": {"type": "string"}}
                                    }
                                }
                            },
                            "required": ["layout", "slide_title", "headline", "body_claims"]
                        },
                        "insert_after": {
                            "type": "integer",
                            "description": "0-based index to insert after (-1 for beginning). Used with add_slide."
                        }
                    },
                    "required": ["slide_index", "action"]
                }
            }
        },
        "required": ["edits"]
    }
}

EDIT_SPEC_SYSTEM_PROMPT = """You are a slide spec editor. You receive a <current_spec> (the existing slide deck), a <claim_catalog> of available claims, and optionally <brand_guidelines> for layout/styling decisions. The user describes a targeted change. Return ONLY the minimal edits needed.

Actions:
- replace_headline: swap the headline claim_id on a slide
- replace_body_claim: swap a specific body_claim by index
- add_body_claim: add a new claim to body_claims
- remove_body_claim: remove a body_claim by index
- change_layout: change a slide's layout type
- change_title: change a slide's slide_title text
- add_slide: insert a new slide. Provide new_slide (full slide object with layout, slide_title, headline, body_claims, footer_claims) and insert_after (0-based index; -1 for beginning). Set slide_index to 0 (ignored for add_slide).
- remove_slide: delete a slide at slide_index

Rules:
- Only return edits for what the user asked to change. Do NOT re-specify unchanged slides.
- Match the user's intent to the closest available claim in the catalog.
- For replace actions, set new_claim_id to the best matching claim from the catalog.
- When adding slides, choose a layout that fits the claims and respects brand guidelines if provided.
- Claim IDs in new_slide must come from the claim catalog.

Table/Visual claim handling:
- Claims with content_format "table" or "figure" are visual assets extracted from the document. They render as rich tables or figures on the slide.
- When the user asks for a specific table (e.g. "Table 2", "the adverse reactions table"), find the claim with content_format "table" whose text/id matches. Use that claim's exact ID.
- When a slide features a table claim, use layout "data_table". The headline should be a TEXT claim that frames the table (e.g. a section header or context sentence). The table claim goes in body_claims with role "supporting".
- NEVER put a table/figure claim as the headline. Headlines must be text claims.
- Use section_hierarchy to disambiguate claims from different sections (e.g. "FRESCO-2 Study" under "6. ADVERSE REACTIONS" vs under "14. CLINICAL STUDIES")."""


def edit_slide_spec(
    prompt: str,
    current_spec: dict,
    claims: list,
    history: Optional[list] = None,
    brand_guidelines: Optional[dict] = None,
) -> dict:
    """
    Apply targeted edits to an existing spec. Returns the modified spec.
    Uses a lightweight tool call to determine edits, then applies them in Python.
    """
    print(f"[PIPELINE] edit_slide_spec: prompt=\"{prompt[:120]}\"")
    print(f"[PIPELINE] edit_slide_spec: {len(claims)} claims, {len(current_spec.get('slides', []))} existing slides")
    client = _get_client()

    claims_by_id = {c['id']: c for c in claims}
    catalog = []
    for c in claims:
        entry = {
            "id": c['id'],
            "text": c['text'],
            "type": c['claim_type'],
            "tags": c.get('tags') or [],
            "content_format": c.get('content_format', 'text'),
        }
        if c.get('section_hierarchy'):
            entry["section_hierarchy"] = c['section_hierarchy']
        catalog.append(entry)

    # Resolve current spec so the model sees actual text, not just IDs
    resolved_spec = copy.deepcopy(current_spec)
    for slide in resolved_spec.get('slides', []):
        h = slide.get('headline', {})
        hid = h.get('claim_id')
        if hid and hid in claims_by_id:
            h['text'] = claims_by_id[hid]['text']
        for bc in slide.get('body_claims', []):
            cid = bc.get('claim_id')
            if cid and cid in claims_by_id:
                bc['text'] = claims_by_id[cid]['text']
        for fc in slide.get('footer_claims', []):
            cid = fc.get('claim_id')
            if cid and cid in claims_by_id:
                fc['text'] = claims_by_id[cid]['text']

    # Prefilter catalog: use section_hierarchy to find claims from the right part of the document
    deck_claim_ids = set()
    for slide in current_spec.get('slides', []):
        h = slide.get('headline', {})
        if h.get('claim_id'):
            deck_claim_ids.add(h['claim_id'])
        for bc in slide.get('body_claims', []):
            if bc.get('claim_id'):
                deck_claim_ids.add(bc['claim_id'])
        for fc in slide.get('footer_claims', []):
            if fc.get('claim_id'):
                deck_claim_ids.add(fc['claim_id'])

    prompt_lower = prompt.lower()
    prompt_words = set(re.sub(r'[^a-z0-9\s]', '', prompt_lower).split())
    prompt_words -= {'the', 'a', 'an', 'and', 'or', 'for', 'to', 'on', 'in', 'of', 'can', 'you',
                     'create', 'make', 'add', 'show', 'display', 'slide', 'please', 'with'}

    filtered_catalog = []
    extra_scored = []
    for c in catalog:
        cid = c['id']
        # Always keep: claims already in the deck
        if cid in deck_claim_ids:
            filtered_catalog.append(c)
            continue

        score = 0

        # Section hierarchy matching: check if prompt phrases match any ancestor
        # e.g. prompt "dosage modifications" matches "2.2. Dosage Modifications for Adverse Reactions"
        for section_entry in (c.get('section_hierarchy') or []):
            section_lower = section_entry.lower()
            # Substring match: "dosage modifications" in "2.2. dosage modifications for adverse reactions"
            # Check 2+ word phrases from prompt against section titles
            if any(pw in section_lower for pw in prompt_words if len(pw) > 3):
                score += 5
            # Bonus: check multi-word phrase match (stronger signal)
            # Extract meaningful phrases from prompt (consecutive content words)
            section_words = set(re.sub(r'[^a-z0-9\s]', '', section_lower).split())
            section_overlap = len(prompt_words & section_words)
            if section_overlap >= 2:
                score += 10  # strong section match

        # Tag and text keyword matching
        claim_words = set(re.sub(r'[^a-z0-9\s]', '', (c.get('text') or '').lower()).split())
        tag_words = set(t.lower() for t in (c.get('tags') or []))
        score += len(prompt_words & tag_words) * 3
        score += len(prompt_words & claim_words)

        # Explicit table/figure number match: "table 2" in prompt vs claim text
        for ref in re.findall(r'(?:table|figure)\s*\d+', prompt_lower):
            if ref in (c.get('text') or '').lower():
                score += 20

        # Always keep visual claims with any relevance signal
        if c.get('content_format') in ('table', 'figure') and score > 0:
            score += 10  # boost relevant visuals

        if score > 0:
            extra_scored.append((c, score))

    # Take top 40 prompt-relevant claims, sorted by score
    extra_scored.sort(key=lambda x: x[1], reverse=True)
    for c, s in extra_scored[:40]:
        filtered_catalog.append(c)
        if s >= 10:
            fmt = c.get('content_format', 'text')
            label = f" [{fmt}]" if fmt != 'text' else ''
            print(f"[DEBUG] Edit prefilter (score={s}): {c['id']}{label} — {c.get('text', '')[:80]}")

    print(f"[DEBUG] Edit catalog: {len(filtered_catalog)}/{len(catalog)} claims (deck={len(deck_claim_ids)})")
    catalog = filtered_catalog

    # Detect explicit visual references (e.g. "Table 2", "Figure 3") and pin them
    pinned_visuals = _match_explicit_visuals(prompt, claims)
    pinned_directive = ""
    if pinned_visuals:
        # Ensure pinned claims are in the catalog
        catalog_ids = {c['id'] for c in catalog}
        for pv in pinned_visuals:
            if pv['id'] not in catalog_ids:
                catalog.append({
                    "id": pv['id'], "text": pv['text'],
                    "type": pv.get('claim_type', ''), "tags": pv.get('tags') or [],
                    "content_format": pv.get('content_format', 'text'),
                    "section_hierarchy": pv.get('section_hierarchy') or [],
                })
        pinned_ids = [pv['id'] for pv in pinned_visuals]
        pinned_directive = (
            f"\n\n<pinned_claims>\n"
            f"The user is specifically requesting these visual assets. You MUST use them:\n"
            + "\n".join(f"- {pv['id']} ({pv.get('content_format','text')}): {pv['text'][:120]}" for pv in pinned_visuals)
            + f"\nUse layout \"data_table\" for table claims. Put the table claim in body_claims as \"supporting\". "
            f"Use a text claim from the same section as the headline.\n"
            f"</pinned_claims>"
        )
        print(f"[DEBUG] Edit: pinned visuals: {pinned_ids}")

    claim_id_enum = [c['id'] for c in catalog]
    tool = copy.deepcopy(EDIT_SPEC_TOOL)
    # Inject enum into new_claim_id
    tool['input_schema']['properties']['edits']['items']['properties']['new_claim_id']['enum'] = claim_id_enum

    brand_block = ""
    if brand_guidelines:
        brand_block = f"<brand_guidelines>\n{json.dumps(brand_guidelines, indent=2)}\n</brand_guidelines>\n\n"

    user_content = (
        f"<current_spec>\n{json.dumps(resolved_spec, indent=2)}\n</current_spec>\n\n"
        f"<claim_catalog>\n{json.dumps(catalog, indent=2)}\n</claim_catalog>\n\n"
        f"{brand_block}"
        f"{pinned_directive}"
        f"{prompt}"
    )

    messages = list(history or []) + [{'role': 'user', 'content': user_content}]

    response = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=2048,
        system=EDIT_SPEC_SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "tool", "name": "edit_slide_spec"},
        messages=messages,
    )

    edits = None
    for block in response.content:
        if block.type == 'tool_use' and block.name == 'edit_slide_spec':
            edits = block.input.get('edits', [])
            break

    if not edits:
        raise ValueError("Model did not return edits")

    print(f"[DEBUG] edit_slide_spec edits returned: {json.dumps(edits, indent=2)}")

    # Apply edits to a copy of the spec
    spec = copy.deepcopy(current_spec)
    print(f"[DEBUG] prev spec before edits: {json.dumps(spec, indent=2)}")
    slides = spec.get('slides', [])

    # Separate structural edits (add/remove slide) from per-slide edits
    per_slide_edits = []
    removes = []
    adds = []
    for edit in edits:
        action = edit['action']
        if action == 'remove_slide':
            removes.append(edit)
        elif action == 'add_slide':
            adds.append(edit)
        else:
            per_slide_edits.append(edit)

    # Pass 1: apply per-slide edits (before structural changes shift indices)
    for edit in per_slide_edits:
        idx = edit['slide_index']
        if idx < 0 or idx >= len(slides):
            continue
        slide = slides[idx]
        action = edit['action']

        if action == 'replace_headline' and edit.get('new_claim_id'):
            slide['headline'] = {'claim_id': edit['new_claim_id']}
        elif action == 'replace_body_claim' and edit.get('body_claim_index') is not None:
            bi = edit['body_claim_index']
            if 0 <= bi < len(slide.get('body_claims', [])):
                slide['body_claims'][bi] = {
                    'claim_id': edit.get('new_claim_id', slide['body_claims'][bi].get('claim_id')),
                    'role': edit.get('new_role', slide['body_claims'][bi].get('role', 'supporting')),
                }
        elif action == 'add_body_claim' and edit.get('new_claim_id'):
            slide.setdefault('body_claims', []).append({
                'claim_id': edit['new_claim_id'],
                'role': edit.get('new_role', 'supporting'),
            })
        elif action == 'remove_body_claim' and edit.get('body_claim_index') is not None:
            bi = edit['body_claim_index']
            if 0 <= bi < len(slide.get('body_claims', [])):
                slide['body_claims'].pop(bi)
        elif action == 'change_layout' and edit.get('new_layout'):
            slide['layout'] = edit['new_layout']
        elif action == 'change_title' and edit.get('new_title'):
            slide['slide_title'] = edit['new_title']

    # Pass 2: remove slides in reverse index order to avoid shifting
    for edit in sorted(removes, key=lambda e: e['slide_index'], reverse=True):
        idx = edit['slide_index']
        if 0 <= idx < len(slides):
            slides.pop(idx)

    # Pass 3: insert new slides in forward order
    for edit in sorted(adds, key=lambda e: e.get('insert_after', len(slides))):
        new_slide = edit.get('new_slide')
        if not new_slide:
            continue
        insert_after = edit.get('insert_after', len(slides) - 1)
        insert_pos = insert_after + 1 if insert_after >= 0 else 0
        insert_pos = min(insert_pos, len(slides))
        slides.insert(insert_pos, new_slide)

    print(f"[DEBUG] spec after edits applied: {json.dumps(spec, indent=2)}")
    print(f"[PIPELINE] edit_slide_spec: result → {len(slides)} slides, edits={len(per_slide_edits)} per-slide, {len(adds)} adds, {len(removes)} removes")
    return spec


# ── Incremental per-slide generation pipeline ─────────────────────────────────

NARRATIVE_PLAN_TOOL = {
    "name": "plan_narrative",
    "description": "Plan the narrative arc of the slide deck by listing slide topics grounded in document headings.",
    "input_schema": {
        "type": "object",
        "properties": {
            "slides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Short description of the slide's intent, derived from the document heading"
                        },
                        "section": {
                            "type": "string",
                            "description": "The EXACT heading title from <document_outline> that this slide maps to"
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Key terms from the heading text for claim filtering"
                        },
                        "claim_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional: claim types if known (efficacy, safety, dosing, isi, etc.)"
                        }
                    },
                    "required": ["topic", "section", "keywords"]
                }
            }
        },
        "required": ["slides"]
    }
}

SELECT_CLAIMS_TOOL = {
    "name": "select_claims",
    "description": "Select the most relevant claims for a single slide topic.",
    "input_schema": {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "role": {
                            "type": "string",
                            "enum": ["headline", "supporting", "comparison", "context", "subgroup", "footer"]
                        }
                    },
                    "required": ["claim_id", "role"]
                }
            }
        },
        "required": ["selected"]
    }
}

BUILD_SLIDE_TOOL = {
    "name": "build_slide",
    "description": "Build a single slide: choose component/layout, wire claims, write title.",
    "input_schema": {
        "type": "object",
        "properties": {
            "layout": {
                "type": "string",
                "enum": [
                    "hero", "big_stat", "stat_row", "two_column",
                    "three_column_cards", "comparison_table",
                    "data_table", "subgroup_forest", "title_only"
                ]
            },
            "slide_title": {
                "type": "string",
                "description": (
                    "Creative framing headline with NO numbers, NO percentages, "
                    "NO comparative outcomes. Pure brand/context copy only."
                )
            },
            "headline": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "emphasis": {
                        "type": "object",
                        "properties": {
                            "numeric_value_index": {"type": "integer"},
                            "style": {
                                "type": "string",
                                "enum": ["hero_number", "bold", "color_accent"]
                            }
                        }
                    }
                },
                "required": ["claim_id"]
            },
            "body_claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "role": {
                            "type": "string",
                            "enum": ["supporting", "comparison", "context", "subgroup"]
                        }
                    },
                    "required": ["claim_id", "role"]
                }
            },
            "footer_claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"}
                    },
                    "required": ["claim_id"]
                }
            },
            "cta_text": {
                "type": "string",
                "description": "Optional CTA button label. Short, no clinical data."
            }
        },
        "required": ["layout", "slide_title", "headline"]
    }
}

NARRATIVE_PLAN_SYSTEM = """You are a pharma slide deck narrative planner. You plan slides strictly from the document's own structure.

HARD RULE: Every slide you plan MUST map to a real section heading from <document_outline>. You must set the "section" field to the EXACT heading title from the outline. Do NOT invent topics that are not in the outline. Do NOT use generic categories like "efficacy overview" or "safety profile" unless those exact words appear as a heading in the outline.

Your job:
1. Read <document_outline> to understand what sections the document contains.
2. Read the user's prompt to understand which parts of the document they want slides for.
3. Map the user's request to specific outline headings. Each slide plan corresponds to one or more outline sections.
4. Set the "topic" field to a short description derived from the heading, and the "section" field to the exact heading title.
5. Set "keywords" to key terms from the heading text itself — not from outside knowledge.

Guidelines:
- Start with a hero/title slide if the request implies a full deck
- Keep the deck focused — 4-8 slides for a typical request
- When the user says something broad like "efficacy", find all outline headings that fall under efficacy-related sections and plan slides from those specific headings
- When <visual_assets> is provided, these are tables and figures extracted from the document. Incorporate them into the narrative when relevant. Use keywords from the visual asset's text/caption in the slide plan's keywords field.
- If <document_outline> is missing or empty, tell the user via a single-slide plan with topic "No document structure available — please re-upload the document"."""

SELECT_CLAIMS_SYSTEM = """You are a strict claim selector for pharma slides. Given a slide topic and candidate claims, select ONLY the claims that are directly relevant to this specific slide topic. Err on the side of fewer, more relevant claims.

Rules:
- Select 1 claim for the "headline" role — the most impactful claim for this topic
- Select 0-4 claims for supporting roles (supporting, comparison, context, subgroup)
- Select ISI/boilerplate claims for the "footer" role when available and relevant
- Do NOT select claims that are tangentially related — strict relevance only
- Every selected claim must have a clear reason for being on THIS slide
- Claims with content_format "table" or "figure" are visual assets (extracted tables/charts). When the slide topic involves data visualization, charts, or tabular data, prefer selecting these visual claims as they render as rich content on the slide.
- CRITICAL: Select at most ONE table claim per slide. Pick the table whose caption most closely matches the slide topic. Do NOT select multiple tables.
- When you select a content_format "table" claim, do NOT also select text claims that duplicate rows from that table. The table claim already contains complete structured data. Only add 1-2 text claims for context or footnotes that are NOT in the table itself.
- NEVER assign a "table" or "figure" claim to the "headline" role. Visual assets must always be "supporting" body claims. The headline must always be a text claim that frames the visual.
- Pay close attention to what the table caption says. "adverse reactions" and "laboratory abnormalities" are DIFFERENT tables. Match the table whose caption aligns with the slide topic."""

BUILD_SLIDE_SYSTEM = """You are a pharma slide builder. You receive a slide topic, a set of pre-selected claims (with assigned roles), brand guidelines, and component patterns.

HARD CONSTRAINTS:
- You MUST use EVERY claim from <selected_claims>. Never drop, skip, or omit any claim.
- You may ONLY use claim_id values that appear in <selected_claims>. Never invent, guess, or placeholder a claim_id. Copy each claim_id string exactly as provided.
- The layout must adapt to accommodate ALL the given claims, not the other way around.

Your job in order:
1. Read all claims from <selected_claims> and note their roles and numeric_values.
2. Pick the layout that best presents ALL of these claims using the VWES decision tree below.
3. Wire every claim into the output using its exact claim_id. Write a slide_title (no numbers/percentages). Set emphasis per the rules below.

LAYOUT SELECTION — VWES decision tree (first match wins):

You are optimizing for Visual Weight Equilibrium across 5 dimensions:
  T (Type hierarchy): headline-to-body size ratio should feel 2.5×–3.5×. Layouts with one dominant element (big_stat, hero) score high.
  C (Color weight): 25%–40% chroma coverage is ideal. Each color_accent emphasis adds ~5% chroma.
  S (Spatial balance): visual mass should be centered ±10%. two_column must have roughly equal mass per side. big_stat is inherently centered.
  H (White space): 30%–50% negative space. Fewer elements = more breathing room. big_stat scores highest, data_table lowest.
  D (Data density): fewer distinct elements improve comprehension.

STEP 1 — OVERRIDE LAYOUTS (check first, always win):
  - Any body claim has role "subgroup" AND has 3+ numeric_values → subgroup_forest
  - Any body claim has role "comparison" AND headline has 2+ numeric_values → comparison_table
  - More than 5 non-footer claims → data_table (accommodates high density)

STEP 2 — COUNT non-footer claims (headline counts as 1):
  Total = 1 → big_stat IF headline has numeric_values, else two_column
  Total = 2 → two_column (headline left, 1 supporting right)
  Total = 3 → three_column_cards IF all 3 have the same role and similar numeric_values count
               two_column IF roles differ
  Total = 4 → stat_row (headline top, 3 metrics below)
  Total = 5 → stat_row with 4 body claims
  Total > 5 → data_table

STEP 3 — SPATIAL BALANCE CHECK (S dimension, two_column only):
  Left column = headline claim. Right column = body claims.
  If right has only 1 claim with text under 80 chars and no numeric_values → switch to big_stat.
  Never output two_column where one side is visually empty.

STEP 4 — SPECIAL CASES:
  - No clinical claims, deck opener → hero
  - Section divider between topics → title_only

SLIDE TITLE (the only text you write):
- Must be a framing headline with ZERO numbers, ZERO percentages, ZERO comparative language
- Good: "Proven Survival Benefit", "Manageable Safety Profile"
- Bad: "34% reduction in OS risk"

EMPHASIS — set after layout is decided:
  big_stat: emphasis.style = "hero_number" on the numeric_value_index with the largest value
  two_column, stat_row: emphasis.style = "bold" on headline numeric_value_index 0
  three_column_cards: emphasis.style = "color_accent" on each card's key numeric_value_index
  comparison_table, data_table, subgroup_forest: no emphasis (data speaks for itself)
  footer claims: never set emphasis

CONTENT FORMAT OVERRIDES:
When a claim has content_format other than "text", apply these layout overrides:
- content_format: "table" → prefer data_table layout. The table claim contains complete structured data in table_markdown. Do NOT also select individual text claims that duplicate rows from the same table — the table_markdown already has all the data. You may select 1-2 text claims for context/footnotes only.
- content_format: "figure" → prefer two_column layout with the figure in one column, or full-width figure display. Select supporting text claims for stats and context that complement the figure.
These overrides take priority over the VWES decision tree above."""


def _plan_narrative(prompt, claims, brand_guidelines, target_audience, audience_rules, history, doc_outline=None):
    """Step 0: Plan the narrative arc — produces ordered slide topics."""
    client = _get_client()

    # Build visual assets list (tables/figures) — the planner needs to know what visuals exist
    visual_assets = []
    for c in claims:
        content_format = c.get('content_format', 'text')
        if content_format in ('table', 'figure'):
            visual_assets.append({
                'id': c.get('id'),
                'content_format': content_format,
                'text': c.get('text', ''),
                'section': c.get('section'),
                'page_number': c.get('page_number'),
            })

    context_parts = []
    if doc_outline:
        context_parts.append(f"<document_outline>\n{json.dumps(doc_outline, indent=2)}\n</document_outline>")
    else:
        context_parts.append("<document_outline>No document outline available.</document_outline>")
    if visual_assets:
        context_parts.append(f"<visual_assets>\n{json.dumps(visual_assets, indent=2)}\n</visual_assets>")
    if brand_guidelines:
        context_parts.append(f"<brand_guidelines>\n{json.dumps(brand_guidelines, indent=2)}\n</brand_guidelines>")
    if target_audience:
        context_parts.append(f"<target_audience>\n{target_audience}\n</target_audience>")
    if audience_rules and target_audience and target_audience in audience_rules:
        context_parts.append(
            f"<audience_rules>\n{json.dumps({target_audience: audience_rules[target_audience]}, indent=2)}\n</audience_rules>"
        )

    user_content = "\n\n".join(context_parts) + f"\n\n{prompt}"
    messages = list(history or []) + [{'role': 'user', 'content': user_content}]

    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=2048,
        system=NARRATIVE_PLAN_SYSTEM,
        tools=[NARRATIVE_PLAN_TOOL],
        tool_choice={"type": "tool", "name": "plan_narrative"},
        messages=messages,
    )

    for block in response.content:
        if block.type == 'tool_use' and block.name == 'plan_narrative':
            print(f"[DEBUG] Narrative plan: {json.dumps(block.input, indent=2)}")
            return block.input

    raise ValueError("Narrative planner did not return a plan")


def _prefilter_claims(claims, slide_plan):
    """Step 1a: Programmatic pre-filter — narrow claims by type and keyword overlap."""
    target_types = set(t.lower() for t in slide_plan.get('claim_types', []))
    # Expand compound keywords: "overall_survival" → {"overall_survival", "overall", "survival"}
    keywords = set()
    for k in slide_plan.get('keywords', []):
        kl = k.lower()
        keywords.add(kl)
        if '_' in kl:
            keywords.update(kl.split('_'))
    target_section = (slide_plan.get('section') or '').lower().strip()

    content_scored = []
    isi_claims = []
    for c in claims:
        ctype = (c.get('claim_type') or '').lower()
        # Normalize tags: split multi-word tags into individual tokens too
        raw_tags = set(t.lower() for t in (c.get('tags') or []))
        tags = set(raw_tags)
        for t in raw_tags:
            tags.update(t.split())
        content_format = c.get('content_format', 'text')

        # Collect ISI/boilerplate separately (capped later, not competing for content slots)
        if ctype in ('isi', 'boilerplate'):
            isi_claims.append(c)
            continue

        # Visual claims (tables/figures) get boosted scoring — they're high-value
        # and their short captions shouldn't penalize them
        is_visual = content_format in ('table', 'figure')

        # Must match at least one target type (if types specified)
        # Visual claims bypass the type filter since they're always 'stat'
        if target_types and ctype not in target_types and not is_visual:
            continue

        # Score by keyword overlap with tags + text keywords
        text_tokens = set(re.sub(r'[^a-z0-9\s]', '', (c.get('text') or '').lower()).split())
        tag_overlap = len(keywords & tags)
        text_overlap = len(keywords & text_tokens)
        score = tag_overlap * 3 + text_overlap  # tags weighted higher

        # Heavily boost claims from matching document section (check full hierarchy)
        claim_sections = [s.lower() for s in (c.get('section_hierarchy') or [])]
        if not claim_sections:
            # Fallback to flat section for backward compat
            flat = (c.get('section') or '').lower().strip()
            if flat:
                claim_sections = [flat]
        if target_section and any(target_section in s for s in claim_sections):
            score += 10

        # Match topic words against claim text (critical for tables with enriched captions)
        topic_words = set(re.sub(r'[^a-z0-9\s]', '', (slide_plan.get('topic') or '').lower()).split())
        topic_words -= {'the', 'and', 'for', 'from', 'with', 'that', 'this', 'show', 'add', 'table', 'slide', 'create'}
        claim_text_words = set(re.sub(r'[^a-z0-9\s]', '', (c.get('text') or '').lower()).split())
        topic_text_match = len(topic_words & claim_text_words)
        if is_visual and topic_text_match >= 2:
            score += 15  # strong match between topic and table caption/context

        # Boost visual claims — any keyword match in their caption is highly relevant
        if is_visual and (text_overlap > 0 or tag_overlap > 0):
            score += 8
        # Visual claims in matching section always included even with zero keyword overlap
        elif is_visual and target_section and any(target_section in s for s in claim_sections):
            score += 5

        # Boost if the slide topic explicitly mentions this table/figure by number
        # e.g., topic "Overall Survival (Table 7, Figure 2)" → match "Table 7" in caption
        if is_visual:
            claim_text_lower = (c.get('text') or '').lower()
            topic_lower = (slide_plan.get('topic') or '').lower()
            # Match "table N" or "figure N" in both topic and caption
            for ref in re.findall(r'(?:table|figure)\s*\d+', topic_lower):
                if ref in claim_text_lower:
                    score += 20  # strong signal — user/planner explicitly named this visual
                    break

        if score > 0 or not keywords:
            content_scored.append((c, score))

    # Take top 17 content claims + up to 3 ISI/boilerplate
    content_scored.sort(key=lambda x: x[1], reverse=True)
    result = [c for c, _ in content_scored[:17]] + isi_claims[:3]

    # Debug: log top candidates with scores
    for c, s in content_scored[:17]:
        fmt = c.get('content_format', 'text')
        label = f" [{fmt}]" if fmt != 'text' else ''
        print(f"[DEBUG] Prefilter candidate (score={s}): {c.get('id', '?')}{label} — {c.get('text', '')[:80]}")
    if isi_claims:
        print(f"[DEBUG] Prefilter: {len(isi_claims)} ISI/boilerplate claims, including top {min(3, len(isi_claims))}")
    return result


def _select_claims(slide_topic, candidate_claims):
    """Step 1b: LLM strict claim selection for a single slide topic."""
    client = _get_client()

    catalog = [
        {
            "id": c['id'],
            "text": c['text'],
            "type": c.get('claim_type', ''),
            "tags": c.get('tags') or [],
            "content_format": c.get('content_format', 'text'),
            "section_hierarchy": c.get('section_hierarchy') or [],
        }
        for c in candidate_claims
    ]

    # Inject claim_id enum into tool
    tool = copy.deepcopy(SELECT_CLAIMS_TOOL)
    claim_ids = [c['id'] for c in catalog]
    tool['input_schema']['properties']['selected']['items']['properties']['claim_id']['enum'] = claim_ids

    user_content = (
        f"<slide_topic>\n{slide_topic}\n</slide_topic>\n\n"
        f"<candidate_claims>\n{json.dumps(catalog, indent=2)}\n</candidate_claims>"
    )

    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=1024,
        system=SELECT_CLAIMS_SYSTEM,
        tools=[tool],
        tool_choice={"type": "tool", "name": "select_claims"},
        messages=[{'role': 'user', 'content': user_content}],
    )

    for block in response.content:
        if block.type == 'tool_use' and block.name == 'select_claims':
            selected = block.input.get('selected', [])
            print(f"[DEBUG] Claims selected for '{slide_topic}': {json.dumps(block.input, indent=2)}")

            # Guard: visual claims (table/figure) must never be headlines — demote to body
            claims_lookup = {c['id']: c for c in candidate_claims}
            headline_sel = [s for s in selected if s.get('role') == 'headline']
            if headline_sel:
                h = headline_sel[0]
                h_claim = claims_lookup.get(h['claim_id'], {})
                if h_claim.get('content_format', 'text') in ('table', 'figure'):
                    print(f"[DEBUG] Demoting visual claim {h['claim_id']} from headline to supporting")
                    h['role'] = 'supporting'
                    # Promote first text body claim to headline
                    for s in selected:
                        if s['role'] != 'headline' and s['role'] != 'footer':
                            s_claim = claims_lookup.get(s['claim_id'], {})
                            if s_claim.get('content_format', 'text') == 'text':
                                s['role'] = 'headline'
                                print(f"[DEBUG] Promoted {s['claim_id']} to headline")
                                break

            # Guard: max ONE table per slide. If multiple tables selected, keep the
            # most relevant one (best caption match to slide_topic) and drop the rest.
            table_selections = [
                s for s in selected
                if claims_lookup.get(s['claim_id'], {}).get('content_format') == 'table'
            ]
            if len(table_selections) > 1:
                topic_lower = slide_topic.lower()
                topic_words = set(re.sub(r'[^a-z0-9\s]', '', topic_lower).split())

                def _table_relevance(sel):
                    claim = claims_lookup.get(sel['claim_id'], {})
                    caption = (claim.get('text') or '').lower()
                    caption_words = set(re.sub(r'[^a-z0-9\s]', '', caption).split())
                    score = len(topic_words & caption_words) * 2
                    # Bonus for table number match
                    for ref in re.findall(r'table\s*\d+', topic_lower):
                        if ref in caption:
                            score += 20
                    return score

                table_selections.sort(key=_table_relevance, reverse=True)
                keep = table_selections[0]
                drop_ids = {s['claim_id'] for s in table_selections[1:]}
                selected = [s for s in selected if s['claim_id'] not in drop_ids]
                print(f"[DEBUG] Kept table {keep['claim_id']}, dropped {drop_ids}")

            return selected

    raise ValueError(f"Claim selector did not return selections for topic: {slide_topic}")


def _build_slide(slide_topic, selected_claims, all_claims, brand_guidelines, component_patterns):
    """Steps 2+3+4: Component selection → template → assembly for a single slide."""
    client = _get_client()

    # Build full claim data for selected claims
    claims_by_id = {c['id']: c for c in all_claims}
    selected_full = []
    for sel in selected_claims:
        cid = sel['claim_id']
        claim = claims_by_id.get(cid)
        if claim:
            fmt = claim.get('content_format', 'text')
            if fmt in ('table', 'figure'):
                # Visual claims: send only label + format, no raw data
                caption = claim['text'][:120] if claim.get('text') else fmt
                entry = {
                    "claim_id": cid,
                    "role": sel['role'],
                    "text": f"[Visual: {caption}]",
                    "content_format": fmt,
                }
            else:
                entry = {
                    "claim_id": cid,
                    "role": sel['role'],
                    "text": claim['text'],
                    "type": claim.get('claim_type', ''),
                    "tags": claim.get('tags') or [],
                    "numeric_values": claim.get('numeric_values') or [],
                    "content_format": fmt,
                }
            selected_full.append(entry)

    # Guard: if no valid claims resolved, return a title_only slide with no claim refs
    if not selected_full:
        print(f"[DEBUG] No valid claims resolved for '{slide_topic}', returning title_only slide")
        return {
            "layout": "title_only",
            "slide_title": slide_topic,
        }

    # Inject claim_id enum into tool
    tool = copy.deepcopy(BUILD_SLIDE_TOOL)
    claim_ids = [s['claim_id'] for s in selected_full]
    print(f"[DEBUG] claim_ids for build_slide enum: {claim_ids}")
    # Inject into headline
    tool['input_schema']['properties']['headline']['properties']['claim_id']['enum'] = claim_ids
    # Inject into body_claims
    tool['input_schema']['properties']['body_claims']['items']['properties']['claim_id']['enum'] = claim_ids
    # Inject into footer_claims
    tool['input_schema']['properties']['footer_claims']['items']['properties']['claim_id']['enum'] = claim_ids

    context_parts = [
        f"<slide_topic>\n{slide_topic}\n</slide_topic>",
        f"<selected_claims>\n{json.dumps(selected_full, indent=2)}\n</selected_claims>",
    ]
    if brand_guidelines:
        context_parts.append(f"<brand_guidelines>\n{json.dumps(brand_guidelines, indent=2)}\n</brand_guidelines>")
    if component_patterns:
        context_parts.append(f"<component_patterns>\n{json.dumps(component_patterns, indent=2)}\n</component_patterns>")

    user_content = "\n\n".join(context_parts)

    response = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=2048,
        system=BUILD_SLIDE_SYSTEM,
        tools=[tool],
        tool_choice={"type": "tool", "name": "build_slide"},
        messages=[{'role': 'user', 'content': user_content}],
    )

    for block in response.content:
        if block.type == 'tool_use' and block.name == 'build_slide':
            result = block.input
            print(f"[DEBUG] Built slide for '{slide_topic}': {result.get('layout')}")

            # Post-check: scrub any claim_ids not in the provided set
            valid_ids = set(claim_ids)
            headline = result.get('headline', {})
            if headline.get('claim_id') and headline['claim_id'] not in valid_ids:
                print(f"[WARN] headline claim_id '{headline['claim_id']}' not valid, replacing with {claim_ids[0]}")
                headline['claim_id'] = claim_ids[0]

            for claim_list_key in ('body_claims', 'footer_claims'):
                result[claim_list_key] = [
                    c for c in result.get(claim_list_key, [])
                    if c.get('claim_id') in valid_ids
                ]

            return result

    raise ValueError(f"Slide builder did not return a slide for topic: {slide_topic}")


def _match_explicit_visuals(prompt: str, claims: list) -> list:
    """Detect explicit table/figure references in the user prompt and return matching claims.

    Handles patterns like:
    - "display table 7", "show table 5", "table 6"
    - "show figure 2", "display the Kaplan-Meier figure"
    - "show the survival table", "display the adverse reactions table"
    """
    prompt_lower = prompt.lower()
    matched = []

    # Build visual claim lookup
    visual_claims = [c for c in claims if c.get('content_format') in ('table', 'figure')]
    print(f"[PIPELINE] _match_explicit_visuals: {len(visual_claims)} visual claims in catalog")
    if not visual_claims:
        print(f"[PIPELINE] _match_explicit_visuals: no visual claims → skip")
        return []

    # 1. Match by explicit number: "table 5", "figure 2"
    table_nums = re.findall(r'\btable\s*(\d+)\b', prompt_lower)
    figure_nums = re.findall(r'\bfigure\s*(\d+)\b', prompt_lower)
    print(f"[PIPELINE] _match_explicit_visuals: regex found table_nums={table_nums}, figure_nums={figure_nums}")

    for num in table_nums:
        pattern = f"table {num}"
        for c in visual_claims:
            caption = (c.get('text') or '').lower()
            if c['content_format'] == 'table' and pattern in caption:
                if c not in matched:
                    matched.append(c)
                    print(f"[DEBUG] Explicit match: '{pattern}' → {c['id']}")

    for num in figure_nums:
        pattern = f"figure {num}"
        for c in visual_claims:
            caption = (c.get('text') or '').lower()
            if c['content_format'] == 'figure' and pattern in caption:
                if c not in matched:
                    matched.append(c)
                    print(f"[DEBUG] Explicit match: '{pattern}' → {c['id']}")

    # 2. Match by keyword in caption: "survival table", "adverse reactions table",
    #    "Kaplan-Meier figure", "dose reduction table"
    # Extract key phrases around "table" or "figure" mentions
    keyword_patterns = re.findall(
        r'(?:show|display|include|add|render|create)?\s*(?:the\s+)?'
        r'([\w\s-]+?)\s*(?:table|figure)\b',
        prompt_lower,
    )
    keyword_patterns += re.findall(
        r'\b(?:table|figure)\s+(?:of|for|about|showing|with)\s+([\w\s-]+)',
        prompt_lower,
    )
    for phrase in keyword_patterns:
        phrase = phrase.strip()
        if not phrase or len(phrase) < 3:
            continue
        phrase_words = set(phrase.split())
        for c in visual_claims:
            caption = (c.get('text') or '').lower()
            caption_words = set(re.sub(r'[^a-z0-9\s]', '', caption).split())
            # Check if the key phrase words appear in the caption
            overlap = phrase_words & caption_words
            if len(overlap) >= min(2, len(phrase_words)):
                if c not in matched:
                    matched.append(c)
                    print(f"[DEBUG] Keyword match: '{phrase}' → {c['id']} ({c['text'][:60]})")

    # 3. Generic "show table" / "display the table" without number — match all?
    #    No, too broad. Only if there's exactly one table claim, or skip.
    if not matched and re.search(r'\b(?:show|display|include)\s+(?:the\s+)?table\b', prompt_lower):
        # User wants "the table" but didn't specify which — check if topic narrows it
        print(f"[DEBUG] Generic 'show table' request — will rely on prefilter/selection")

    print(f"[PIPELINE] _match_explicit_visuals: {len(matched)} matches → {[c['id'] for c in matched]}")
    return matched


def generate_slide_spec(
    prompt: str,
    claims: list,
    brand_guidelines: Optional[dict] = None,
    target_audience: Optional[str] = None,
    audience_rules: Optional[dict] = None,
    history: Optional[list] = None,
    component_patterns: Optional[dict] = None,
    on_slide_ready: Optional[Callable] = None,
    doc_outline: Optional[list] = None,
) -> dict:
    """
    Incremental per-slide generation pipeline.
    Step 0: Narrative plan → per-slide loop (1a: prefilter, 1b: select, 2+3+4: build).
    Returns the parsed slide spec dict.
    """
    print(f"[PIPELINE] generate_slide_spec: prompt=\"{prompt[:120]}\"")
    print(f"[PIPELINE] generate_slide_spec: {len(claims)} total claims")
    # Step -1: Detect explicit visual references in the user prompt
    pinned_visuals = _match_explicit_visuals(prompt, claims)
    pinned_ids = {c['id'] for c in pinned_visuals}
    if pinned_visuals:
        print(f"[DEBUG] Pinned {len(pinned_visuals)} visual claims from prompt: {[c['id'] for c in pinned_visuals]}")

    # Step 0: Plan narrative
    plan = _plan_narrative(prompt, claims, brand_guidelines,
                           target_audience, audience_rules, history,
                           doc_outline=doc_outline)

    slide_plans = plan.get('slides', [])

    # Decide which slide each pinned visual belongs to (best-match, one visual per slide max).
    # Score each (pinned_visual, slide_plan) pair and assign greedily.
    pinned_assignment = {}  # slide_idx → list of pinned claim dicts
    if pinned_visuals:
        unassigned = list(pinned_visuals)
        for pv in unassigned:
            pv_text = (pv.get('text') or '').lower()
            pv_section = (pv.get('section') or '').lower()
            best_idx, best_score = 0, -1
            for si, sp in enumerate(slide_plans):
                topic = (sp.get('topic') or '').lower()
                section = (sp.get('section') or '').lower()
                score = 0
                # Check if topic mentions the table/figure by number
                for ref in re.findall(r'(?:table|figure)\s*\d+', topic):
                    if ref in pv_text:
                        score += 20
                # Keyword overlap between topic and caption
                topic_words = set(re.sub(r'[^a-z0-9\s]', '', topic).split())
                pv_words = set(re.sub(r'[^a-z0-9\s]', '', pv_text).split())
                score += len(topic_words & pv_words) * 2
                # Section match
                if section and pv_section and section in pv_section:
                    score += 5
                if score > best_score:
                    best_score = score
                    best_idx = si
            pinned_assignment.setdefault(best_idx, []).append(pv)
            print(f"[DEBUG] Pinned visual {pv['id']} assigned to slide {best_idx} (score={best_score})")

    def _process_slide(idx_and_plan):
        idx, slide_plan = idx_and_plan
        topic = slide_plan['topic']
        print(f"[DEBUG] Processing slide {idx}: {topic}")

        # Pinned visuals for THIS slide only
        slide_pinned = pinned_assignment.get(idx, [])

        # Step 1a: Programmatic pre-filter
        candidates = _prefilter_claims(claims, slide_plan)

        # Ensure this slide's pinned visuals are in candidates
        candidate_ids = {c['id'] for c in candidates}
        for pv in slide_pinned:
            if pv['id'] not in candidate_ids:
                candidates.append(pv)
                print(f"[DEBUG] Injected pinned visual into candidates: {pv['id']}")

        print(f"[DEBUG] Pre-filtered {len(candidates)} candidates for '{topic}'")

        # Step 1b: LLM strict selection
        selected = _select_claims(topic, candidates)

        # Ensure this slide's pinned visuals are in the selection
        selected_ids = {s['claim_id'] for s in selected}
        for pv in slide_pinned:
            if pv['id'] not in selected_ids:
                selected.append({'claim_id': pv['id'], 'role': 'supporting'})
                print(f"[DEBUG] Force-added pinned visual to selection: {pv['id']}")

        # Steps 2+3+4: Build slide
        slide = _build_slide(topic, selected, claims,
                             brand_guidelines, component_patterns)
        if on_slide_ready:
            on_slide_ready(idx, slide)
        return idx, slide

    # Log pinned assignments summary
    if pinned_assignment:
        for si, pvs in pinned_assignment.items():
            print(f"[PIPELINE] generate_slide_spec: slide {si} pinned visuals: {[pv['id'] for pv in pvs]}")

    # Run slides in parallel — each slide's LLM calls are independent
    slides = [None] * len(slide_plans)
    with ThreadPoolExecutor(max_workers=min(len(slide_plans), 5)) as executor:
        futures = {
            executor.submit(_process_slide, (i, sp)): i
            for i, sp in enumerate(slide_plans)
        }
        for future in as_completed(futures):
            idx, slide = future.result()
            slides[idx] = slide

    # Per-slide summary
    for i, s in enumerate(slides):
        layout = s.get('layout', '?') if s else '?'
        body_count = len(s.get('body_claims', [])) if s else 0
        title = s.get('slide_title', '') if s else ''
        print(f"[PIPELINE] generate_slide_spec: slide {i} → layout={layout}, body_claims={body_count}, title=\"{title[:60]}\"")
    return {"slides": slides}


# ── Design token extraction ───────────────────────────────────────────────────

def extract_design_tokens(pdf_text: str, tables: list = None) -> dict:
    client = _get_client()
    prompt = f'Extract all design tokens from this style guide:\n---\n{pdf_text}\n---\n'
    if tables:
        table_text = '\n\n'.join(
            f'Table {t["index"]} (page {t["page_no"]}):\n{t["markdown"]}' for t in tables
        )
        prompt += f'\nStructured tables extracted from the PDF:\n---\n{table_text}\n---\n'
    prompt += 'Return only the JSON object, no explanation.'
    message = client.messages.create(
        model='claude-opus-4-6',
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{
            'role': 'user',
            'content': prompt,
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
