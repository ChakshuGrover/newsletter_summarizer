import logging
import time
import json
import os
import datetime
import re
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
        
        # Using the user-selected Gemini 3 Preview model
        self.model = genai.GenerativeModel('gemini-3-flash-preview')
        
        self.system_prompt = """You are an expert content curator. Summarize the provided newsletter content into a clean, well-formatted HTML response, filtering out any promotional material like ads, job postings, or subscription pleas.
- Use `<ul>` and `<li>` for bullet points.
- Do NOT include the newsletter's subject; it will be added separately.
- Each bullet point should be on a new line.
- Keep the summary concise and focused on the most significant information only.
- Try to keep it to 5 to 7 bullet points, capturing only the most significant and impactful information.
- CRITICAL: Prioritize truly current events and news from the last 7 days. 
- IGNORE historical recaps, long analytical essays reflecting on old deals, "looking back" sections, or background context unless there is a significant NEW development reported *today*.
- If you are unsure if a piece of news is recent, err on the side of excluding it."""

    def _repair_json(self, raw_text):
        """Repair common JSON formatting issues from AI output."""
        if not raw_text:
            return "[]"
        
        # Remove markdown code blocks
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        # Try to find the start and end of the JSON array or object
        start_idx = raw_text.find("[")
        if start_idx == -1:
            start_idx = raw_text.find("{")
            
        end_idx = raw_text.rfind("]")
        if end_idx == -1:
            end_idx = raw_text.rfind("}")
            
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            raw_text = raw_text[start_idx:end_idx + 1]
            
        # Remove trailing commas before closing braces/brackets
        raw_text = re.sub(r",\s*\]", "]", raw_text)
        raw_text = re.sub(r",\s*\}", "}", raw_text)
        
        return raw_text

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
                        # Optimization from original: parse "retry in X" if available
                        match = re.search(r'retry in ([\d.]+)s', error_str)
                        if match:
                            delay = float(match.group(1)) + 1
                        
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
            email_metadata.append({
                'subject': email['subject'], 
                'sender': email['sender'], 
                'link': email.get('link')
            })
            emails_text += f"\n--- Email {i+1} ---\nSubject: {email['subject']}\nFrom: {email['sender']}\nDate: {email.get('date', 'Unknown')}\nContent:\n{email['body']}\n---\n"

        batch_prompt = f"""{self.system_prompt}

Please summarize each of the following newsletters. Format your response as follows:

For each email, provide:
EMAIL_START
Subject: [original subject]
From: [sender name]
Summary: [your HTML summary here using <ul> and <li> tags]
EMAIL_END

Here are the newsletters to summarize:
{emails_text}

Please provide summaries for all {len(filtered_emails)} emails in the format specified above."""
        
        try:
            logging.info("Sending batch summarization request to Gemini API...")
            response = self.retry_with_backoff(lambda: self.model.generate_content(batch_prompt))
            if not response or not response.text:
                return []
            return self._parse_batch_summaries(response.text, email_metadata)
        except Exception as e:
            logging.error(f"Error in batch summarization: {e}. Falling back to individual.")
            return self._summarize_individually(filtered_emails)

    def _parse_batch_summaries(self, response_text, email_metadata):
        summaries = []
        response_text = response_text.replace("```html", "").replace("```", "").strip()
        
        # Method 1: Try to parse using EMAIL_START/EMAIL_END markers
        if "EMAIL_START" in response_text:
            email_sections = response_text.split("EMAIL_START")
            for i, section in enumerate(email_sections[1:]):
                if i >= len(email_metadata): break
                summary_part = section.split("EMAIL_END")[0] if "EMAIL_END" in section else section
                summary_text = summary_part.split("Summary:", 1)[1].strip() if "Summary:" in summary_part else summary_part.strip()
                summary_text = summary_text.replace("EMAIL_START", "").replace("EMAIL_END", "").strip()
                
                metadata = email_metadata[i]
                if metadata.get('link'):
                    summary_text += f'<br><a href="{metadata["link"]}">Read More</a>'
                
                summaries.append({
                    'subject': metadata['subject'],
                    'summary_text': summary_text,
                    'sender': metadata['sender']
                })
        
        # Method 2: Try splitting by email numbers (Restored from original)
        if len(summaries) != len(email_metadata) and "--- Email" in response_text:
            logging.info("Trying alternative parsing method using email separators")
            email_sections = response_text.split("--- Email")
            summaries = []
            for i, section in enumerate(email_sections[1:]):
                if i >= len(email_metadata): break
                if "Summary:" in section or "Content:" in section:
                    lines = section.split("\n")
                    summary_lines = []
                    in_summary = False
                    for line in lines:
                        if "Summary:" in line or "Content:" in line:
                            in_summary = True
                            if ":" in line: summary_lines.append(line.split(":", 1)[1].strip())
                            continue
                        if in_summary and line.strip(): summary_lines.append(line.strip())
                    summary_text = "\n".join(summary_lines)
                else:
                    summary_text = section.strip()
                
                metadata = email_metadata[i]
                if metadata.get('link'): summary_text += f'<br><a href="{metadata["link"]}">Read More</a>'
                summaries.append({'subject': metadata['subject'], 'summary_text': summary_text, 'sender': metadata['sender']})

        return summaries

    def _summarize_individually(self, emails):
        summaries = []
        limiter = RateLimiter(4)
        for email in emails:
            try:
                limiter.wait_for_permission()
                resp = self.model.generate_content(f"{self.system_prompt}\n\nSummarize:\n{email['body']}")
                summary = resp.text.replace("```html", "").replace("```", "").strip() if resp and resp.text else ""
                if email.get('link'): summary += f'<br><a href="{email["link"]}">Read More</a>'
                summaries.append({'subject': email['subject'], 'summary_text': summary, 'sender': email['sender']})
            except Exception as e:
                logging.error(f"Error summarizing {email['subject']}: {e}")
        return summaries

    def generate_landscape_commentary(self, summaries):
        if not summaries:
            return ""
        
        combined = ""
        for i, item in enumerate(summaries):
            combined += f"Subject: {item['subject']}\nSummary: {item['summary_text']}\n\n"
            
        prompt = f"""Act as a high-level technology analyst and ghostwriter. Analyze the following AI and Tech newsletter summaries and provide a single, punchy paragraph (maximum 5 sentences) that captures the overarching progression and 'vibe' of the industry over the last few days.
        
        CRITICAL REQUIREMENTS:
        - Output ONLY the paragraph in PLAIN TEXT.
        - DO NOT use any Markdown (no bolding, no headers like ###, no bullet points, no **).
        - DO NOT include ANY introductory or concluding conversational filler. 
        - DO NOT start with phrases like "Based on the summaries provided..." or "Here is an analysis...". Start immediately with the analysis.
        - Focus on a high-level synthesis: Connect the dots between different news items rather than just listing them.
        
        Newsletter Summaries:
        {combined}"""
        
        try:
            resp = self.retry_with_backoff(lambda: self.model.generate_content(prompt))
            return resp.text.strip() if resp and resp.text else ""
        except Exception as e:
            logging.error(f"Error generating commentary: {e}")
            return ""

    def generate_contrarian_take(self, top_story):
        if not top_story:
            return ""
            
        prompt = f"""Act as a sharp, highly analytical tech skeptic. Given the following major news story, provide a single-sentence 'Contrarian Take' or 'Devil's Advocate' perspective that highlights potential risks, overhyped aspects, or hidden downsides.
        
        Story Title: {top_story.get('title', '')}
        Story News: {top_story.get('news', '')}
        """
        
        try:
            resp = self.retry_with_backoff(lambda: self.model.generate_content(prompt))
            return resp.text.strip() if resp and resp.text else ""
        except Exception as e:
            logging.error(f"Error generating contrarian take: {e}")
            return ""

    def get_top_stories(self, summaries, update_history=True):
        history = []
        # Extended window to 30 days for better "Story Arc" tracking
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
        today_prefix = datetime.datetime.now().isoformat()[:10]
        
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    history = json.load(f)
            except json.JSONDecodeError:
                history = []
        
        # Filter history to only include the last 30 days, excluding today (to avoid feedback loops)
        active_history = [item for item in history if item.get('date', '') > cutoff and not item.get('date', '').startswith(today_prefix)]
        history_context = [{"title": item.get('title', item.get('subject', '')), "impact": item.get('impact', item.get('reason', ''))} for item in active_history]

        combined = ""
        for i, item in enumerate(summaries):
            combined += f"Story {i+1}:\nSubject: {item['subject']}\nSender: {item['sender']}\nSummary: {item['summary_text']}\n\n"

        prompt = f"""From the following newsletter summaries, identify the top AI & Tech stories (maximum 30).
    
    **CRITICAL INSTRUCTIONS:**
    1. Compare these new stories against the recent history provided below.
    2. Categorize each new story with a Tag:
       - 🟢 [New Break]: Entirely new developments.
       - 🔵 [Developing]: Significant updates to an ongoing storyline from the history.
       - 🔴 [Contradiction]: A pivot, reversal, or contradiction to a previous historical story.
    3. Ignore stories that are merely repetitions of history without significant updates.
    4. Provide "The News" (a concise summary) and "The Impact" (a 1-sentence explanation of why it matters to the industry).
    5. For 🔵 [Developing] or 🔴 [Contradiction] stories, provide a ONE-LINE "Tag Reason" that explains exactly what it follows or contradicts from the history. If it is 🟢 [New Break], leave it empty.
    6. UNIQUE NUGGETS: While prioritizing major trends, also capture unique "nuggets" (e.g., a specific new tool, a niche model update, or a unique data point) that might only appear in a single newsletter, ensuring no unique value is lost when individual summaries are removed.
    
    **CRITICAL RECENTNESS & GROUNDING RULES:**
    1. ONLY identify stories that are reported as NEW or DEVELOPING breaking news within the provided summaries.
    2. IGNORE analytical essays, historical recaps, deep dives into old news, or "looking back" sections.
    3. If a story mentions a deal or event that occurred months ago (even if discussed in a recent essay), EXCLUDE it.
    4. Ensure every story is grounded in a specific, recent factual event reported in the provided newsletter summaries.
    5. The "title" and "news" MUST reflect a development from the last 7 days, not background context or historical analysis.
    6. Be extremely selective: prefer high-quality, truly recent stories over mediocre or old ones.
    7. If a newsletter is an analytical deep dive into Meta's past spending or strategy, DO NOT extract old deals as "Top Stories".

    **Recent History Context (Last 30 Days):**
    {json.dumps(history_context, indent=2)}

    **Output Format:**
    You MUST respond with ONLY valid JSON. Return an array of JSON objects, where each object has EXACTLY these keys:
    - "title": (string) The subject title.
    - "tag": (string) Either "🟢 [New Break]", "🔵 [Developing]", or "🔴 [Contradiction]".
    - "tag_reason": (string) One-liner on what it followed or contradicted (if applicable).
    - "news": (string) The concise summary.
    - "impact": (string) The "So What?" impact statement.

    Newsletter Summaries:
    {combined}"""
        
        try:
            resp = self.retry_with_backoff(lambda: self.model.generate_content(prompt))
            raw_text = resp.text if resp and resp.text else "[]"
            
            # Use the new robust JSON repair
            raw_text = self._repair_json(raw_text)
            
            top_stories_data = json.loads(raw_text)
            
            if top_stories_data and update_history:
                today_iso = datetime.datetime.now().isoformat()
                new_entries = []
                for story in top_stories_data:
                    new_entries.append({
                        'title': story.get('title', ''),
                        'tag': story.get('tag', ''),
                        'news': story.get('news', ''),
                        'impact': story.get('impact', ''),
                        'tag_reason': story.get('tag_reason', ''),
                        'date': today_iso
                    })
                
                # Save only the active 30-day window + new entries to disk
                updated_history = active_history + new_entries
                with open(HISTORY_FILE, 'w') as f: 
                    json.dump(updated_history, f, indent=2)
            
            return top_stories_data
        except Exception as e:
            logging.error(f"Error getting top stories: {e}")
            return []

    def generate_linkedin_posts(self, summaries):
        # Restored the full, high-quality LinkedIn prompt from original
        combined = ""
        for i, item in enumerate(summaries):
            combined += f"Story {i+1}:\nSubject: {item['subject']}\nSummary: {item['summary_text']}\n\n"

        prompt = f"""Act as a world-class LinkedIn ghostwriter. Using the newsletter summaries provided, generate 3 high-performance posts designed to maximize dwell time and engagement.

    **Engagement Framework:**
    - **The Hook:** Start with a punchy first line (under 10 words).
    - **The Body:** Use "The Slide" technique—short, punchy sentences. 1-2 emojis.
    - **The CTA:** End with a low-friction question.
    - **Visuals:** Prioritize white space.

    **Option Definitions:**
    1. **The Contrarian Highlight:** Focus on the biggest story. Challenge the popular opinion.
    2. **The "Too Busy To Read" Roundup:** "3 things you need to know today" format.
    3. **The "So What?" Insight:** Connect a specific development to a bottom-line implication.

    **Hashtag Rule:** Include exactly 3 relevant hashtags at the end.

    **Formatting Rules (CRITICAL):**
    - NO meta-text, labels (e.g., "Option 1"), or headers.
    - NO introductory or concluding conversational filler.
    - Separate the three options using exactly: |||POST_SEPARATOR|||

    Summaries:
    {combined}"""
        
        try:
            resp = self.retry_with_backoff(lambda: self.model.generate_content(prompt))
            if not resp or not resp.text: return []
            return [p.strip() for p in resp.text.split("|||POST_SEPARATOR|||") if p.strip()]
        except Exception as e:
            logging.error(f"Error generating LinkedIn posts: {e}")
            return []
