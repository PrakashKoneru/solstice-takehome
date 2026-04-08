import html as _html
from services.renderer.components import render_header, render_footer, render_slide_title


def render(slide: dict, claims_by_id: dict, style, asset_ctx: dict) -> str:
    all_claims = []
    headline = slide.get('headline', {})
    cid = headline.get('claim_id')
    if cid and cid in claims_by_id:
        all_claims.append(claims_by_id[cid])

    for bc in slide.get('body_claims', []):
        bcid = bc.get('claim_id')
        if bcid and bcid in claims_by_id:
            all_claims.append(claims_by_id[bcid])

    rows = ''.join(
        f'<tr>'
        f'<td style="padding:8px 12px;border-bottom:1px solid {_html.escape(style.border)};'
        f'font-family:{_html.escape(style.font_body)};font-size:{_html.escape(style.size_body)};'
        f'color:{_html.escape(style.text)};line-height:1.4;">'
        f'{_html.escape(c["text"])}'
        f'<span style="display:block;font-size:{_html.escape(style.size_caption)};'
        f'color:{_html.escape(style.text_muted)};margin-top:2px;">{_html.escape(c.get("source_citation") or "")}</span>'
        f'</td>'
        f'</tr>'
        for c in all_claims
    )

    header = render_header(asset_ctx.get('assets', []), style, asset_ctx.get('brand_guidelines', {}))
    footer = render_footer(slide.get('footer_claims', []), claims_by_id, style)
    title  = render_slide_title(slide.get('slide_title', ''), style)

    return (
        f'<div data-slide style="width:1024px;height:576px;overflow:hidden;position:relative;'
        f'box-sizing:border-box;background:{_html.escape(style.bg)};">'
        f'{header}'
        f'<div style="padding:24px 48px 80px;">'
        f'{title}'
        f'<table style="width:100%;border-collapse:collapse;margin-top:16px;">'
        f'<thead><tr>'
        f'<th style="text-align:left;padding:8px 12px;'
        f'background:{_html.escape(style.primary)};'
        f'color:{_html.escape(style.text_inverse)};'
        f'font-family:{_html.escape(style.font_hero)};'
        f'font-size:{_html.escape(style.size_body)};border-radius:4px 4px 0 0;">'
        f'Clinical Data</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
        f'</div>'
        f'{footer}'
        f'</div>'
    )
