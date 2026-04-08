"""Shared slide components: header, footer, ISI block."""
import html


def render_header(ds_assets: list, style, brand_guidelines: dict) -> str:
    hallmark = brand_guidelines.get('hallmark', '') if brand_guidelines else ''

    # Try to find logo asset
    logo = next((a for a in (ds_assets or []) if a.get('asset_type') == 'logo'), None)

    if logo and logo.get('file_url'):
        logo_html = (
            f'<img src="{html.escape(logo["file_url"])}" '
            f'style="height:36px;object-fit:contain;" alt="logo">'
        )
    elif hallmark:
        logo_html = (
            f'<span style="font-family:{html.escape(style.font_hero)};'
            f'font-size:18px;font-weight:{style.weight_h1};'
            f'color:{html.escape(style.primary)};">'
            f'{html.escape(hallmark)}</span>'
        )
    else:
        logo_html = ''

    return (
        f'<div style="display:flex;align-items:center;justify-content:flex-end;'
        f'padding:12px 24px 8px;border-bottom:3px solid {html.escape(style.primary)};">'
        f'{logo_html}'
        f'</div>'
    )


def render_footer(footer_claims: list, claims_by_id: dict, style) -> str:
    texts = []
    for fc in footer_claims:
        cid = fc.get('claim_id')
        if cid and cid in claims_by_id:
            texts.append(claims_by_id[cid]['text'])

    if not texts:
        return ''

    items_html = ' '.join(
        f'<span style="margin-right:12px;">{html.escape(t)}</span>'
        for t in texts
    )
    return (
        f'<div style="position:absolute;bottom:0;left:0;right:0;'
        f'background:{html.escape(style.secondary)};'
        f'padding:6px 24px;'
        f'font-family:{html.escape(style.font_caption)};'
        f'font-size:{html.escape(style.size_caption)};'
        f'color:{html.escape(style.text_inverse)};'
        f'line-height:1.3;overflow:hidden;">'
        f'{items_html}'
        f'</div>'
    )


def render_slide_title(title: str, style) -> str:
    if not title:
        return ''
    return (
        f'<div style="font-family:{html.escape(style.font_hero)};'
        f'font-size:{html.escape(style.size_h1)};'
        f'font-weight:{style.weight_h1};'
        f'color:{html.escape(style.text)};'
        f'margin-bottom:{html.escape(style.spacing_md)};'
        f'line-height:1.2;">'
        f'{html.escape(title)}'
        f'</div>'
    )


def get_emphasis_html(claim: dict, emphasis: dict, style) -> str:
    """Return HTML for a claim with optional numeric emphasis."""
    text = claim['text']
    if not emphasis:
        return html.escape(text)

    nv_index = emphasis.get('numeric_value_index')
    em_style = emphasis.get('style', 'bold')
    numeric_values = claim.get('numeric_values') or []

    if nv_index is not None and nv_index < len(numeric_values):
        nv = numeric_values[nv_index]
        hero_val = f"{nv['value']} {nv.get('unit', '')}".strip()

        if em_style == 'hero_number':
            return (
                f'<div style="font-family:{html.escape(style.font_hero)};'
                f'font-size:{html.escape(style.size_hero)};'
                f'font-weight:{style.weight_hero};'
                f'color:{html.escape(style.primary)};'
                f'line-height:1;margin-bottom:8px;">'
                f'{html.escape(hero_val)}</div>'
                f'<div style="font-size:{html.escape(style.size_body)};'
                f'color:{html.escape(style.text_muted)};">'
                f'{html.escape(text)}</div>'
            )
        elif em_style == 'bold':
            escaped = html.escape(text)
            escaped_val = html.escape(hero_val)
            return escaped.replace(escaped_val, f'<strong>{escaped_val}</strong>', 1)
        elif em_style == 'color_accent':
            escaped = html.escape(text)
            escaped_val = html.escape(hero_val)
            return escaped.replace(
                escaped_val,
                f'<span style="color:{html.escape(style.primary)};font-weight:{style.weight_h1};">{escaped_val}</span>',
                1
            )

    return html.escape(text)
