import html as _html
from services.renderer.components import render_header, render_footer, render_slide_title, get_emphasis_html


def render(slide: dict, claims_by_id: dict, style, asset_ctx: dict) -> str:
    headline = slide.get('headline', {})
    cid = headline.get('claim_id')
    claim = claims_by_id.get(cid, {})

    headline_html = get_emphasis_html(claim, headline.get('emphasis'), style)

    body_parts = []
    for bc in slide.get('body_claims', []):
        bcid = bc.get('claim_id')
        if bcid and bcid in claims_by_id:
            body_parts.append(
                f'<p style="font-family:{_html.escape(style.font_body)};'
                f'font-size:{_html.escape(style.size_body)};'
                f'color:{_html.escape(style.text_muted)};'
                f'margin:4px 0;line-height:1.4;">'
                f'{_html.escape(claims_by_id[bcid]["text"])}</p>'
            )

    header = render_header(asset_ctx.get('assets', []), style, asset_ctx.get('brand_guidelines', {}))
    footer = render_footer(slide.get('footer_claims', []), claims_by_id, style)
    title  = render_slide_title(slide.get('slide_title', ''), style)

    return (
        f'<div data-slide style="width:1024px;height:576px;overflow:hidden;position:relative;'
        f'box-sizing:border-box;background:{_html.escape(style.bg)};'
        f'font-family:{_html.escape(style.font_body)};">'
        f'{header}'
        f'<div style="padding:32px 64px 80px;">'
        f'{title}'
        f'<div style="margin-top:16px;">{headline_html}</div>'
        f'<div style="margin-top:16px;">{"".join(body_parts)}</div>'
        f'</div>'
        f'{footer}'
        f'</div>'
    )
