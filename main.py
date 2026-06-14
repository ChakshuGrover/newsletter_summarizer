import datetime
import logging
import os
import argparse
import sys
import time

from config import (
    setup_logging, LAST_RUN_FILE, EXPECTED_EMAIL, RECIPIENT_EMAILS, ARCHIVE_DIR, REPLY_TO_EMAIL
)
from gmail_manager import (
    get_gmail_service, get_user_email, fetch_newsletter_emails, send_email
)
from ai_summarizer import AISummarizer
from digest_layout import render_themed_stories
from notifier import send_telegram_message

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
        subject = f"AI & Tech Newsletters Digest - {date_range_str}"
        
        logging.info("Sleeping for 60 seconds to reset Token Per Minute (TPM) quota...")
        time.sleep(60)
        
        logging.info("Generating consolidated digest data (commentary, top stories)...")
        digest_data = summarizer.generate_digest_data(summaries, update_history=not args.force, target_date=target_date_str)
        
        commentary = digest_data.get("commentary", "")
        top_stories_data = digest_data.get("top_stories", [])
        
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
      max-width: 1000px;
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
    .pill {{
      display: inline-block;
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      line-height: 1.25;
      border: 2px solid #1E293B;
      border-radius: 4px;
      padding: 4px 10px;
      box-shadow: 3px 3px 0px #1E293B;
      color: #1E293B;
      vertical-align: middle;
    }}
    .pill--macro {{
      background-color: #D35F47;
      color: #ffffff;
    }}
    .pill--new-break {{
      background-color: #A7E4CB;
    }}
    .pill--developing {{
      background-color: #9ACBF7;
    }}
    .pill--contradiction {{
      background-color: #FAAA9C;
    }}
    .pill--capital {{
      background-color: #FDE68A;
      color: #92400E;
    }}
    .pill--products {{
      background-color: #DDD6FE;
      color: #5B21B6;
    }}
    .pill--infrastructure {{
      background-color: #D1FAE5;
      color: #065F46;
    }}
    .pill--industry {{
      background-color: #E2E8F0;
      color: #334155;
    }}
    .section-title {{
      margin-top: 32px;
      margin-bottom: 22px;
    }}
    .section-title:first-of-type {{
      margin-top: 0;
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
    .nugget-card {{
      background-color: #FCF9F3;
      box-shadow: 3px 3px 0px #1E293B;
    }}
    .story-title {{
      margin: 0 0 14px 0;
    }}
    .story-title-text {{
      font-size: 18px;
      font-weight: 800;
      line-height: 1.4;
      margin: 0 0 10px 0;
    }}
    .story-title-badges {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }}
    .story-title-text a {{
      color: #1E293B;
      text-decoration: underline;
      text-decoration-thickness: 2px;
      text-underline-offset: 3px;
      transition: all 0.2s ease;
    }}
    .story-title-text a:hover {{
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
    .tldr-card {{
      background-color: #FFE4E6; /* Soft Light Rose */
      border: 2px solid #1E293B;
      padding: 24px;
      border-radius: 8px;
      box-shadow: 4px 4px 0px #1E293B;
      margin-bottom: 30px;
    }}
    .tldr-list {{
      margin: 0;
      padding-left: 20px;
      font-weight: 700;
      color: #9F1239; /* Rich Rose Dark */
      font-size: 15px;
      line-height: 1.7;
    }}
    .tldr-list li {{
      margin-bottom: 8px;
    }}
    .analogy-bullet {{
      margin-top: 12px !important;
      padding: 8px 12px;
      background-color: #ECFDF5; /* Soft Mint Green */
      border-left: 4px solid #10B981;
      font-size: 13px !important;
      color: #065F46 !important;
      border-radius: 4px;
    }}
    .killer-quote {{
      margin: 16px 0;
      padding: 10px 18px;
      border-left: 4px solid #F59E0B; /* Warm Amber */
      background-color: #FEF3C7; /* Soft Light Amber */
      font-style: italic;
      font-size: 13.5px;
      color: #78350F;
      font-weight: 500;
      border-radius: 4px;
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
    @media (max-width: 600px) {{
      .wrapper {{
        padding: 15px 10px;
      }}
      .header {{
        padding: 30px 15px;
      }}
      .header h1 {{
        font-size: 26px;
      }}
      .content {{
        padding: 20px 15px;
      }}
      .story-card {{
        padding: 16px;
        margin-bottom: 20px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <p>Your AI &amp; Tech Newsletter Brief</p>
        <h1>AI & Tech Digest</h1>
        <p style="font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.12em; color: #1E293B; opacity: 0.85; margin-top: 6px;">{date_range_str}</p>
      </div>
      <div class="content">

"""



        if commentary:
            html_body += f"""
        <div class="section-title pill pill--macro">Macro Landscape Commentary</div>
        <div class="commentary-card">
          <p class="commentary-text">"{commentary}"</p>
        </div>
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
          <div class="sources-title">Sources Scanned ({len(summaries)} newsletters)</div>
          <div class="sources-links">
            {", ".join(sources)}
          </div>
        </div>
        <p style="margin-top: 30px; font-size: 11px; color: #475569;">
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
