import datetime
import logging
import os
import argparse
import sys

from config import (
    setup_logging, LAST_RUN_FILE, EXPECTED_EMAIL, RECIPIENT_EMAIL
)
from gmail_manager import (
    get_gmail_service, get_user_email, fetch_newsletter_emails, send_email
)
from ai_summarizer import AISummarizer
from notifier import send_telegram_message

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
        # 5. Generate Digest and Send Email
        date_range_str = f"{window_start.strftime('%b %d')} - {window_end.strftime('%b %d, %Y')}"
        subject = f"AI & Tech Newsletters Daily Digest - {date_range_str}"
        top_stories_html = summarizer.get_top_stories(summaries)
        
        html_body = f"<h1>Top AI & Tech Stories</h1>{top_stories_html}<br><hr>"
        for s in summaries:
            html_body += f"<h2>{s['sender']} - {s['subject']}</h2>{s['summary_text']}<br><hr>"

        logging.info(f"Sending digest email to {RECIPIENT_EMAIL}")
        send_email(service, RECIPIENT_EMAIL, subject, html_body)

        # 6. LinkedIn & Telegram
        linkedin_posts = summarizer.generate_linkedin_posts(summaries)
        if linkedin_posts:
            send_telegram_message("📢 *Daily LinkedIn Post Options* (Ready to Copy/Paste):")
            for post in linkedin_posts:
                send_telegram_message(post)

    # 7. Update state
    with open(LAST_RUN_FILE, 'w') as f: f.write(target_date_str)
    logging.info("Main process complete.")

if __name__ == '__main__':
    main()
