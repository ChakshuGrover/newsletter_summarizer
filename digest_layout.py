from collections import defaultdict
import html

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
    
    badge_colors = {
        "products": {"bg": "#F1F5F9", "fg": "#334155"},
        "models-&-products": {"bg": "#F1F5F9", "fg": "#334155"},
        "🧠-models-&-products": {"bg": "#F1F5F9", "fg": "#334155"},
        "infrastructure": {"bg": "#ECFDF5", "fg": "#065F46"},
        "infrastructure-&-chips": {"bg": "#ECFDF5", "fg": "#065F46"},
        "🏗️-infrastructure-&-chips": {"bg": "#ECFDF5", "fg": "#065F46"},
        "industry": {"bg": "#F8FAFC", "fg": "#475569"},
        "industry-&-policy": {"bg": "#F8FAFC", "fg": "#475569"},
        "🏛️-industry-&-policy": {"bg": "#F8FAFC", "fg": "#475569"},
        "capital": {"bg": "#FFFBEB", "fg": "#D97706"},
        "business-&-capital": {"bg": "#FFFBEB", "fg": "#D97706"},
        "💸-business-&-capital": {"bg": "#FFFBEB", "fg": "#D97706"}
    }
    
    cfg = badge_colors.get(category, {"bg": "#F1F5F9", "fg": "#334155"})
    style = f"display: inline-block; font-size: 8px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; line-height: 1.25; border-radius: 4px; padding: 3px 7px; margin-right: 6px; margin-bottom: 4px; vertical-align: middle; background-color: {cfg['bg']}; color: {cfg['fg']};"
    return f'<span class="pill" style="{style}">{label}</span>'


def render_section_title(section_id, label):
    return f'<h2 style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; font-size: 18px; font-weight: 800; color: #0F172A; margin: 35px 0 20px 0; border-bottom: 2px solid #F1F5F9; padding-bottom: 8px; text-align: left; text-transform: uppercase; letter-spacing: 0.05em;">{label}</h2>\n'


def render_story_card(story, index, get_tag_badge, *, compact=False, show_category=False):
    tag_str = story.get("tag", "")
    badge_html = get_tag_badge(tag_str)
    category = story.get("category", "")
    category_badge = get_category_badge(category) if show_category and category else ""
    source_url = story.get("source_url", "")

    title_text = f"{index}. {story.get('title', 'Unknown')}"
    if source_url:
        title_html = f"<a href='{source_url}' style='color: #0F172A; text-decoration: none;'>{title_text} <span style='color: #E5A93B; text-decoration: none; font-weight: normal;'>↗</span></a>"
    else:
        title_html = title_text

    border_style = "none" if compact else "1px solid #F1F5F9"
    padding_bottom = "0" if compact else "25px"
    margin_bottom = "10px" if compact else "25px"
    card_style = f"padding: 0 0 {padding_bottom}; border-bottom: {border_style}; margin-bottom: {margin_bottom}; background-color: #ffffff; text-align: left;"

    badges = "".join(b for b in (category_badge, badge_html) if b)
    badges_row = (
        f'          <div style="margin-bottom: 10px; padding: 0;">{badges}</div>\n' if badges else ""
    )

    html = f"""
        <div style="{card_style}">
          <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 16.5px; font-weight: 700; color: #0F172A; margin: 0 0 8px 0; line-height: 1.4;">{title_html}</div>
{badges_row}
"""
    html += f"""
          <p style="font-size: 14px; line-height: 1.65; color: #475569; margin: 0 0 8px 0;"><b>The News:</b> {story.get('news', '')}</p>
          <p style="font-size: 14px; line-height: 1.65; color: #475569; margin: 0 0 8px 0;"><b>The Impact:</b> {story.get('impact', '')}</p>
"""
    
    tag_reason = story.get("tag_reason", "")
    if tag_reason:
        html += f'          <div style="font-size: 11px; font-weight: 700; color: #4F46E5; margin: 6px 0; text-transform: uppercase; letter-spacing: 0.05em; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">Context: {tag_reason}</div>\n'

    contrarian_take = story.get("contrarian_take", "").strip()
    if contrarian_take and not compact:
        html += (
            f'          <div style="margin-top: 14px; padding: 12px 16px; background-color: #FAF8F0; border-left: 4px solid #E5A93B; font-size: 13.5px; line-height: 1.6; color: #475569; font-style: italic; border-radius: 0 6px 6px 0;">'
            f"<b>Skeptic's Take:</b> {contrarian_take}</div>\n"
        )
    elif contrarian_take and compact:
        html += (
            f'          <p style="font-size: 13px; margin-top: 8px; line-height: 1.65; color: #475569; margin: 0 0 8px 0;">'
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


def markdown_to_html(md_text):
    """Converts a subset of markdown (headers, bold, links, lists, paragraphs) into HTML."""
    import re
    import html
    
    # 1. Normalize spacing around headers to ensure they split into distinct blocks
    lines = md_text.split('\n')
    normalized_lines = []
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith("### ") or line_stripped.startswith("## ") or line_stripped.startswith("# "):
            normalized_lines.append("")
            normalized_lines.append(line_stripped)
            normalized_lines.append("")
        else:
            normalized_lines.append(line)
    normalized_text = "\n".join(normalized_lines)
    normalized_text = re.sub(r'\n\n+', '\n\n', normalized_text).strip()
    
    # 2. Escape HTML tags first to prevent raw injection
    escaped = html.escape(normalized_text)
    
    # 3. Pre-process code blocks wrapped in triple backticks
    code_blocks = []
    def save_code_block(match):
        code_content = match.group(1).strip()
        placeholder = f"__CODE_BLOCK_{len(code_blocks)}__"
        code_blocks.append(
            f'<pre style="font-family: monospace; font-size: 13px; background-color: #F8FAFC; '
            f'border: 1px solid #E2E8F0; padding: 15px; border-radius: 6px; overflow-x: auto; '
            f'margin: 20px 0; color: #334155; line-height: 1.45; white-space: pre; text-align: left;">{code_content}</pre>'
        )
        return f"\n\n{placeholder}\n\n"
        
    escaped = re.sub(r'```(?:[a-zA-Z0-9_-]+)?\n(.*?)\n```', save_code_block, escaped, flags=re.DOTALL)
    escaped = re.sub(r'```(.*?)```', save_code_block, escaped, flags=re.DOTALL)
    
    # 4. Split into blocks
    blocks = re.split(r'\n\n+', escaped)
    html_blocks = []
    
    in_list = False
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
            
        # Re-insert code block placeholders
        if block.startswith("__CODE_BLOCK_") and block.endswith("__"):
            if in_list:
                html_blocks.append("</ul>")
                in_list = False
            idx = int(block[13:-2])
            if idx < len(code_blocks):
                html_blocks.append(code_blocks[idx])
        # Horizontal rules (markdown dividers like --- or ***)
        if block == "---" or block == "***" or re.match(r'^[-*_]{3,}$', block):
            if in_list:
                html_blocks.append("</ul>")
                in_list = False
            html_blocks.append('<hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 30px 0;"/>')
            continue

        # Box drawing character or ASCII boundaries detection for raw diagrams
        box_chars = r'[│─┌┐└┘┬┴┼▼▲◄►┬┴┤├─]'
        is_ascii_diagram = False
        if re.search(box_chars, block):
            is_ascii_diagram = True
        else:
            # Analyze line-by-line for ASCII boundary boxes or structure
            lines = block.split('\n')
            diagram_line_count = 0
            for line in lines:
                line_stripped = line.strip()
                if (line_stripped.startswith('+') and '-' in line_stripped) or \
                   (line_stripped.startswith('|') and len(line_stripped) > 5) or \
                   ('|' in line_stripped and ('--' in line_stripped or '  ' in line_stripped)):
                    diagram_line_count += 1
            if len(lines) > 1 and (diagram_line_count >= 2 or diagram_line_count / len(lines) >= 0.4):
                is_ascii_diagram = True

        if is_ascii_diagram:
            if in_list:
                html_blocks.append("</ul>")
                in_list = False
            html_blocks.append(
                f'<pre style="font-family: monospace; font-size: 13px; background-color: #F8FAFC; '
                f'border: 1px solid #E2E8F0; padding: 15px; border-radius: 6px; overflow-x: auto; '
                f'margin: 20px 0; color: #334155; line-height: 1.45; white-space: pre; text-align: left;">{block}</pre>'
            )
            continue

        # Headers
        if block.startswith("### ") or block.startswith("## ") or block.startswith("# "):
            if in_list:
                html_blocks.append("</ul>")
                in_list = False
            
            if block.startswith("### "):
                level = 3
                header_text = block[4:]
            elif block.startswith("## "):
                level = 2
                header_text = block[3:]
            else:
                level = 1
                header_text = block[2:]
                
            # Process inline markdown inside headers
            header_text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" style="color: #E5A93B; text-decoration: underline;">\1</a>', header_text)
            header_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', header_text)
            header_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', header_text)
            
            if level == 3:
                html_blocks.append(f'<h3 style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; font-size: 18px; font-weight: 800; color: #0F172A; margin: 32px 0 12px 0;">{header_text}</h3>')
            elif level == 2:
                html_blocks.append(f'<h2 style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; font-size: 20px; font-weight: 800; color: #0F172A; margin: 35px 0 15px 0;">{header_text}</h2>')
            else:
                html_blocks.append(f'<h1 style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; font-size: 26px; font-weight: 800; color: #0F172A; margin: 40px 0 20px 0;">{header_text}</h1>')
                
        elif block.startswith("1. ") or block.startswith("2. ") or block.startswith("3. "):
            if in_list:
                html_blocks.append("</ul>")
                in_list = False
            lines = block.split('\n')
            section_html = []
            for line in lines:
                m = re.match(r'^(\d+)\.\s+\*\*(.*?)\*\*:\s*(.*)$', line.strip())
                if m:
                    num, title, body = m.groups()
                    body = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" style="color: #E5A93B; text-decoration: underline;">\1</a>', body)
                    body = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', body)
                    body = re.sub(r'\*(.*?)\*', r'<i>\1</i>', body)
                    section_html.append(
                        f'<p style="font-size: 14.5px; line-height: 1.7; color: #475569; margin: 0 0 20px 0;">'
                        f'<b style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; font-size: 16.5px; color: #0F172A; display: block; margin-bottom: 6px;">{num}. {title}</b>{body}</p>'
                    )
                else:
                    parsed_line = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" style="color: #E5A93B; text-decoration: underline;">\1</a>', line)
                    parsed_line = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', parsed_line)
                    parsed_line = re.sub(r'\*(.*?)\*', r'<i>\1</i>', parsed_line)
                    section_html.append(f'<p style="font-size: 14.5px; line-height: 1.7; color: #475569; margin: 0 0 20px 0;">{parsed_line}</p>')
            html_blocks.append("\n".join(section_html))
            
        elif block.startswith("* ") or block.startswith("- "):
            if not in_list:
                html_blocks.append('<ul style="margin: 0 0 20px 0; padding-left: 20px;">')
                in_list = True
            lines = block.split('\n')
            for line in lines:
                line_text = line.strip()
                if line_text.startswith("* ") or line_text.startswith("- "):
                    item_text = line_text[2:]
                    item_text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" style="color: #E5A93B; text-decoration: underline;">\1</a>', item_text)
                    item_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', item_text)
                    item_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', item_text)
                    html_blocks.append(f'<li style="margin-bottom: 10px; font-size: 14.5px; line-height: 1.7; color: #475569;">{item_text}</li>')
        else:
            if in_list:
                html_blocks.append("</ul>")
                in_list = False
            paragraph_text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" style="color: #E5A93B; text-decoration: underline;">\1</a>', block)
            paragraph_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', paragraph_text)
            paragraph_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', paragraph_text)
            html_blocks.append(f'<p style="font-size: 14.5px; line-height: 1.7; color: #475569; margin: 0 0 20px 0;">{paragraph_text}</p>')
            
    if in_list:
        html_blocks.append("</ul>")
        
    return "\n".join(html_blocks)


def render_weekly_deep_dive(deep_dive_data, date_str):
    """Generates the premium HTML email structure for the Sunday Editorial Weekly Deep Dive."""
    topic_title = html.escape(deep_dive_data.get("topic_title", "Weekly AI Strategy Deep Dive"))
    essay_markdown = deep_dive_data.get("essay_markdown", "No analysis generated.")
    
    essay_html = markdown_to_html(essay_markdown)
    
    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Weekly Deep Dive: {topic_title}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #F3F4F6; /* Premium slate gray-blue canvas */
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #1E293B;
      -webkit-font-smoothing: antialiased;
    }}
    .wrapper {{
      width: 100%;
      background-color: #F3F4F6;
      padding: 50px 0;
    }}
    .container {{
      max-width: 680px;
      margin: 0 auto;
      background-color: #ffffff;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #E2E8F0; /* Clean fall-back border for clients stripping shadow */
      border-top: 5px solid #E5A93B; /* Email-safe solid Ochre Gold top bar */
      box-shadow: 0 20px 40px -15px rgba(99, 102, 241, 0.08), 0 1px 3px rgba(0, 0, 0, 0.02);
    }}
    .header {{
      padding: 40px 30px 20px 30px;
      text-align: left;
      border-bottom: 1px solid #F1F5F9;
    }}
    .header p {{
      margin: 0 0 8px 0;
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.2em;
      color: #8E8870;
    }}
    .header h1 {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 30px;
      font-weight: 800;
      line-height: 1.3;
      letter-spacing: -0.02em;
      color: #0F172A;
    }}
    .content {{
      padding: 20px 30px 40px 30px;
    }}
    .editorial-card {{
      text-align: left;
      font-size: 14.5px;
      line-height: 1.7;
      color: #475569;
    }}
    .editorial-card h3 {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 18px;
      font-weight: 800;
      color: #0F172A;
      margin: 32px 0 12px 0;
    }}
    .editorial-card h3:first-of-type {{
      margin-top: 0;
    }}
    .editorial-card p {{
      margin: 0 0 20px 0;
    }}
    .editorial-card ul, .editorial-card ol {{
      margin: 0 0 20px 0;
      padding-left: 20px;
    }}
    .editorial-card li {{
      margin-bottom: 10px;
    }}
    .editorial-card hr {{
      border: 0;
      border-top: 1px solid #F1F5F9;
      margin: 30px 0;
    }}
    .numbered-story-title {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 16.5px;
      color: #0F172A;
      display: block;
      margin-bottom: 6px;
    }}
    .editorial-card a {{
      color: #6366F1;
      text-decoration: underline;
    }}
    .editorial-card a:hover {{
      color: #EC4899;
    }}
    .footer {{
      background-color: #FAFAFA;
      padding: 35px 50px;
      text-align: left;
      font-size: 11px;
      color: #94A3B8;
      border-top: 1px solid #F1F5F9;
    }}
    .footer p {{
      margin: 4px 0;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <p>Sunday Strategy Editorial &bull; {date_str}</p>
        <h1>{topic_title}</h1>
      </div>
      <div class="content">
        <div class="editorial-card">
          {essay_html}
        </div>
      </div>
      <div class="footer">
        <p>This weekly deep dive is synthesized from top technology stories using Antigravity AI.</p>
        <p>&copy; 2026 AI &amp; Tech Digest. All rights reserved.</p>
      </div>
    </div>
  </div>
</body>
</html>
"""
    return html_body

