import datetime
import logging
import os
import argparse
import sys

from config import (
    setup_logging, LAST_RUN_FILE, EXPECTED_EMAIL, RECIPIENT_EMAILS
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
        
        logging.info("Generating macro landscape commentary...")
        commentary = summarizer.generate_landscape_commentary(summaries)
        
        logging.info("Extracting top stories and generating contrarian take...")
        top_stories_data = summarizer.get_top_stories(summaries, update_history=not args.force)
        
        html_body = ""
        if commentary:
            html_body += f"<h2>Macro Landscape Commentary</h2>"
            html_body += f"<blockquote style='font-style: italic; color: #555; padding-left: 15px; border-left: 4px solid #ccc;'>{commentary}</blockquote><hr>"
        
        html_body += f"<h1>Top AI & Tech Stories</h1>"
        if not top_stories_data:
            html_body += "<p>No top stories found.</p><hr>"
        else:
            for i, story in enumerate(top_stories_data):
                tag_str = story.get('tag', '')
                html_body += f"<h3>{i+1}. {story.get('title', 'Unknown')} {tag_str}</h3>"
                
                # Contrarian Take for top 5 stories
                tag_reason = story.get('tag_reason', '')
                if i < 5:
                    contrarian_take = summarizer.generate_contrarian_take(story)
                    html_body += f"<p><b>The News:</b> {story.get('news', '')}</p>"
                    html_body += f"<p><b>The Impact:</b> {story.get('impact', '')}</p>"
                    if tag_reason:
                        html_body += f"<p style='color: #2196F3; font-style: italic;'><b>Context:</b> {tag_reason}</p>"
                    if contrarian_take:
                        html_body += f"<div style='background-color: #ffebee; padding: 10px; border-left: 4px solid #f44336; margin-top: 10px; margin-bottom: 10px; border-radius: 4px;'><b>The Contrarian Take:</b> {contrarian_take}</div>"
                else:
                    html_body += f"<ul><li><b>The News:</b> {story.get('news', '')}</li>"
                    html_body += f"<li><b>The Impact:</b> {story.get('impact', '')}</li>"
                    if tag_reason:
                        html_body += f"<li><span style='color: #2196F3; font-style: italic;'><b>Context:</b> {tag_reason}</span></li>"
                    html_body += "</ul>"
            html_body += "<hr>"
            
        # Sources Scanned (Replacing redundant individual summaries)
        html_body += "<p style='color: #777; font-size: 0.9em;'><b>Sources Scanned:</b> "
        sources = []
        for s in summaries:
            source_info = f"{s['sender']} ({s['subject']})"
            sources.append(source_info)
        html_body += ", ".join(sources)
        html_body += "</p>"

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
