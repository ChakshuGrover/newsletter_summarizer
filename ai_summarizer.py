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
from digest_layout import normalize_category, normalize_tier

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
        
        # Using the Gemini 3.5 Flash model
        self.model = genai.GenerativeModel('gemini-3.5-flash')
        
        self.system_prompt = """You are an expert content curator. Summarize the provided newsletter content into a clean, well-formatted HTML response, filtering out any promotional material like ads, job postings, or subscription pleas.
- Use `<ul>` and `<li>` for bullet points.
- Do NOT include the newsletter's subject; it will be added separately.
- Each bullet point should be on a new line.
- Keep the summary concise and focused on the most significant information only.
- Try to keep it to 5 to 7 bullet points, capturing only the most significant and impactful information.
- CRITICAL: Prioritize truly current events and news from the last 7 days. 
- IGNORE historical recaps, long analytical essays reflecting on old deals, "looking back" sections, or background context unless there is a significant NEW development reported *today*.
- If you are unsure if a piece of news is recent, err on the side of excluding it.
- **LINKS**: If a story has a relevant URL provided in brackets [like this], preserve that URL in your summary by making the story title or key phrase a clickable link: `<a href="URL">Title</a>`."""

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
                    logging.warning(f"Rate limit hit on key index {self.current_key_index}: {e}")
                    
                    if len(API_KEYS) > 1:
                        self.current_key_index = (self.current_key_index + 1) % len(API_KEYS)
                        logging.info(f"Rotating to API key index {self.current_key_index}...")
                        genai.configure(api_key=API_KEYS[self.current_key_index])
                        # CRITICAL FIX: Re-instantiate the model so it binds to the new active key
                        self.model = genai.GenerativeModel('gemini-3.5-flash')
                        
                        try:
                            logging.info("Retrying immediately with the new rotated key...")
                            return func()
                        except Exception as retry_err:
                            logging.warning(f"Immediate retry on rotated key index {self.current_key_index} failed: {retry_err}")
                    
                    if attempt < max_retries - 1:
                        delay = initial_delay * (2 ** attempt)
                        match = re.search(r'retry in ([\d.]+)s', error_str)
                        if match:
                            delay = float(match.group(1)) + 1
                        
                        logging.warning(f"Sleeping for {delay:.1f} seconds before next retry...")
                        time.sleep(delay)
                        continue
                raise e

    def summarize_emails(self, filtered_emails, chunk_size=10):
        if not filtered_emails:
            return []
        
        all_summaries = []
        total_emails = len(filtered_emails)
        logging.info(f"Summarizing {total_emails} emails in chunks of {chunk_size}...")
        
        for chunk_idx in range(0, total_emails, chunk_size):
            chunk = filtered_emails[chunk_idx : chunk_idx + chunk_size]
            logging.info(f"Processing chunk {chunk_idx // chunk_size + 1}/{(total_emails - 1) // chunk_size + 1} ({len(chunk)} emails)...")
            
            email_metadata = []
            emails_text = ""
            for i, email in enumerate(chunk):
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

Please provide summaries for all {len(chunk)} emails in the format specified above."""
            
            try:
                response = self.retry_with_backoff(
                    lambda: self.model.generate_content(
                        batch_prompt, 
                        generation_config={"temperature": 0.0}
                    )
                )
                if not response or not response.text:
                    logging.error(f"Empty response received for chunk starting at index {chunk_idx}.")
                    continue
                
                chunk_summaries = self._parse_batch_summaries(response.text, email_metadata)
                if not chunk_summaries:
                    logging.warning(f"No summaries were parsed for chunk starting at index {chunk_idx}!")
                    logging.warning(f"Raw response (first 1000 chars): {response.text[:1000]}")
                else:
                    all_summaries.extend(chunk_summaries)
            except Exception as e:
                logging.error(f"Error in chunk summarization (index {chunk_idx}): {e}")
                
        return all_summaries

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
                    'sender': metadata['sender'],
                    'link': metadata.get('link')
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
                summaries.append({
                    'subject': metadata['subject'],
                    'summary_text': summary_text,
                    'sender': metadata['sender'],
                    'link': metadata.get('link')
                })

        return summaries

    def generate_landscape_commentary(self, summaries):
        if not summaries:
            return ""
        
        combined = ""
        for i, item in enumerate(summaries):
            combined += f"Subject: {item['subject']}\nSummary: {item['summary_text']}\n\n"
            
        prompt = f"""Act as a world-class technology analyst, venture capitalist, and chief storyteller writing with the narrative flair of Wired, the sharp-witted clarity of Stratechery, and the editorial precision of The Economist.

Analyze the following AI and Tech newsletter summaries and provide a single, punchy paragraph (maximum 5 sentences) that synthesizes the overarching narrative and 'vibe' of the industry over the last few days.

CRITICAL CONTENT & CREATIVITY REQUIREMENTS:
- HOOK WITH TECH & CAPABILITIES: Start immediately with a dynamic, specific opening hook focused on the latest technological breakthroughs, new product/model launches, or what is now possible with AI. Do NOT start with corporate drama, layoffs, or funding rounds; keep the focus on technology and capability first, integrating business context only as secondary support.
- BANNED CLICHÉS: Strictly forbid the standard, repetitive opening formulas. Do NOT start with phrases like:
  * "The technology sector/AI industry is transitioning/shifting/undergoing a transition..."
  * "The tech landscape is shifting..."
  * "The technology landscape has officially entered..."
  * "The AI industry has moved past/entered..."
  * "Transitioning from speculative chatbot hype..."
- HIGH-LEVEL SYNTHESIS: Connect the dots between different news items into a coherent story, but ensure it is grounded in real facts, numbers, dollar values, or company names from the summaries. Do NOT write in vague, generic platitudes.
- OUTPUT FORMAT: Output ONLY the paragraph in PLAIN TEXT. No markdown (no bolding like **, no headers like ###, no bullet points). No introductory or concluding conversational filler.

Newsletter Summaries:
{combined}"""
        
        try:
            resp = self.retry_with_backoff(
                lambda: self.model.generate_content(
                    prompt, 
                    generation_config={"temperature": 0.75}
                )
            )
            return resp.text.strip() if resp and resp.text else ""

        except Exception as e:
            logging.error(f"Error generating commentary: {e}")
            return ""

    def get_top_stories(self, summaries, update_history=True, target_date=None):
        history = []
        # Extended window to 30 days for better "Story Arc" tracking
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
        
        # Determine the logical date of this run
        logical_date = target_date if target_date else datetime.datetime.now().isoformat()
        logical_day_prefix = logical_date[:10]
        
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    history = json.load(f)
            except json.JSONDecodeError:
                history = []
        
        # Filter history to only include the last 30 days, excluding the current logical run day (to avoid feedback loops)
        active_history = [item for item in history if item.get('date', '') > cutoff and not item.get('date', '').startswith(logical_day_prefix)]
        history_context = [{"title": item.get('title', item.get('subject', '')), "impact": item.get('impact', item.get('reason', ''))} for item in active_history]

        combined = ""
        for i, item in enumerate(summaries):
            combined += f"Story {i+1}:\nSubject: {item['subject']}\nSender: {item['sender']}\nLink: {item.get('link', '')}\nSummary: {item['summary_text']}\n\n"

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
    6. SOURCE NEWSLETTER: For every story, identify the specific newsletter summary it was extracted from (represented as 'Story 1', 'Story 2', etc. in the list below).
    7. CONTRARIAN TAKE: For every story, act as a sharp, highly analytical tech skeptic and generate a single-sentence 'Contrarian Take' or 'Devil's Advocate' perspective that highlights potential risks, overhyped aspects, or hidden downsides.
    8. UNIQUE NUGGETS: While prioritizing major trends, also capture unique "nuggets" (e.g., a specific new tool, a niche model update, or a unique data point) that might only appear in a single newsletter, ensuring no unique value is lost when individual summaries are removed.
    9. STORY TIER: Assign each story exactly one tier:
       - "headline": The 5–7 most important stories of the period (major industry shifts, landmark deals, flagship model launches). Use sparingly.
       - "standard": Significant stories that belong in a themed section below.
       - "nugget": Smaller but useful items (niche tool launches, minor feature updates, single data points). Aim for 5–10 nuggets when available.
    10. CATEGORY: Assign each story exactly one primary category (use these exact snake_case values):
       - "capital": Funding rounds, valuations, M&A, IPO/S-1 filings, major partnerships with dollar figures, and public-company financial news (quarterly earnings, revenue beats/misses, guidance, investor-day targets, secondary offerings).
       - "products": Model launches and updates, benchmarks, papers, safety/interpretability research, shipped features, GA product releases, integrations, developer tools, and landmark researcher or lab-lead hires tied to model building (e.g. joins pretraining team). Prefer "products" over "industry" for technical talent moves.
       - "infrastructure": Data centers, chips/TPUs/GPUs/CPUs, energy/grid, cloud capacity, compute architecture, hardware roadmaps.
       - "industry": Layoffs, hiring freezes, reorgs, C-suite or business/operations leadership moves, regulation, lawsuits, military/government contracts, privacy, and security breaches. Do NOT use "industry" for earnings, revenue, IPO/filing news, or core R&D hires—use "capital" or "products" instead.
       Category tie-breakers: (a) earnings + product launch in one newsletter → split into two stories (see rule 11); (b) chip earnings alone → "capital"; (c) new silicon/CPU/GPU announcement alone → "infrastructure"; (d) famous researcher joins training/R&D team → "products"; (e) CEO/CFO/COO or mass layoffs → "industry".
    11. SPLIT COMBINED STORIES: When a newsletter summary clearly contains two distinct beats (e.g., "record Q1 earnings" AND "unveils new Vera CPU"), emit TWO separate JSON objects—one per beat—each with its own title, category, tier, and importance_rank. Do not merge unrelated developments into one card. Both items may share the same source_newsletter_index. Splits count toward the maximum of 30 stories.
    12. IMPORTANCE_RANK: Integer 1–30 where 1 is the single most important story in this digest. Headlines should be ranks 1–7. Nuggets should be ranks 20–30.
    
    **CRITICAL RECENTNESS & GROUNDING RULES:**
    1. ONLY identify stories that are reported as NEW or DEVELOPING breaking news within the provided summaries.
    2. IGNORE analytical essays, historical recaps, deep dives into old news, or "looking back" sections.
    3. If a story mentions a deal or event that occurred months ago (even if discussed in a recent essay), EXCLUDE it.
    4. Ensure every story is grounded in a specific, recent factual event reported in the provided newsletter summaries.
    5. The "title" and "news" MUST reflect a development from the last 7 days, not background context or historical analysis.
    6. Be extremely selective: prefer high-quality, truly recent stories over mediocre or old ones.
    7. If a newsletter is an analytical deep dive into a company's past strategy, historical deals, or a "looking back" essay, DO NOT extract those events as "Top Stories". Every story MUST be a new factual development reported in the last 7 days.
    8. VERIFY RECENTNESS: If the text describes an event in the past tense without a specific recent date (e.g., "Last year," "In 2024," "The previously announced deal"), EXCLUDE it. Only include news that is happening NOW.

    **Recent History Context (Last 30 Days):**
    {json.dumps(history_context, indent=2)}

    **Output Format:**
    You MUST respond with ONLY valid JSON. Return an array of JSON objects, where each object has EXACTLY these keys:
    - "title": (string) The subject title.
    - "tag": (string) Either "🟢 [New Break]", "🔵 [Developing]", or "🔴 [Contradiction]".
    - "tag_reason": (string) One-liner on what it followed or contradicted (if applicable).
    - "news": (string) The concise summary.
    - "impact": (string) The "So What?" impact statement.
    - "source_newsletter_index": (integer) The 1-based index of the newsletter summary where this story was found (e.g., 1 for Story 1, 2 for Story 2, etc.).
    - "contrarian_take": (string) The single-sentence contrarian take or skeptical perspective.
    - "tier": (string) Exactly one of: "headline", "standard", "nugget".
    - "category": (string) Exactly one of: "capital", "products", "infrastructure", "industry".
    - "importance_rank": (integer) Importance rank 1–30 within this digest.

    Newsletter Summaries:
    {combined}"""
        
        try:
            resp = self.retry_with_backoff(
                lambda: self.model.generate_content(
                    prompt, 
                    generation_config={"temperature": 0.0}
                )
            )

            raw_text = resp.text if resp and resp.text else "[]"
            
            # Use the new robust JSON repair
            raw_text = self._repair_json(raw_text)
            
            top_stories_data = json.loads(raw_text)
            
            if top_stories_data:
                for story in top_stories_data:
                    story['tier'] = normalize_tier(story.get('tier'))
                    story['category'] = normalize_category(story.get('category'))
                    idx = story.get('source_newsletter_index')
                    if idx is not None:
                        try:
                            idx = int(idx)
                            if 1 <= idx <= len(summaries):
                                story['source_url'] = summaries[idx - 1].get('link') or ""
                            else:
                                story['source_url'] = ""
                        except (ValueError, TypeError):
                            story['source_url'] = ""
                    else:
                        story['source_url'] = ""
            
            if top_stories_data and update_history:
                new_entries = []
                for story in top_stories_data:
                    new_entries.append({
                        'title': story.get('title', ''),
                        'tag': story.get('tag', ''),
                        'news': story.get('news', ''),
                        'impact': story.get('impact', ''),
                        'tag_reason': story.get('tag_reason', ''),
                        'source_url': story.get('source_url', ''),
                        'contrarian_take': story.get('contrarian_take', ''),
                        'tier': story.get('tier', 'standard'),
                        'category': story.get('category', 'products'),
                        'date': logical_date
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
            resp = self.retry_with_backoff(
                lambda: self.model.generate_content(
                    prompt, 
                    generation_config={"temperature": 0.5}
                )
            )
            if not resp or not resp.text: return []

            return [p.strip() for p in resp.text.split("|||POST_SEPARATOR|||") if p.strip()]
        except Exception as e:
            logging.error(f"Error generating LinkedIn posts: {e}")
            return []
