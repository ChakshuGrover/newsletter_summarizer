import logging
import time
import json
import os
import datetime
from collections import deque
import google.generativeai as genai
from bs4 import BeautifulSoup
from config import API_KEYS, HISTORY_FILE

class RateLimiter:
    def __init__(self, rate_limit_per_minute):
        self.rate_limit_per_minute = rate_limit_per_minute
        self.requests = deque()

    def wait_for_permission(self):
        current_time = time.time()
        while self.requests and self.requests[0] <= current_time - 60:
            self.requests.popleft()
        if len(self.requests) >= self.rate_limit_per_minute:
            time_to_wait = 60 - (current_time - self.requests[0])
            if time_to_wait > 0:
                logging.info(f"Rate limit reached. Waiting for {time_to_wait:.2f} seconds.")
                time.sleep(time_to_wait)
                current_time = time.time()
        self.requests.append(current_time)

class AISummarizer:
    def __init__(self):
        self.current_key_index = 0
        if API_KEYS:
            genai.configure(api_key=API_KEYS[0])
        self.model = genai.GenerativeModel('gemini-3-flash-preview')
        self.system_prompt = """You are an expert content curator. Summarize the provided newsletter content into a clean, well-formatted HTML response, filtering out any promotional material like ads, job postings, or subscription pleas.
- Use `<ul>` and `<li>` for bullet points.
- Do NOT include the newsletter's subject; it will be added separately.
- Each bullet point should be on a new line.
- Keep the summary concise and focused on the most significant information only.
- Try to keep it to 5 to 7 bullet points, capturing only the most significant and impactful information."""

    def retry_with_backoff(self, func, max_retries=3, initial_delay=5):
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                error_str = str(e).lower()
                if any(x in error_str for x in ["429", "quota", "rate limit"]):
                    logging.warning(f"Rate limit hit on key index {self.current_key_index}.")
                    if len(API_KEYS) > 1:
                        self.current_key_index = (self.current_key_index + 1) % len(API_KEYS)
                        genai.configure(api_key=API_KEYS[self.current_key_index])
                        logging.info(f"Switching to API key index {self.current_key_index}...")
                        try:
                            return func()
                        except Exception:
                            pass
                    
                    if attempt < max_retries - 1:
                        delay = initial_delay * (2 ** attempt)
                        logging.warning(f"Retrying in {delay:.1f} seconds...")
                        time.sleep(delay)
                        continue
                raise e

    def summarize_emails(self, filtered_emails):
        if not filtered_emails:
            return []
        
        email_metadata = []
        emails_text = ""
        for i, email in enumerate(filtered_emails):
            email_metadata.append({'subject': email['subject'], 'sender': email['sender'], 'link': email.get('link')})
            emails_text += f"\n--- Email {i+1} ---\nSubject: {email['subject']}\nFrom: {email['sender']}\nContent:\n{email['body']}\n---\n"

        prompt = f"""{self.system_prompt}
Please summarize each of the following newsletters. Format your response as follows:
For each email, provide:
EMAIL_START
Subject: [original subject]
From: [sender name]
Summary: [your HTML summary here using <ul> and <li> tags]
EMAIL_END

Here are the newsletters to summarize:
{emails_text}
"""
        try:
            response = self.retry_with_backoff(lambda: self.model.generate_content(prompt))
            if not response or not response.text:
                return []
            return self._parse_batch_summaries(response.text, email_metadata)
        except Exception as e:
            logging.error(f"Error in batch summarization: {e}")
            return self._summarize_individually(filtered_emails)

    def _parse_batch_summaries(self, text, metadata_list):
        summaries = []
        text = text.replace("```html", "").replace("```", "").strip()
        sections = text.split("EMAIL_START")
        for i, section in enumerate(sections[1:]):
            if i >= len(metadata_list): break
            summary_part = section.split("EMAIL_END")[0] if "EMAIL_END" in section else section
            summary_text = summary_part.split("Summary:", 1)[1].strip() if "Summary:" in summary_part else summary_part.strip()
            summary_text = summary_text.replace("EMAIL_START", "").replace("EMAIL_END", "").strip()
            
            metadata = metadata_list[i]
            if metadata.get('link'):
                summary_text += f'<br><a href="{metadata["link"]}">Read More</a>'
            
            summaries.append({
                'subject': metadata['subject'],
                'summary_text': summary_text,
                'sender': metadata['sender']
            })
        return summaries

    def _summarize_individually(self, emails):
        summaries = []
        limiter = RateLimiter(4)
        for email in emails:
            try:
                limiter.wait_for_permission()
                resp = self.model.generate_content(f"{self.system_prompt}\n\nSummarize:\n{email['body']}")
                summary = resp.text.replace("```html", "").replace("```", "").strip() if resp and resp.text else ""
                if email.get('link'):
                    summary += f'<br><a href="{email["link"]}">Read More</a>'
                summaries.append({'subject': email['subject'], 'summary_text': summary, 'sender': email['sender']})
            except Exception as e:
                logging.error(f"Error summarizing {email['subject']}: {e}")
        return summaries

    def get_top_stories(self, summaries):
        history = []
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=15)).isoformat()
        today_prefix = datetime.datetime.now().isoformat()[:10]
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f:
                history = json.load(f)
        
        dedup_history = [item for item in history if item.get('date') > cutoff and not item.get('date', '').startswith(today_prefix)]
        history_context = [f"Subject: {item['subject']} | Summary: {item.get('reason', '')}" for item in dedup_history]

        combined = "\n".join([f"Story {i+1}: {s['subject']} - {s['sender']}\n{s['summary_text']}" for i, s in enumerate(summaries)])
        prompt = f"""Identify top AI & Tech stories (max 10). 
Select ONLY new, high-impact stories. Avoid similarity to:
{json.dumps(history_context, indent=2)}
Format as HTML `<ul>` and `<li>`. Each `<li>` must be: <li><b>Subject</b> Reason</li>.
Stories:
{combined}"""
        
        try:
            resp = self.retry_with_backoff(lambda: self.model.generate_content(prompt))
            html = resp.text.replace("```html", "").replace("```", "").strip() if resp and resp.text else ""
            
            # Update history
            soup = BeautifulSoup(html, 'html.parser')
            new_entries = []
            for li in soup.find_all('li'):
                b = li.find('b')
                if b:
                    new_entries.append({'subject': b.text.strip(), 'reason': li.text.replace(b.text, "").strip(), 'date': datetime.datetime.now().isoformat()})
            if new_entries:
                history.extend(new_entries)
                with open(HISTORY_FILE, 'w') as f: json.dump(history, f, indent=2)
            return html
        except Exception as e:
            logging.error(f"Error getting top stories: {e}")
            return "<p>Could not retrieve top stories.</p>"

    def generate_linkedin_posts(self, summaries):
        combined = "\n".join([f"Story {i+1}: {s['subject']}\n{s['summary_text']}" for i, s in enumerate(summaries)])
        prompt = f"""Act as a LinkedIn ghostwriter. Generate 3 high-performance posts based on:
{combined}
Use |||POST_SEPARATOR||| between posts. No meta-text."""
        try:
            resp = self.retry_with_backoff(lambda: self.model.generate_content(prompt))
            if not resp or not resp.text: return []
            return [p.strip() for p in resp.text.split("|||POST_SEPARATOR|||") if p.strip()]
        except Exception as e:
            logging.error(f"Error generating LinkedIn posts: {e}")
            return []
