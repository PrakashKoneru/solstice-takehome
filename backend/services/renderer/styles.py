"""Convert design tokens + brand guidelines into a StyleContext used by all layout renderers."""


class StyleContext:
    def __init__(self, design_tokens: dict, brand_guidelines: dict):
        colors = design_tokens.get('colors', {})
        palette = colors.get('palette', {})
        text_colors = colors.get('text', {})
        fill = colors.get('fill', {})
        border = colors.get('border', {})

        self.primary   = palette.get('primary') or '#7c3aed'
        self.secondary = palette.get('secondary') or '#002855'
        self.bg        = fill.get('default') or '#ffffff'
        self.bg_subtle = fill.get('subtle') or '#f8f9fa'
        self.border    = border.get('default') or '#e5e7eb'
        self.text      = text_colors.get('default') or '#1a1a2e'
        self.text_muted = text_colors.get('muted') or '#6b7280'
        self.text_inverse = text_colors.get('inverse') or '#ffffff'

        fonts = design_tokens.get('fonts', {})
        sizes = design_tokens.get('fontSizes', {})
        weights = design_tokens.get('fontWeights', {})

        self.font_hero   = fonts.get('hero') or brand_guidelines.get('primaryFont') or 'Arial, sans-serif'
        self.font_body   = fonts.get('body') or brand_guidelines.get('secondaryFont') or 'Arial, sans-serif'
        self.font_caption = fonts.get('caption') or self.font_body

        self.size_hero    = sizes.get('hero') or '64px'
        self.size_h1      = sizes.get('h1') or '28px'
        self.size_h2      = sizes.get('h2') or '20px'
        self.size_body    = sizes.get('body') or '13px'
        self.size_caption = sizes.get('caption') or '10px'

        self.weight_hero = weights.get('hero') or '800'
        self.weight_h1   = weights.get('h1') or '700'
        self.weight_body = weights.get('body') or '400'

        spacing = design_tokens.get('spacing', {})
        self.spacing_sm = spacing.get('sm') or '8px'
        self.spacing_md = spacing.get('md') or '16px'
        self.spacing_lg = spacing.get('lg') or '24px'

        radius = design_tokens.get('borderRadius', {})
        self.radius_sm = radius.get('sm') or '4px'
        self.radius_md = radius.get('md') or '8px'

        self.font_import = (
            f"@import url('https://fonts.googleapis.com/css2?family="
            f"{self.font_hero.split(',')[0].strip().replace(' ', '+')}:wght@400;600;700;800&display=swap');"
            if self.font_hero and 'Arial' not in self.font_hero else ''
        )


def build_style_context(design_tokens: dict, brand_guidelines: dict) -> StyleContext:
    return StyleContext(design_tokens or {}, brand_guidelines or {})
