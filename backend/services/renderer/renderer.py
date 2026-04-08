"""Deterministic slide renderer: spec + claims → HTML."""
import html as _html
from services.renderer.styles import build_style_context
from services.renderer.layouts import big_stat, stat_row, two_column, three_column_cards, comparison_table, misc

LAYOUT_REGISTRY = {
    'big_stat':           big_stat.render,
    'stat_row':           stat_row.render,
    'two_column':         two_column.render,
    'three_column_cards': three_column_cards.render,
    'comparison_table':   comparison_table.render,
    'data_table':         misc.render_data_table,
    'subgroup_forest':    misc.render_subgroup_forest,
    'hero':               misc.render_hero,
    'title_only':         misc.render_title_only,
}

ERROR_SLIDE = (
    '<div data-slide style="width:1024px;height:576px;overflow:hidden;position:relative;'
    'box-sizing:border-box;background:#fff;display:flex;align-items:center;justify-content:center;">'
    '<p style="font-family:Arial,sans-serif;font-size:14px;color:#cc0000;">'
    'Slide render error: missing required ISI claim in footer.</p>'
    '</div>'
)


def build_asset_context(ds_assets: list, brand_guidelines: dict) -> dict:
    return {
        'assets': ds_assets or [],
        'brand_guidelines': brand_guidelines or {},
    }


def render_deck(
    spec: dict,
    claims_by_id: dict,
    design_tokens: dict,
    brand_guidelines: dict,
    ds_assets: list,
) -> str:
    """
    Render a full deck from a validated slide spec.
    Returns concatenated HTML string of all slides.
    """
    style = build_style_context(design_tokens or {}, brand_guidelines or {})
    asset_ctx = build_asset_context(ds_assets, brand_guidelines)

    # Load font once, before first slide
    font_import = ''
    if style.font_import:
        font_import = f'<style>{_html.escape(style.font_import, quote=False)}</style>'

    slides_html = []
    for slide in spec.get('slides', []):
        # Defense in depth: ISI check
        layout = slide.get('layout', 'two_column')
        layout_fn = LAYOUT_REGISTRY.get(layout, two_column.render)

        # Check for ISI in footer when clinical data present
        footer_claim_ids = [fc.get('claim_id') for fc in slide.get('footer_claims', [])]
        has_isi = any(
            claims_by_id.get(cid, {}).get('claim_type') == 'isi'
            for cid in footer_claim_ids if cid
        )
        # Layouts that require ISI
        clinical_layouts = {'big_stat', 'stat_row', 'two_column', 'three_column_cards',
                            'comparison_table', 'data_table', 'subgroup_forest'}
        if layout in clinical_layouts and not has_isi:
            slides_html.append(ERROR_SLIDE)
            continue

        try:
            slides_html.append(layout_fn(slide, claims_by_id, style, asset_ctx))
        except Exception as e:
            slides_html.append(
                f'<div data-slide style="width:1024px;height:576px;overflow:hidden;'
                f'position:relative;box-sizing:border-box;background:#fff;'
                f'display:flex;align-items:center;justify-content:center;">'
                f'<p style="font-family:Arial,sans-serif;font-size:14px;color:#cc0000;">'
                f'Render error: {_html.escape(str(e))}</p></div>'
            )

    return font_import + ''.join(slides_html)
