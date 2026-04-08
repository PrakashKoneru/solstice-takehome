"""data_table, subgroup_forest, hero, title_only layouts."""
import html as _html
from services.renderer.components import render_header, render_footer, render_slide_title, get_emphasis_html


def render_data_table(slide: dict, claims_by_id: dict, style, asset_ctx: dict) -> str:
    # Same as comparison_table with a slightly different header label
    from services.renderer.layouts.comparison_table import render
    return render(slide, claims_by_id, style, asset_ctx)


def render_subgroup_forest(slide: dict, claims_by_id: dict, style, asset_ctx: dict) -> str:
    """Renders subgroup claims as a simple bulleted list (forest plot requires chart data)."""
    all_claims = []
    cid = slide.get('headline', {}).get('claim_id')
    if cid and cid in claims_by_id:
        all_claims.append(claims_by_id[cid])
    for bc in slide.get('body_claims', []):
        bcid = bc.get('claim_id')
        if bcid and bcid in claims_by_id:
            all_claims.append(claims_by_id[bcid])

    items = ''.join(
        f'<li style="font-family:{_html.escape(style.font_body)};'
        f'font-size:{_html.escape(style.size_body)};'
        f'color:{_html.escape(style.text)};margin-bottom:6px;line-height:1.4;">'
        f'{_html.escape(c["text"])}</li>'
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
        f'<ul style="list-style:disc;padding-left:20px;margin-top:16px;">{items}</ul>'
        f'</div>'
        f'{footer}'
        f'</div>'
    )


def render_hero(slide: dict, claims_by_id: dict, style, asset_ctx: dict) -> str:
    headline = slide.get('headline', {})
    cid = headline.get('claim_id')
    claim = claims_by_id.get(cid, {})
    headline_html = get_emphasis_html(claim, headline.get('emphasis'), style)
    slide_title = slide.get('slide_title', '')

    header = render_header(asset_ctx.get('assets', []), style, asset_ctx.get('brand_guidelines', {}))
    footer = render_footer(slide.get('footer_claims', []), claims_by_id, style)

    return (
        f'<div data-slide style="width:1024px;height:576px;overflow:hidden;position:relative;'
        f'box-sizing:border-box;background:{_html.escape(style.primary)};">'
        f'{header}'
        f'<div style="display:flex;flex-direction:column;justify-content:center;'
        f'align-items:center;text-align:center;padding:40px 80px 80px;height:calc(100% - 60px);">'
        + (
            f'<div style="font-family:{_html.escape(style.font_hero)};'
            f'font-size:{_html.escape(style.size_h1)};'
            f'font-weight:{style.weight_hero};'
            f'color:{_html.escape(style.text_inverse)};'
            f'margin-bottom:16px;line-height:1.2;">{_html.escape(slide_title)}</div>'
            if slide_title else ''
        )
        + f'<div style="font-family:{_html.escape(style.font_body)};'
        f'font-size:{_html.escape(style.size_body)};'
        f'color:rgba(255,255,255,0.85);line-height:1.5;">'
        f'{headline_html}</div>'
        f'</div>'
        f'{footer}'
        f'</div>'
    )


def render_title_only(slide: dict, claims_by_id: dict, style, asset_ctx: dict) -> str:
    slide_title = slide.get('slide_title', '')
    headline = slide.get('headline', {})
    cid = headline.get('claim_id')
    claim = claims_by_id.get(cid, {})
    body_text = _html.escape(claim.get('text', '')) if claim else ''

    header = render_header(asset_ctx.get('assets', []), style, asset_ctx.get('brand_guidelines', {}))
    footer = render_footer(slide.get('footer_claims', []), claims_by_id, style)

    return (
        f'<div data-slide style="width:1024px;height:576px;overflow:hidden;position:relative;'
        f'box-sizing:border-box;background:{_html.escape(style.bg)};">'
        f'{header}'
        f'<div style="display:flex;flex-direction:column;justify-content:center;'
        f'padding:40px 80px 80px;height:calc(100% - 60px);">'
        + (
            f'<div style="font-family:{_html.escape(style.font_hero)};'
            f'font-size:{_html.escape(style.size_h1)};'
            f'font-weight:{style.weight_hero};'
            f'color:{_html.escape(style.primary)};'
            f'margin-bottom:16px;">{_html.escape(slide_title)}</div>'
            if slide_title else ''
        )
        + (
            f'<div style="font-family:{_html.escape(style.font_body)};'
            f'font-size:{_html.escape(style.size_body)};'
            f'color:{_html.escape(style.text_muted)};line-height:1.5;">{body_text}</div>'
            if body_text else ''
        )
        + f'</div>'
        f'{footer}'
        f'</div>'
    )
