import datetime
import logging
import os
import argparse
import sys
import time

from config import (
    setup_logging, LAST_RUN_FILE, EXPECTED_EMAIL, RECIPIENT_EMAILS, ARCHIVE_DIR
)
from gmail_manager import (
    get_gmail_service, get_user_email, fetch_newsletter_emails, send_email
)
from ai_summarizer import AISummarizer
from notifier import send_telegram_message

def get_tag_badge(tag):
    tag = tag.strip().upper()
    if 'NEW BREAK' in tag:
        return '<span style="display: inline-block; padding: 4px 10px; font-size: 10px; font-weight: 800; border-radius: 4px; border: 2px solid #1E293B; background-color: #A7E4CB; color: #1E293B; text-transform: uppercase; letter-spacing: 0.05em; vertical-align: middle; margin-left: 8px;">New Break</span>'
    elif 'DEVELOPING' in tag:
        return '<span style="display: inline-block; padding: 4px 10px; font-size: 10px; font-weight: 800; border-radius: 4px; border: 2px solid #1E293B; background-color: #9ACBF7; color: #1E293B; text-transform: uppercase; letter-spacing: 0.05em; vertical-align: middle; margin-left: 8px;">Developing</span>'
    elif 'CONTRADICTION' in tag:
        return '<span style="display: inline-block; padding: 4px 10px; font-size: 10px; font-weight: 800; border-radius: 4px; border: 2px solid #1E293B; background-color: #FAAA9C; color: #1E293B; text-transform: uppercase; letter-spacing: 0.05em; vertical-align: middle; margin-left: 8px;">Contradiction</span>'
    return ''


def main():
    parser = argparse.ArgumentParser(description='Summarize AI newsletters.')
    parser.add_argument('--days-offset', type=int, default=0, help='Number of days to go back.')
    parser.add_argument('--force', action='store_true', help='Bypass last run check.')
    args = parser.parse_args()

    setup_logging()
    logging.info(f"Starting main process with offset {args.days_offset}.")
    print(f"Heartbeat: Script triggered at {datetime.datetime.now()}")

    # 1. Gmail Setup
    service = get_gmail_service()
    user_email = get_user_email(service)
    if not user_email or user_email.lower() != EXPECTED_EMAIL.lower():
        logging.error(f"Auth error: expected {EXPECTED_EMAIL}, got {user_email}.")
        return

    # 2. Time Window Calculation
    now = datetime.datetime.now().astimezone()
    today_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
    base_target_end = today_6am if now >= today_6am else today_6am - datetime.timedelta(days=1)
    window_end = base_target_end - datetime.timedelta(days=args.days_offset)
    
    # Run only on Wednesday (2) and Saturday (5)
    weekday = window_end.weekday()
    if weekday == 2:
        window_start = window_end - datetime.timedelta(days=4)
    elif weekday == 5:
        window_start = window_end - datetime.timedelta(days=3)
    else:
        if not args.force:
            logging.info(f"Today is not a scheduled run day (Wednesday or Saturday). Exiting.")
            return
        else:
            logging.info(f"Force flag used on non-scheduled run day. Defaulting to 1-day window.")
            window_start = window_end - datetime.timedelta(days=1)

    target_date_str = window_end.isoformat()

    # 3. Guard Logic
    if os.path.exists(LAST_RUN_FILE) and args.days_offset == 0 and not args.force:
        with open(LAST_RUN_FILE, 'r') as f:
            if f.read().strip() == target_date_str:
                logging.info(f"Already processed window ending {target_date_str}. Exiting.")
                return

    # 4. Fetch and Process
    emails = fetch_newsletter_emails(service, window_start, window_end)
    if not emails:
        logging.info("No new emails. Marking window as processed.")
        with open(LAST_RUN_FILE, 'w') as f: f.write(target_date_str)
        return

    summarizer = AISummarizer()
    summaries = summarizer.summarize_emails(emails)

    if summaries:
        # 5. Generate Insights and Digest
        date_range_str = f"{window_start.strftime('%b %d')} - {window_end.strftime('%b %d, %Y')}"
        subject = f"AI & Tech Newsletters Daily Digest - {date_range_str}"
        
        logging.info("Sleeping for 60 seconds to reset Token Per Minute (TPM) quota...")
        time.sleep(60)
        
        logging.info("Generating macro landscape commentary...")
        commentary = summarizer.generate_landscape_commentary(summaries)
        
        logging.info("Sleeping for 15 seconds to respect rate limits...")
        time.sleep(15)
        
        logging.info("Extracting top stories and generating contrarian take...")
        top_stories_data = summarizer.get_top_stories(summaries, update_history=not args.force)
        
        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@800&display=swap');
    body {{
      margin: 0;
      padding: 0;
      background-color: #F5F4F0;
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #1E293B;
      -webkit-font-smoothing: antialiased;
    }}
    .wrapper {{
      width: 100%;
      background-color: #F5F4F0;
      padding: 40px 0;
    }}
    .container {{
      max-width: 650px;
      margin: 0 auto;
      background-color: #ffffff;
      border-radius: 12px;
      overflow: hidden;
      border: 2px solid #1E293B;
      box-shadow: 6px 6px 0px #1E293B;
    }}
    .header {{
      background-color: #E5A93B; /* Refined Ochre Gold */
      padding: 45px 30px;
      text-align: center;
      border-bottom: 2px solid #1E293B;
    }}
    .header h1 {{
      margin: 0 0 10px 0;
      font-family: "Outfit", "Inter", sans-serif;
      font-size: 34px;
      font-weight: 800;
      letter-spacing: -0.03em;
      text-transform: uppercase;
      color: #1E293B;
    }}
    .header p {{
      margin: 0;
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #1E293B;
      opacity: 0.85;
    }}
    .content {{
      padding: 35px 30px;
    }}
    .section-title {{
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      background-color: #D35F47; /* Elegant Muted Terracotta */
      color: #ffffff;
      border: 2px solid #1E293B;
      padding: 6px 14px;
      display: inline-block;
      box-shadow: 3px 3px 0px #1E293B;
      margin-bottom: 25px;
      border-radius: 4px;
    }}
    .commentary-card {{
      background-color: #FCF9F3; /* Light Warm Sand */
      border: 2px solid #1E293B;
      padding: 24px;
      border-radius: 8px;
      box-shadow: 4px 4px 0px #1E293B;
      margin-bottom: 40px;
    }}
    .commentary-text {{
      margin: 0;
      font-size: 15px;
      line-height: 1.65;
      font-weight: 600;
      color: #334155;
    }}
    .story-card {{
      padding: 24px;
      border: 2px solid #1E293B;
      border-radius: 8px;
      margin-bottom: 30px;
      box-shadow: 4px 4px 0px #1E293B;
      background-color: #ffffff;
    }}
    .story-title {{
      font-size: 18px;
      font-weight: 800;
      line-height: 1.4;
      margin: 0 0 14px 0;
    }}
    .story-title a {{
      color: #1E293B;
      text-decoration: underline;
      text-decoration-thickness: 2px;
      text-underline-offset: 3px;
      transition: all 0.2s ease;
    }}
    .story-title a:hover {{
      color: #D35F47;
      text-decoration-color: #D35F47;
    }}
    .story-body {{
      font-size: 14px;
      line-height: 1.6;
      color: #334155;
      margin: 0 0 10px 0;
    }}
    .story-context {{
      font-size: 11px;
      font-weight: 800;
      color: #4F46E5;
      margin: 8px 0;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .contrarian-bullet {{
      margin-top: 16px;
      padding: 14px 18px;
      background-color: #FFEBD3; /* Elegant Warm Apricot Cream */
      border: 2px solid #1E293B;
      box-shadow: 3px 3px 0px #1E293B;
      border-radius: 6px;
      font-size: 13.5px;
      line-height: 1.55;
      color: #334155;
      font-weight: 600;
    }}
    .story-list {{
      margin: 0;
      padding-left: 20px;
    }}
    .story-list li {{
      margin-bottom: 8px;
      font-size: 14px;
      line-height: 1.55;
      color: #334155;
    }}
    .sources-section {{
      text-align: left;
      margin-bottom: 30px;
      padding: 20px;
      background-color: #ffffff;
      border: 2px solid #1E293B;
      box-shadow: 3px 3px 0px #1E293B;
      border-radius: 6px;
    }}
    .sources-title {{
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #1E293B;
      margin: 0 0 10px 0;
    }}
    .sources-links {{
      font-size: 12px;
      line-height: 1.6;
      font-weight: 600;
      color: #475569;
    }}
    .sources-links a {{
      color: #1E293B;
      text-decoration: underline;
    }}
    .sources-links a:hover {{
      color: #D35F47;
    }}
    .footer {{
      background-color: #EFEBE4;
      padding: 40px 30px;
      text-align: center;
      border-top: 2px solid #1E293B;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <p>Your Daily Tech Intelligence</p>
        <h1>AI & Tech Digest</h1>
        <p style="font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.12em; color: #1E293B; opacity: 0.85; margin-top: 6px;">{date_range_str}</p>
      </div>
      <div class="content">

"""

        if commentary:
            html_body += f"""
        <div class="section-title">Macro Landscape Commentary</div>
        <div class="commentary-card">
          <p class="commentary-text">"{commentary}"</p>
        </div>
"""
        
        html_body += f'<div class="section-title">Top AI & Tech Stories</div>'
        if not top_stories_data:
            html_body += "<p style='color: #64748b; font-size: 14px;'>No top stories found.</p>"
        else:
            for i, story in enumerate(top_stories_data):
                tag_str = story.get('tag', '')
                badge_html = get_tag_badge(tag_str)
                source_url = story.get('source_url', '')
                
                title_text = f"{i+1}. {story.get('title', 'Unknown')}"
                if source_url:
                    title_html = f"<a href='{source_url}'>{title_text}</a>"
                else:
                    title_html = title_text
                
                html_body += f"""
        <div class="story-card">
          <div class="story-title">
            {title_html}
            {badge_html}
          </div>
"""
                
                tag_reason = story.get('tag_reason', '')
                contrarian_take = story.get('contrarian_take', '')
                
                html_body += f"""
          <p class="story-body"><b>The News:</b> {story.get('news', '')}</p>
          <p class="story-body"><b>The Impact:</b> {story.get('impact', '')}</p>
"""
                if tag_reason:
                    html_body += f'          <div class="story-context">Context: {tag_reason}</div>'
                if contrarian_take:
                    html_body += f'          <div class="contrarian-bullet"><b>Skeptic\'s Take:</b> {contrarian_take}</div>'
                
                html_body += '        </div>'

            
        # Sources Scanned
        sources = []
        for s in summaries:
            source_info = f"{s['sender']} ({s['subject']})"
            if s.get('link'):
                source_info = f"<a href='{s['link']}'>{source_info}</a>"
            sources.append(source_info)
            
        html_body += f"""
      </div> <!-- /content -->
      <div class="footer">
        <div class="sources-section">
          <div class="sources-title">Sources Scanned ({len(summaries)} newsletters)</div>
          <div class="sources-links">
            {", ".join(sources)}
          </div>
        </div>
        <p style="margin-top: 30px; font-size: 11px; color: #475569;">
          You are receiving this because you subscribed to the AI & Tech Newsletters Daily Digest.<br>
          ChakshuGrover/newsletter_summarizer &copy; 2026. All rights reserved.
        </p>
      </div>
    </div> <!-- /container -->
  </div> <!-- /wrapper -->
</body>
</html>
"""

        # Archive the email
        try:
            if not os.path.exists(ARCHIVE_DIR):
                os.makedirs(ARCHIVE_DIR)
            
            archive_filename = f"digest_{window_end.strftime('%Y-%m-%d')}.html"
            archive_path = os.path.join(ARCHIVE_DIR, archive_filename)
            
            with open(archive_path, 'w') as f:
                f.write(f"<!-- Subject: {subject} -->\n")
                f.write(html_body)
            logging.info(f"Email archived to {archive_path}")
        except Exception as e:
            logging.error(f"Failed to archive email: {e}")

        # Filter recipients for forced runs
        active_recipients = RECIPIENT_EMAILS
        if args.force:
            active_recipients = ["chakshu.grover8@gmail.com"]
            logging.info(f"Forced run detected. Overriding recipients to: {active_recipients}")

        to_list = ", ".join(active_recipients)
        logging.info(f"Sending digest email to {to_list}")
        send_email(service, to_list, subject, html_body)

        # 6. LinkedIn & Telegram (Disabled for now)
        # linkedin_posts = summarizer.generate_linkedin_posts(summaries)
        # if linkedin_posts:
        #     header = "📢 *Daily LinkedIn Post Options* (Ready to Copy/Paste):"
        #     if args.force:
        #         header = "🧪 *[TEST RUN] LinkedIn Post Options*:"

        #     # send_telegram_message(header)
        #     # for post in linkedin_posts:
        #     #     send_telegram_message(post)
        #     logging.info("Telegram notifications are currently disabled.")

    # 7. Update state
    with open(LAST_RUN_FILE, 'w') as f: f.write(target_date_str)
    logging.info("Main process complete.")

if __name__ == '__main__':
    main()
