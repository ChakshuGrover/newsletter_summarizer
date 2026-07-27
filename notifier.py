import logging
import requests
import html
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(message, chat_id=None):
    """Sends a message to the configured Telegram chat/channel using HTML parsing."""
    target_chat_id = chat_id if chat_id else TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not target_chat_id:
        logging.warning("Telegram credentials not found. Skipping Telegram notification.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info("Telegram message sent successfully.")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")
        # Log response content if available to debug API errors (like bad HTML tags)
        if 'response' in locals() and response is not None:
            logging.error(f"Telegram API response: {response.text}")

def format_digest_for_telegram(digest_data, date_str):
    """Formats the JSON digest data into a list of Telegram-optimized HTML messages."""
    macro_themes = digest_data.get("macro_themes", [])
    top_stories = digest_data.get("top_stories", [])
    
    messages = []
    
    # Message 1: Header + Macro Themes
    msg1 = f"📅 <b>AI &amp; Tech Daily Digest</b>\n"
    msg1 += f"📅 <i>{date_str}</i>\n\n"
    
    if macro_themes:
        msg1 += f"🔍 <b>Macro Themes Analysis</b>\n\n"
        for theme in macro_themes:
            theme_title = html.escape(theme.get("theme_title", "Unnamed Theme"))
            synthesis = html.escape(theme.get("synthesis", ""))
            
            msg1 += f"• <b>{theme_title}</b>\n"
            msg1 += f"  {synthesis}\n\n"
            
    messages.append(msg1.strip())
    
    # Sort stories by importance rank
    sorted_stories = sorted(top_stories, key=lambda x: x.get('importance_rank', 99))
    
    # Split stories into groups of 5
    chunk_size = 5
    for i in range(0, len(sorted_stories), chunk_size):
        chunk = sorted_stories[i:i + chunk_size]
        part_num = (i // chunk_size) + 1
        total_parts = (len(sorted_stories) + chunk_size - 1) // chunk_size
        
        msg_stories = f"🧠 <b>Top Stories of the Day (Part {part_num}/{total_parts})</b>\n\n"
        
        for idx, story in enumerate(chunk, i + 1):
            title = html.escape(story.get('title', 'Unknown Title'))
            tag = story.get('tag', '')
            news = html.escape(story.get('news', ''))
            impact = html.escape(story.get('impact', ''))
            contrarian_take = html.escape(story.get('contrarian_take', '').strip())
            source_url = story.get('source_url', '')
            
            # Format tag badge
            tag_badge = ""
            if "New Break" in tag:
                tag_badge = "🟢 New Break"
            elif "Developing" in tag:
                tag_badge = "🔵 Developing"
            elif "Contradiction" in tag:
                tag_badge = "🔴 Contradiction"
                
            badge_str = f" [<i>{tag_badge}</i>]" if tag_badge else ""
            
            # Hyperlink title if URL is present
            if source_url:
                title_str = f"<a href=\"{html.escape(source_url)}\"><b>{title}</b></a>"
            else:
                title_str = f"<b>{title}</b>"
                
            msg_stories += f"{idx}. {title_str}{badge_str}\n"
            msg_stories += f"• <b>The News:</b> {news}\n"
            msg_stories += f"• <b>The Impact:</b> {impact}\n"
            
            if contrarian_take:
                msg_stories += f"• <b>Skeptic's Take:</b> <i>{contrarian_take}</i>\n"
                
            msg_stories += "\n"
            
        messages.append(msg_stories.strip())
        
    return messages


def format_weekly_deep_dive_for_telegram(deep_dive_data, date_str):
    """Formats the weekly deep dive markdown essay into a list of Telegram-safe HTML messages."""
    import re
    import html
    
    topic_title = html.escape(deep_dive_data.get("topic_title", "Weekly Strategy Deep Dive"))
    essay_markdown = deep_dive_data.get("essay_markdown", "")
    
    # 1. Parse markdown inline elements to Telegram HTML entities
    text = html.escape(essay_markdown)
    
    # Convert headers (### and ##) to bold lines
    text = re.sub(r'^###\s+(.*)$', r'\n<b>\1</b>\n', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.*)$', r'\n<b>\1</b>\n', text, flags=re.MULTILINE)
    
    # Convert links
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    
    # Convert bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # Convert italics
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    
    # Convert horizontal rules (--- or ***) to clean visual dividers
    text = re.sub(r'^---+$', r'───────────────────', text, flags=re.MULTILINE)
    text = re.sub(r'^\*\*\*+$', r'───────────────────', text, flags=re.MULTILINE)
    
    # Split processed text into paragraph blocks
    paragraphs = re.split(r'\n\n+', text)
    
    messages = []
    
    # Message 1 Header
    current_msg = f"🔔 <b>WEEKLY DEEP DIVE: {topic_title.upper()}</b>\n"
    current_msg += f"📅 <i>{date_str} (Sunday Editorial)</i>\n\n"
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        # Group paragraphs until adding another exceeds the 4000 char threshold
        if len(current_msg) + len(para) + 4 > 4000:
            messages.append(current_msg.strip())
            current_msg = para + "\n\n"
        else:
            current_msg += para + "\n\n"
            
    if current_msg.strip():
        messages.append(current_msg.strip())
        
    return messages


def format_digest_for_whatsapp(digest_data, date_str):
    """Formats the JSON digest data into a list of WhatsApp-optimized Markdown messages."""
    macro_themes = digest_data.get("macro_themes", [])
    top_stories = digest_data.get("top_stories", [])
    
    messages = []
    
    # Message 1: Header + Macro Themes
    msg1 = f"*📅 AI & Tech Daily Digest*\n"
    msg1 += f"_📅 {date_str}_\n\n"
    
    if macro_themes:
        msg1 += f"*🔍 Macro Themes Analysis*\n\n"
        for theme in macro_themes:
            theme_title = theme.get("theme_title", "Unnamed Theme")
            synthesis = theme.get("synthesis", "")
            
            msg1 += f"• *{theme_title}*\n"
            msg1 += f"  {synthesis}\n\n"
            
    messages.append(msg1.strip())
    
    # Sort stories by importance rank
    sorted_stories = sorted(top_stories, key=lambda x: x.get('importance_rank', 99))
    
    # Split stories into groups of 5
    chunk_size = 5
    for i in range(0, len(sorted_stories), chunk_size):
        chunk = sorted_stories[i:i + chunk_size]
        part_num = (i // chunk_size) + 1
        total_parts = (len(sorted_stories) + chunk_size - 1) // chunk_size
        
        msg_stories = f"*🧠 Top Stories of the Day (Part {part_num}/{total_parts})*\n\n"
        
        for idx, story in enumerate(chunk, i + 1):
            title = story.get('title', 'Unknown Title')
            tag = story.get('tag', '')
            news = story.get('news', '')
            impact = story.get('impact', '')
            contrarian_take = story.get('contrarian_take', '').strip()
            source_url = story.get('source_url', '')
            
            # Format tag badge
            tag_badge = ""
            if "New Break" in tag:
                tag_badge = "🟢 New Break"
            elif "Developing" in tag:
                tag_badge = "🔵 Developing"
            elif "Contradiction" in tag:
                tag_badge = "🔴 Contradiction"
                
            badge_str = f" [_{tag_badge}_]" if tag_badge else ""
            
            # WhatsApp doesn't support HTML links, so we place raw link next to title
            link_str = f" ({source_url})" if source_url else ""
            
            msg_stories += f"{idx}. *{title}*{badge_str}{link_str}\n"
            msg_stories += f"• *The News:* {news}\n"
            msg_stories += f"• *The Impact:* {impact}\n"
            
            if contrarian_take:
                msg_stories += f"• *Skeptic's Take:* _{contrarian_take}_\n"
                
            msg_stories += "\n"
            
        messages.append(msg_stories.strip())
        
    return messages

