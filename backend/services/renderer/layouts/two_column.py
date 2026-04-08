import html as _html
from services.renderer.components import render_header, render_footer, render_slide_title, get_emphasis_html


def render(slide: dict, claims_by_id: dict, style, asset_ctx: dict) -> str:
    headline = slide.get('headline', {})
    cid = headline.get('claim_id')
    claim = claims_by_id.get(cid, {})
    headline_html = get_emphasis_html(claim, headline.get('emphasis'), style)

    supporting = [bc for bc in slide.get('body_claims', []) if bc.get('role') in ('supporting', 'context')]
    comparison = [bc for bc in slide.get('body_claims', []) if bc.get('role') in ('comparison', 'subgroup')]
    right_claims = comparison or supporting[1:]
    left_extra = supporting[:1] if not comparison else supporting

    def claim_p(cid):
        if cid and cid in claims_by_id:
            return (
                f'<p style="font-family:{_html.escape(style.font_body)};'
                f'font-size:{_html.escape(style.size_body)};'
                f'color:{_html.escape(style.text)};margin:6px 0;line-height:1.4;">'
                f'{_html.escape(claims_by_id[cid]["text"])}</p>'
            )
        return ''

    left_html = (
        f'<div style="font-family:{_html.escape(style.font_hero)};'
        f'font-size:{_html.escape(style.size_h2)};'
        f'font-weight:{style.weight_h1};'
        f'color:{_html.escape(style.text)};margin-bottom:12px;line-height:1.3;">'
        f'{headline_html}</div>'
        + ''.join(claim_p(bc['claim_id']) for bc in left_extra if bc.get('claim_id'))
    )

    right_html = ''.join(claim_p(bc['claim_id']) for bc in right_claims if bc.get('claim_id'))

    header = render_header(asset_ctx.get('assets', []), style, asset_ctx.get('brand_guidelines', {}))
    footer = render_footer(slide.get('footer_claims', []), claims_by_id, style)
    title  = render_slide_title(slide.get('slide_title', ''), style)

    return (
        f'<div data-slide style="width:1024px;height:576px;overflow:hidden;position:relative;'
        f'box-sizing:border-box;background:{_html.escape(style.bg)};">'
        f'{header}'
        f'<div style="padding:24px 48px 80px;">'
        f'{title}'
        f'<div style="display:flex;gap:32px;margin-top:16px;align-items:stretch;">'
        f'<div style="flex:55;padding-right:16px;border-right:2px solid {_html.escape(style.border)};">{left_html}</div>'
        f'<div style="flex:45;padding-left:16px;">{right_html}</div>'
        f'</div>'
        f'</div>'
        f'{footer}'
        f'</div>'
    )
