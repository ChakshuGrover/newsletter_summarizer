"""Organize and render digest stories into Headlines + themed sections + Nuggets."""

from collections import defaultdict

CATEGORY_SECTIONS = [
    ("products", "🧠 Models & Products"),
    ("infrastructure", "🏗️ Infrastructure & Chips"),
    ("capital", "💸 Business & Capital"),
    ("industry", "🏛️ Industry & Policy"),
]

VALID_CATEGORIES = {c[0] for c in CATEGORY_SECTIONS}
VALID_TIERS = {"headline", "standard", "nugget"}

SECTION_PILL_CLASS = {
    "headlines": "pill--macro",
    "capital": "pill--capital",
    "products": "pill--products",
    "infrastructure": "pill--infrastructure",
    "industry": "pill--industry",
    "nuggets": "pill--macro",
}

# Map legacy 6-category values from older digests or model output
LEGACY_CATEGORY_MAP = {
    "research": "products",
    "release": "products",
    "corporate": "industry",
    "policy_security": "industry",
}

CATEGORY_ALIASES = {
    "business": "capital",
    "funding": "capital",
    "investment": "capital",
    "investments": "capital",
    "deals": "capital",
    "m&a": "capital",
    "ipo": "capital",
    "earnings": "capital",
    "revenue": "capital",
    "guidance": "capital",
    "valuation": "capital",
    "valuations": "capital",
    "research": "products",
    "science": "products",
    "breakthrough": "products",
    "breakthroughs": "products",
    "model": "products",
    "models": "products",
    "release": "products",
    "product": "products",
    "launch": "products",
    "launches": "products",
    "agents": "products",
    "tool": "products",
    "tools": "products",
    "infra": "infrastructure",
    "compute": "infrastructure",
    "chips": "infrastructure",
    "hardware": "infrastructure",
    "corporate": "industry",
    "labor": "industry",
    "layoffs": "industry",
    "reorg": "industry",
    "reorgs": "industry",
    "strategy": "industry",
    "policy": "industry",
    "security": "industry",
    "legal": "industry",
    "regulation": "industry",
    "policy_security": "industry",
}


def normalize_category(raw):
    if not raw:
        return "products"
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if key in VALID_CATEGORIES:
        return key
    if key in LEGACY_CATEGORY_MAP:
        return LEGACY_CATEGORY_MAP[key]
    return CATEGORY_ALIASES.get(key, "products")


def normalize_tier(raw):
    if not raw:
        return "standard"
    key = str(raw).strip().lower()
    if key in VALID_TIERS:
        return key
    if key in ("head", "top", "lead"):
        return "headline"
    if key in ("nuggets", "minor", "small"):
        return "nugget"
    return "standard"


def _importance_key(story):
    rank = story.get("importance_rank")
    try:
        return int(rank)
    except (TypeError, ValueError):
        return 999


def organize_stories(stories):
    """Return [(section_id, section_label, stories), ...] in display order."""
    if not stories:
        return []

    normalized = []
    for story in stories:
        s = dict(story)
        s["tier"] = normalize_tier(s.get("tier"))
        s["category"] = normalize_category(s.get("category"))
        # Force capital category stories out of headlines to keep headlines focused on tech
        if s["category"] == "capital" and s["tier"] == "headline":
            s["tier"] = "standard"
        normalized.append(s)

    headlines = sorted(
        [s for s in normalized if s["tier"] == "headline"],
        key=_importance_key,
    )
    nuggets = sorted(
        [s for s in normalized if s["tier"] == "nugget"],
        key=_importance_key,
    )
    standard = [s for s in normalized if s["tier"] == "standard"]

    # Fallback: if model omitted tiers, treat first 7 as headlines (excluding capital stories)
    if not headlines and not nuggets and standard:
        non_capital_standard = [s for s in standard if s["category"] != "capital"]
        headlines = sorted(non_capital_standard[:7], key=_importance_key)
        headline_titles = {h["title"] for h in headlines}
        standard = [s for s in standard if s["title"] not in headline_titles]

    by_category = defaultdict(list)
    for story in standard:
        by_category[story["category"]].append(story)
    for cat in by_category:
        by_category[cat] = sorted(by_category[cat], key=_importance_key)

    sections = []
    if headlines:
        sections.append(("headlines", "Headlines", headlines))

    for cat_id, label in CATEGORY_SECTIONS:
        if by_category.get(cat_id):
            sections.append((cat_id, label, by_category[cat_id]))

    if nuggets:
        sections.append(("nuggets", "Nuggets", nuggets))

    return sections


def get_category_badge(category):
    labels = dict(CATEGORY_SECTIONS)
    label = labels.get(category, "News")
    pill_class = SECTION_PILL_CLASS.get(category, "pill--products")
    return f'<span class="pill {pill_class}">{label}</span>'


def render_section_title(section_id, label):
    pill_class = SECTION_PILL_CLASS.get(section_id, "pill--macro")
    return f'<div class="section-title pill {pill_class}">{label}</div>\n'


def render_story_card(story, index, get_tag_badge, *, compact=False, show_category=False):
    tag_str = story.get("tag", "")
    badge_html = get_tag_badge(tag_str)
    category = story.get("category", "")
    category_badge = get_category_badge(category) if show_category and category else ""
    source_url = story.get("source_url", "")

    title_text = f"{index}. {story.get('title', 'Unknown')}"
    if source_url:
        title_html = f"<a href='{source_url}'>{title_text}</a>"
    else:
        title_html = title_text

    card_class = "story-card nugget-card" if compact else "story-card"
    padding = "18px" if compact else "24px"
    margin = "20px" if compact else "30px"

    badges = "".join(b for b in (category_badge, badge_html) if b)
    badges_row = (
        f'          <div class="story-title-badges">{badges}</div>\n' if badges else ""
    )

    html = f"""
        <div class="{card_class}" style="padding: {padding}; margin-bottom: {margin};">
          <div class="story-title">
            <div class="story-title-text">{title_html}</div>
{badges_row}          </div>
"""
    html += f"""
          <p class="story-body"><b>The News:</b> {story.get('news', '')}</p>
          <p class="story-body"><b>The Impact:</b> {story.get('impact', '')}</p>
"""
    


    tag_reason = story.get("tag_reason", "")
    if tag_reason:
        html += f'          <div class="story-context">Context: {tag_reason}</div>\n'

    contrarian_take = story.get("contrarian_take", "")
    if contrarian_take and not compact:
        html += (
            f'          <div class="contrarian-bullet">'
            f"<b>Skeptic's Take:</b> {contrarian_take}</div>\n"
        )
    elif contrarian_take and compact:
        html += (
            f'          <p class="story-body" style="font-size: 13px; margin-top: 8px;">'
            f"<b>Skeptic's Take:</b> {contrarian_take}</p>\n"
        )

    html += "        </div>\n"
    return html


def render_themed_stories(stories, get_tag_badge):
    """Build HTML for all story sections. Returns (html, story_count)."""
    sections = organize_stories(stories)
    if not sections:
        return "<p style='color: #64748b; font-size: 14px;'>No top stories found.</p>", 0

    html_parts = []
    counter = 0

    for section_id, section_label, section_stories in sections:
        compact = False
        show_category = section_id == "headlines"
        html_parts.append(render_section_title(section_id, section_label))
        for story in section_stories:
            counter += 1
            html_parts.append(
                render_story_card(
                    story,
                    counter,
                    get_tag_badge,
                    compact=compact,
                    show_category=show_category,
                )
            )

    return "".join(html_parts), counter
