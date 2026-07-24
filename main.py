import datetime
import logging
import os
import argparse
import sys
import time
import html
import json

from config import (
    setup_logging, LAST_RUN_FILE, EXPECTED_EMAIL, RECIPIENT_EMAILS, ARCHIVE_DIR, REPLY_TO_EMAIL
)
from gmail_manager import (
    get_gmail_service, get_user_email, fetch_newsletter_emails, send_email
)
from ai_summarizer import AISummarizer
from digest_layout import render_themed_stories, render_weekly_deep_dive
from notifier import send_telegram_message, format_digest_for_telegram, format_weekly_deep_dive_for_telegram

def get_tag_badge(tag):
    tag = tag.strip().upper()
    if 'NEW BREAK' in tag:
        return '<span class="pill pill--new-break">New Break</span>'
    if 'DEVELOPING' in tag:
        return '<span class="pill pill--developing">Developing</span>'
    if 'CONTRADICTION' in tag:
        return '<span class="pill pill--contradiction">Contradiction</span>'
    return ''


def main():
    parser = argparse.ArgumentParser(description='Summarize AI newsletters.')
    parser.add_argument('--days-offset', type=int, default=0, help='Number of days to go back.')
    parser.add_argument('--force', action='store_true', help='Bypass last run check.')
    parser.add_argument('--weekly', action='store_true', help='Generate a weekly deep dive strategy editorial.')
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
    
    # Sunday detection: automatically trigger Weekly Deep Dive
    is_sunday = (window_end.weekday() == 6)
    if is_sunday and not args.weekly:
        logging.info("Sunday detected. Automatically switching to Weekly Deep Dive mode.")
        args.weekly = True
        
    # Weekly Deep Dive Branch
    if args.weekly:
        logging.info("Weekly deep-dive mode active. Retrieving last 7 days of processed history...")
        
        # Calculate date range for past 7 days (relative to window_end)
        end_date = window_end.date()
        start_date = end_date - datetime.timedelta(days=7)
        date_range_str = f"{start_date.strftime('%B %d, %Y')} - {end_date.strftime('%B %d, %Y')}"
        logging.info(f"Targeting stories from {start_date} to {end_date}")
        
        # Load history file
        history_path = "top_stories_history.json"
        if not os.path.exists(history_path):
            logging.error(f"History file {history_path} not found. Cannot run weekly deep dive.")
            return
            
        try:
            with open(history_path, 'r') as f:
                history_stories = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load history stories: {e}")
            return
            
        # Filter stories in the 7-day range
        weekly_stories = []
        for story in history_stories:
            story_date_str = story.get("date", "")
            if not story_date_str:
                continue
            try:
                # Date format: YYYY-MM-DD
                story_date = datetime.datetime.strptime(story_date_str[:10], "%Y-%m-%d").date()
                if start_date <= story_date <= end_date:
                    weekly_stories.append(story)
            except Exception as e:
                logging.warning(f"Error parsing story date '{story_date_str}': {e}")
                
        if not weekly_stories:
            logging.warning("No stories found in top_stories_history.json for the last 7 days. Exiting.")
            return
            
        logging.info(f"Found {len(weekly_stories)} stories for synthesis.")
        
        # 3. AISummarizer generation
        summarizer = AISummarizer()
        deep_dive_data = summarizer.generate_weekly_deep_dive(weekly_stories)
        
        # 4. HTML Layout Rendering
        weekly_html = render_weekly_deep_dive(deep_dive_data, date_range_str)
        
        # 5. Archive to file
        weekly_filename = f"weekly_deep_dive_{end_date.strftime('%Y-%m-%d')}.html"
        weekly_archive_path = os.path.join(ARCHIVE_DIR, weekly_filename)
        try:
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
            with open(weekly_archive_path, 'w') as f:
                f.write(weekly_html)
            logging.info(f"Weekly deep dive archived to {weekly_archive_path}")
        except Exception as e:
            logging.error(f"Failed to archive weekly deep dive: {e}")
            
        # 6. Email Dispatch
        active_recipients = RECIPIENT_EMAILS
        if args.force:
            active_recipients = ["chakshu.grover8@gmail.com"]
            logging.info(f"Forced run: overriding email recipients to: {active_recipients}")
            
        bcc_list = ", ".join(active_recipients)
        subject = f"Weekly Deep Dive: {deep_dive_data.get('topic_title')}"
        
        logging.info(f"Sending weekly deep dive email. To: {EXPECTED_EMAIL}, BCC: {bcc_list}")
        send_email(
            service=service,
            to=EXPECTED_EMAIL,
            subject=subject,
            html_body=weekly_html,
            bcc=bcc_list,
            reply_to=REPLY_TO_EMAIL
        )
        
        # 7. Telegram Dispatch
        try:
            logging.info("Formatting and sending Telegram weekly deep-dive messages...")
            telegram_messages = format_weekly_deep_dive_for_telegram(deep_dive_data, date_range_str)
            
            if args.force:
                from config import TELEGRAM_TEST_CHAT_ID
                if TELEGRAM_TEST_CHAT_ID:
                    logging.info(f"Forced run detected. Redirecting Telegram message to test chat: {TELEGRAM_TEST_CHAT_ID}")
                    for msg in telegram_messages:
                        send_telegram_message(msg, chat_id=TELEGRAM_TEST_CHAT_ID)
                        time.sleep(1)
                else:
                    logging.warning("Forced run detected but TELEGRAM_TEST_CHAT_ID is not configured. Skipping Telegram dispatch to prevent channel spam.")
            else:
                for msg in telegram_messages:
                    send_telegram_message(msg)
                    time.sleep(1) # Delay between chunks to preserve ordering
        except Exception as e:
            logging.error(f"Failed to format/send weekly Telegram: {e}")
            
        logging.info("Weekly deep-dive process complete.")
        return
    
    # Daily run: 2 days on Monday to capture the weekend, 1 day otherwise
    is_monday = (window_end.weekday() == 0)
    lookback_days = 2 if is_monday else 1
    window_start = window_end - datetime.timedelta(days=lookback_days)

    target_date_str = window_end.isoformat()

    # 3. Guard Logic
    if os.path.exists(LAST_RUN_FILE) and args.days_offset == 0 and not args.force:
        with open(LAST_RUN_FILE, 'r') as f:
            if f.read().strip() == target_date_str:
                logging.info(f"Already processed window ending {target_date_str}. Exiting.")
                return

    # 4. Fetch and Process
    emails = fetch_newsletter_emails(service, window_start, window_end)
    
    # Fallback: if volume is dry (< 6 emails), expand search window to 3 days dynamically
    if len(emails) < 6:
        logging.info(f"Low daily email count ({len(emails)}) in {lookback_days}-day window. Expanding lookback to 3 days.")
        window_start = window_end - datetime.timedelta(days=3)
        emails = fetch_newsletter_emails(service, window_start, window_end)
        
    if not emails:
        logging.info("No new emails. Marking window as processed.")
        with open(LAST_RUN_FILE, 'w') as f: f.write(target_date_str)
        return

    summarizer = AISummarizer()
    summaries = summarizer.summarize_emails(emails)

    if summaries:
        # 5. Generate Insights and Digest
        if (window_end - window_start).days <= 1:
            date_range_str = window_end.strftime('%B %d, %Y')
        else:
            date_range_str = f"{window_start.strftime('%b %d')} - {window_end.strftime('%b %d, %Y')}"
        subject = f"AI & Tech Newsletters Digest - {date_range_str}"
        
        logging.info("Sleeping for 60 seconds to reset Token Per Minute (TPM) quota...")
        time.sleep(60)
        
        logging.info("Generating consolidated digest data (commentary, top stories)...")
        digest_data = summarizer.generate_digest_data(summaries, update_history=not args.force, target_date=target_date_str)
        
        commentary_themes = digest_data.get("macro_themes", [])
        top_stories_data = digest_data.get("top_stories", [])
        
        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
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
      font-size: 32px;
      font-weight: 800;
      line-height: 1.25;
      letter-spacing: -0.02em;
      color: #0F172A;
    }}
    .content {{
      padding: 20px 30px 40px 30px;
    }}
    .section-title {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 18px;
      font-weight: 800;
      color: #0F172A;
      margin: 35px 0 20px 0;
      border-bottom: 2px solid #F1F5F9;
      padding-bottom: 8px;
      text-align: left;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .section-title:first-of-type {{
      margin-top: 0;
    }}
    .commentary-card {{
      background-color: #F8FAFC;
      border: 1px solid #E2E8F0;
      padding: 24px;
      border-radius: 8px;
      margin-bottom: 30px;
    }}
    .commentary-theme {{
      margin-bottom: 20px;
    }}
    .commentary-theme:last-child {{
      margin-bottom: 0;
    }}
    .commentary-theme h3 {{
      margin: 0 0 6px 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 15px;
      font-weight: 700;
      color: #0F172A;
    }}
    .commentary-theme p {{
      margin: 0;
      font-size: 13.5px;
      line-height: 1.6;
      color: #475569;
    }}
    .story-card {{
      padding: 0 0 25px 0;
      border-bottom: 1px solid #F1F5F9;
      margin-bottom: 25px;
      background-color: #ffffff;
      text-align: left;
    }}
    .story-card:last-child {{
      border-bottom: none;
      margin-bottom: 10px;
      padding-bottom: 0;
    }}
    .nugget-card {{
      padding: 0 0 20px 0;
      border-bottom: 1px solid #F1F5F9;
      margin-bottom: 20px;
      background-color: #ffffff;
    }}
    .nugget-card:last-child {{
      border-bottom: none;
      margin-bottom: 5px;
      padding-bottom: 0;
    }}
    .skeptic-take-compact {{
      font-size: 13px;
      margin-top: 8px;
    }}
    .story-title-text {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 16.5px;
      font-weight: 700;
      color: #0F172A;
      margin: 0 0 8px 0;
      line-height: 1.4;
    }}
    .story-title-text a {{
      color: #0F172A;
      text-decoration: none;
    }}
    .story-title-text a:hover {{
      color: #E5A93B;
      text-decoration: underline;
    }}
    .story-title-badges {{
      margin-bottom: 10px;
      padding: 0;
    }}
    .pill {{
      display: inline-block;
      font-size: 8px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      line-height: 1.25;
      border-radius: 4px;
      padding: 3px 7px;
      margin-right: 6px; /* Universal spacing fallback for flexbox gaps */
      margin-bottom: 4px;
      vertical-align: middle;
    }}
    .pill--new-break {{
      background-color: #EEF2FF;
      color: #4F46E5;
    }}
    .pill--developing {{
      background-color: #F0FDF4;
      color: #16A34A;
    }}
    .pill--contradiction {{
      background-color: #FFF5F5;
      color: #EF4444;
    }}
    .pill--products, .pill--models-&-products, .pill--🧠-models-&-products {{
      background-color: #F1F5F9;
      color: #334155;
    }}
    .pill--infrastructure, .pill--infrastructure-&-chips, .pill--🏗️-infrastructure-&-chips {{
      background-color: #ECFDF5;
      color: #065F46;
    }}
    .pill--industry, .pill--industry-&-policy, .pill--🏛️-industry-&-policy {{
      background-color: #F8FAFC;
      color: #475569;
    }}
    .pill--capital, .pill--business-&-capital, .pill--💸-business-&-capital {{
      background-color: #FFFBEB;
      color: #D97706;
    }}
    .story-body {{
      font-size: 14px;
      line-height: 1.65;
      color: #475569;
      margin: 0 0 8px 0;
    }}
    .story-context {{
      font-size: 11px;
      font-weight: 700;
      color: #4F46E5;
      margin: 6px 0;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .contrarian-bullet {{
      margin-top: 14px;
      padding: 12px 16px;
      background: linear-gradient(135deg, #FAF8F0 0%, #FAF6E8 100%);
      border-left: 4px solid #E5A93B;
      font-size: 13.5px;
      line-height: 1.6;
      color: #475569;
      font-style: italic;
      border-radius: 0 6px 6px 0;
    }}
    .sources-section {{
      text-align: left;
      margin-bottom: 25px;
      padding: 20px;
      background-color: #F8FAFC;
      border: 1px solid #E2E8F0;
      border-radius: 8px;
    }}
    .sources-title {{
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #64748B;
      margin: 0 0 10px 0;
    }}
    .sources-links {{
      font-size: 12px;
      line-height: 1.6;
      font-weight: 600;
      color: #64748B;
    }}
    .sources-links a {{
      color: #E5A93B;
      text-decoration: underline;
    }}
    .sources-links a:hover {{
      color: #EC4899;
    }}
    .footer {{
      background-color: #FAFAFA;
      padding: 30px 30px;
      text-align: left;
      font-size: 11px;
      color: #94A3B8;
      border-top: 1px solid #F1F5F9;
    }}
    .footer p {{
      margin: 4px 0;
    }}
    @media (max-width: 600px) {{
      .wrapper {{
        padding: 15px 10px;
      }}
      .header {{
        padding: 30px 20px;
      }}
      .header h1 {{
        font-size: 26px;
      }}
      .content {{
        padding: 20px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <p>Daily Briefing &bull; {date_range_str}</p>
        <h1>AI &amp; Tech Digest</h1>
      </div>
      <div class="content">
"""

        if commentary_themes:
            html_body += """
        <h2 class="section-title">Macro Themes Analysis</h2>
        <div class="commentary-card">
"""
            for theme in commentary_themes:
                theme_title = html.escape(theme.get("theme_title", "Unnamed Theme"))
                synthesis = html.escape(theme.get("synthesis", ""))
                
                html_body += f"""
          <div class="commentary-theme">
            <h3>{theme_title}</h3>
            <p>{synthesis}</p>
          </div>
"""
            html_body += """        </div>
"""
        
        stories_html, _ = render_themed_stories(top_stories_data, get_tag_badge)
        html_body += stories_html

            
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
          <div class="sources-title">Sources Scanned</div>
          <div class="sources-links">
            {", ".join(sources)}
          </div>
        </div>
        <p style="margin-top: 30px; font-size: 11px; color: #94A3B8;">
          You are receiving this because you subscribed to the AI &amp; Tech Newsletters Digest.<br>
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
            
            date_str = window_end.strftime('%Y-%m-%d')
            base_filename = f"digest_{date_str}.html"
            base_path = os.path.join(ARCHIVE_DIR, base_filename)
            
            if not os.path.exists(base_path):
                # First run of the day (regardless of force or scheduled)
                archive_filename = base_filename
                archive_path = base_path
            else:
                # File already exists, version it sequentially to prevent overwriting
                idx = 1
                suffix = "f" if args.force else "v"
                while True:
                    archive_filename = f"digest_{date_str}_{suffix}{idx}.html"
                    archive_path = os.path.join(ARCHIVE_DIR, archive_filename)
                    if not os.path.exists(archive_path):
                        break
                    idx += 1
            
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

        bcc_list = ", ".join(active_recipients)
        logging.info(f"Sending digest email. To: {user_email}, BCC: {bcc_list}, Reply-To: {REPLY_TO_EMAIL}")
        send_email(
            service=service,
            to=user_email,
            subject=subject,
            html_body=html_body,
            bcc=bcc_list,
            reply_to=REPLY_TO_EMAIL
        )
        
        # 6. Telegram Channel Dispatch
        try:
            logging.info("Formatting and sending Telegram channel messages...")
            telegram_messages = format_digest_for_telegram(digest_data, date_range_str)
            
            if args.force:
                from config import TELEGRAM_TEST_CHAT_ID
                if TELEGRAM_TEST_CHAT_ID:
                    logging.info(f"Forced run detected. Redirecting Telegram message to test chat: {TELEGRAM_TEST_CHAT_ID}")
                    for msg in telegram_messages:
                        send_telegram_message(msg, chat_id=TELEGRAM_TEST_CHAT_ID)
                        time.sleep(1)
                else:
                    logging.warning("Forced run detected but TELEGRAM_TEST_CHAT_ID is not configured. Skipping Telegram dispatch to prevent channel spam.")
            else:
                for msg in telegram_messages:
                    send_telegram_message(msg)
                    time.sleep(1) # Small delay to preserve message order and respect API rate limits
        except Exception as e:
            logging.error(f"Failed to format or send Telegram channel messages: {e}")

    # 7. Update state
    with open(LAST_RUN_FILE, 'w') as f: f.write(target_date_str)
    logging.info("Main process complete.")

if __name__ == '__main__':
    main()
