import html as _html
from services.renderer.components import render_header, render_footer, render_slide_title, get_emphasis_html


def render(slide: dict, claims_by_id: dict, style, asset_ctx: dict) -> str:
    headline = slide.get('headline', {})
    cid = headline.get('claim_id')
    claim = claims_by_id.get(cid, {})

    # Headline + body claims all shown as equal stat cards
    all_claims = [{'claim_id': cid, 'emphasis': headline.get('emphasis'), 'is_headline': True}]
    for bc in slide.get('body_claims', []):
        all_claims.append({'claim_id': bc.get('claim_id'), 'emphasis': None, 'is_headline': False})

    cards = []
    for item in all_claims:
        item_cid = item['claim_id']
        if not item_cid or item_cid not in claims_by_id:
            continue
        item_claim = claims_by_id[item_cid]
        content = get_emphasis_html(item_claim, item.get('emphasis'), style)
        border = f'border-top:3px solid {_html.escape(style.primary)};' if item['is_headline'] else f'border-top:3px solid {_html.escape(style.border)};'
        cards.append(
            f'<div style="flex:1;{border}padding:16px;background:{_html.escape(style.bg_subtle)};'
            f'border-radius:{_html.escape(style.radius_md)};'
            f'font-family:{_html.escape(style.font_body)};'
            f'font-size:{_html.escape(style.size_body)};'
            f'color:{_html.escape(style.text)};line-height:1.4;">'
            f'{content}'
            f'</div>'
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
        f'<div style="display:flex;gap:{_html.escape(style.spacing_md)};margin-top:16px;align-items:stretch;">'
        f'{"".join(cards)}'
        f'</div>'
        f'</div>'
        f'{footer}'
        f'</div>'
    )
