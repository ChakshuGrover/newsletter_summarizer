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
from utils import sanitize_url

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
        self.model = genai.GenerativeModel('gemini-3.6-flash')
        
        self.system_prompt = """You are an expert content curator. Summarize the provided newsletter content into a clean, well-formatted HTML response, filtering out any promotional material like ads, job postings, or subscription pleas.
- Use `<ul>` and `<li>` for bullet points.
- Do NOT include the newsletter's subject; it will be added separately.
- Each bullet point should be on a new line.
- Keep the summary concise and focused on the most significant information only.
- Try to keep it to 5 to 7 bullet points, capturing only the most significant and impactful information.
- CRITICAL: Prioritize truly current events and news from the last 7 days. 
- IGNORE historical recaps, long analytical essays reflecting on old deals, "looking back" sections, or background context unless there is a significant NEW development reported *today*.
- If you are unsure if a piece of news is recent, err on the side of excluding it.
- **LINKS (CRITICAL)**: For every single news event, tool, or story you summarize, if there is a URL provided in brackets [like this] anywhere in that section in the source text, you MUST preserve that exact URL in your summary. Make the key subject name, title, or key phrase a clickable link: `<a href="URL">Subject</a>`. Do NOT omit or lose these links; every reported fact should be link-rich if it was linked in the source.
- **HUMAN-LIKE WRITING STANDARDS (CRITICAL)**:
  * Do NOT use em dashes (`—` or `--`) under any circumstances to append details or make parenthetical remarks. Use standard commas, parentheses, or separate sentences instead.
  * Strictly avoid AI jargon, filler, and transition buzzwords. BANNED words include: *delve, tapestry, testament, pinnacle, cutting-edge, game-changer, revolutionary, groundbreaking, demystify, catalyst, beacon, underpins, underscores, moreover, furthermore, notably, transform, revolutionize*.
  * Vary your sentence structures. Never start consecutive bullet points with identical syntax (e.g. avoid starting multiple items with "Company X announced...", "X is a tool...", or "Y launched...").
  * Ground the writing in plain, direct facts. Eliminate all marketing hype and promotional fluff (e.g., avoid "excited to announce", "paving the way", or "redefining the landscape")."""

    def _repair_json(self, raw_text):
        """Repair common JSON formatting issues from AI output."""
        if not raw_text:
            return "[]"
        
        # Remove markdown code blocks
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        # Try to find the start and end of the JSON array or object
        start_idx_bracket = raw_text.find("[")
        start_idx_brace = raw_text.find("{")
        
        if start_idx_bracket != -1 and start_idx_brace != -1:
            start_idx = min(start_idx_bracket, start_idx_brace)
        elif start_idx_bracket != -1:
            start_idx = start_idx_bracket
        else:
            start_idx = start_idx_brace
            
        # For end, check which of ] or } comes last
        end_idx_bracket = raw_text.rfind("]")
        end_idx_brace = raw_text.rfind("}")
        
        if end_idx_bracket != -1 and end_idx_brace != -1:
            end_idx = max(end_idx_bracket, end_idx_brace)
        elif end_idx_bracket != -1:
            end_idx = end_idx_bracket
        else:
            end_idx = end_idx_brace
            
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
                        self.model = genai.GenerativeModel('gemini-3.6-flash')
                        
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
                    'link': email.get('link'),
                    'raw_links': email.get('raw_links', [])
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
                    'link': metadata.get('link'),
                    'raw_links': metadata.get('raw_links', [])
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
                    'link': metadata.get('link'),
                    'raw_links': metadata.get('raw_links', [])
                })

        return summaries

    def _find_all_sender_matches(self, sender_str, summaries):
        if not sender_str or not summaries:
            return []
        
        sender_clean = sender_str.strip().lower()
        matches = []
        
        # First pass: Exact match
        for i, s in enumerate(summaries):
            s_sender = s.get('sender', '').strip().lower()
            if sender_clean == s_sender:
                matches.append(i)
        if matches:
            return matches
                
        # Second pass: Substring match (e.g. "AI Breakfast" matches "AI Breakfast <no-reply@beehiiv.com>")
        for i, s in enumerate(summaries):
            s_sender = s.get('sender', '').strip().lower()
            s_sub = s.get('subject', '').strip().lower()
            if sender_clean in s_sender or s_sender in sender_clean or sender_clean in s_sub:
                matches.append(i)
        if matches:
            return matches
                
        # Third pass: Token-based matching (e.g. "Zain Kahn" matches "Superhuman - Zain Kahn")
        tokens = [t for t in sender_clean.split() if len(t) > 2]
        for i, s in enumerate(summaries):
            s_sender = s.get('sender', '').strip().lower()
            if any(token in s_sender for token in tokens):
                matches.append(i)
                
        return matches

    def _extract_specific_story_link(self, story_title, story_news, html_summary, raw_links=None):
        if not html_summary and not raw_links:
            return None, 0.0
        try:
            candidates = {}
            
            # 1. From HTML summary
            if html_summary:
                soup = BeautifulSoup(html_summary, 'html.parser')
                for a in soup.find_all('a'):
                    href = a.get('href', '')
                    text = a.text.strip()
                    if href and not href.startswith('#'):
                        norm_href = href.rstrip('/')
                        candidates[norm_href] = {'text': text, 'href': href}
            
            # 2. From raw email links
            if raw_links:
                for rl in raw_links:
                    href = rl.get('href', '')
                    text = rl.get('text', '')
                    if href and not href.startswith('#'):
                        norm_href = href.rstrip('/')
                        if norm_href not in candidates or len(text) > len(candidates[norm_href]['text']):
                            candidates[norm_href] = {'text': text, 'href': href}
                            
            if not candidates:
                return None, 0.0
            
            # Score each link based on word matches between the story's details and the link's anchor text
            raw_title_words = set(re.findall(r'\b\w{3,}\b', (story_title + " " + story_news).lower()))
            
            # Filter out common stop words to avoid accidental matches on generic terms
            stop_words = {
                'new', 'app', 'apps', 'tool', 'tools', 'day', 'days', 'week', 'weeks', 'month', 'months', 'year', 'years', 
                'today', 'daily', 'called', 'using', 'used', 'use', 'with', 'for', 'the', 'this', 'that', 'from', 'our', 
                'your', 'their', 'them', 'they', 'here', 'there', 'who', 'what', 'why', 'how', 'where', 'when', 'will', 
                'would', 'could', 'should', 'have', 'has', 'had', 'been', 'being', 'does', 'doing', 'done', 'make', 
                'making', 'made', 'take', 'taking', 'took', 'get', 'getting', 'got', 'look', 'looking', 'looked', 'find', 
                'finding', 'found', 'also', 'free', 'best', 'more', 'latest', 'trending', 'click', 'link', 'signup',
                'sign', 'join', 'start', 'try', 'now', 'learn', 'get', 'pro'
            }
            title_words = raw_title_words - stop_words
            if not title_words:
                return None, 0.0
            
            best_link = None
            best_score = 0.0
            
            for key, cand in candidates.items():
                href = cand['href']
                anchor_text = cand['text']
                anchor_lower = anchor_text.strip().lower()
                
                # Check for 'readmore' or general read more text, but ONLY skip it if the URL itself doesn't contain high-quality keywords
                is_read_more = 'readmore' in href.lower() or 'read more' in anchor_lower or anchor_lower in ['read more', 'learn more', 'click here', 'github link', 'github repo', 'github']
                
                # Calculate URL-based intersection score
                url_words = set(re.findall(r'\b\w{3,}\b', href.lower())) - stop_words
                url_intersection = title_words.intersection(url_words)
                url_score = len(url_intersection) * 0.5
                
                # If it's a "read more" anchor but there's no URL match, skip it
                if is_read_more and url_score == 0.0:
                    continue
                
                raw_anchor_words = set(re.findall(r'\b\w{3,}\b', anchor_lower))
                anchor_words = raw_anchor_words - stop_words
                
                if not anchor_words and not url_intersection:
                    continue
                
                # Skip sponsor/ad anchors — these appear in every newsletter and are not news stories
                sponsor_signals = ['sponsor', 'sponsored', 'advertisement', 'signup', 'sign up',
                                   'subscribe', 'unsubscribe', 'try for free', 'get started', 'learn more', 'click here']
                if any(sig in anchor_lower for sig in sponsor_signals) and url_score == 0.0:
                    continue
                
                # Calculate raw intersection score
                anchor_intersection = title_words.intersection(anchor_words)
                score = float(len(anchor_intersection))
                
                # Length-based word uniqueness bonus for anchor text words
                common_entities = {
                    'openai', 'anthropic', 'google', 'microsoft', 'meta', 'nvidia', 'apple', 'amazon',
                    'chatgpt', 'claude', 'gemini', 'llama', 'copilot'
                }
                for word in anchor_intersection:
                    if word not in common_entities:
                        if len(word) > 4:
                            score += 0.3
                        if len(word) > 6:
                            score += 0.4
                
                # Add URL-based intersection score and uniqueness bonus
                score += url_score
                for word in url_intersection:
                    if word not in common_entities:
                        if len(word) > 4:
                            score += 0.15
                        if len(word) > 6:
                            score += 0.2
                
                # Length penalty: If anchor text is very long, it's likely a whole paragraph or malformed HTML section
                if len(raw_anchor_words) > 15:
                    score *= 0.1
                elif len(raw_anchor_words) > 8:
                    score *= 0.5
                
                # Short anchors (≤4 words) need a higher bar to avoid coincidental single-word hits on ad copy
                min_score = 1.5 if len(raw_anchor_words) <= 4 else 0.8
                
                if score > best_score and score >= min_score:
                    best_score = score
                    best_link = href
            
            # Resolve tracking redirects and strip UTM params from the winning link
            if best_link:
                best_link = sanitize_url(best_link, resolve=True)
            return best_link, best_score
        except Exception as e:
            logging.warning(f"Error extracting specific story link: {e}")
            return None, 0.0

    def generate_digest_data(self, summaries, update_history=True, target_date=None):
        if not summaries:
            return {"commentary": "", "top_stories": []}
        
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
        history_context = [
            {
                "title": item.get('title', item.get('subject', '')),
                "news": item.get('news', ''),
                "impact": item.get('impact', item.get('reason', ''))
            } 
            for item in active_history
        ]

        combined = ""
        for i, item in enumerate(summaries):
            combined += f"Story {i+1}:\nSubject: {item['subject']}\nSender: {item['sender']}\nLink: {item.get('link', '')}\nSummary: {item['summary_text']}\n\n"

        prompt = f"""From the following newsletter summaries, analyze the tech news landscape and generate two structured elements in a single JSON response:
    1. A list of 2 to 4 dominant macro themes observed across ALL newsletter summaries.
    2. An array of the top AI & Tech stories (strictly maximum 10 stories total across all tiers) representing key developments.
    
    **CRITICAL INSTRUCTIONS FOR MACRO THEMES:**
    - Analyze all incoming newsletter summaries to identify the 2 to 4 dominant, overarching macro themes or storylines of the day.
    - Connect the dots between different news items and show how they are part of a larger trend, rather than just repeating individual stories.
    - For each theme, provide:
      * A title representing the trend (e.g. "The Physical Constraints Bottleneck (Gigawatts & Capex)").
      * A 1-2 sentence synthesis explaining why this trend matters and how it connects the stories under the overarching narrative.
    - THEME DEDUPLICATION & CONTINUITY: Compare today's themes against the recent 30-day history. If an overarching theme (e.g. US-China sanctions) was already active in history, focus today's theme title and synthesis strictly on today's new updates, progression, or complications. Do not repeat high-level introductory overviews or define the theme from scratch.
    
    **CRITICAL INSTRUCTIONS FOR TOP STORIES:**
    - Identify the top AI & Tech stories (strictly maximum 10 stories total across all tiers).
    - Compare these new stories against the recent 30-day history provided below.
    - STRICT 30-DAY DUPLICATION & REPETITION GATING:
      * Avoid duplicating stories that have already been reported in the history.
      * Look at the "title" and "news" fields of the history. If a story in the summaries covers the same announcement, launch, corporate event, or product (even if detailed by a different sender or with minor additional commentary/quotes), you MUST ignore and omit it entirely from the output.
      * **Continuity Limit**: Do NOT include a story as 🔵 [Developing] unless there is a **major, concrete and significant new milestone** reported today (e.g., a model that was previously rumored is now actually open-sourced, or a deal previously in talks has officially closed). If the new email just contains post-launch reactions, opinion pieces, follow-up analysis, minor feature tweaks, or reviews of a story already in the 30-day history, you MUST ignore and omit it.
      * If a story is a repeat of history without a massive new milestone, omit it entirely from the output.
    - STRICT CATEGORY LIMITS: Limit the number of 'capital' category stories (funding, IPOs, M&As, financial capex announcements) to a maximum of 2 stories in the entire digest. Focus the remaining 8+ stories strictly on product launches, model updates, open-source weights, technical infrastructure development, or regulatory policy. Relegate minor capital stories to nuggets or omit them.
    - Categorize each new story with a Tag:
       - 🟢 [New Break]: Entirely new developments.
       - 🔵 [Developing]: Significant updates to an ongoing storyline from the history.
       - 🔴 [Contradiction]: A pivot, reversal, or contradiction to a previous historical story.
    - TONE: Write with the wit of Morning Brew and sharpness of Stratechery. Use vivid verbs, active voice, and avoid corporate jargon.
    - ANALYTICAL OBJECTIVITY: In "The Impact" statement, do NOT make definitive future predictions or subjective value claims. Keep it grounded, analytical, and objective. Use soft qualifiers like "could become", "may set", or "is positioned to" rather than definitive declarations to protect credibility.
    - HUMAN-LIKE WRITING STANDARDS: 
      * Do NOT use em dashes (— or --) under any circumstances in the titles, syntheses, news, or impact summaries. Use standard commas, parentheses, or separate sentences instead.
      * Strictly avoid AI jargon, filler, and transition buzzwords. BANNED words include: delve, tapestry, testament, pinnacle, cutting-edge, game-changer, revolutionary, groundbreaking, demystify, catalyst, beacon, underpins, underscores, moreover, furthermore, notably, transform, revolutionize.
      * Vary your sentence structures. Never start consecutive stories or themes with identical syntax.
      * Ground the writing in plain, direct facts. Eliminate all marketing hype and promotional fluff.
    - For 🔵 [Developing] or 🔴 [Contradiction] stories, provide a ONE-LINE "Tag Reason" that explains exactly what it follows or contradicts from the history. If it is 🟢 [New Break], leave it empty.
    - SOURCE NEWSLETTER SENDER: Identify the exact sender of the newsletter summary where this story was found.
    - OPTIONAL CONTRARIAN TAKE (STRICTLY MAX 3 STORIES): Act as a sharp, highly analytical tech skeptic. You must ONLY provide a 'contrarian_take' for at most 3 stories in the entire digest (specifically those that are highly hyped, controversial, or have major unaddressed risks). For all other stories, you MUST return an empty string "" in this field.
    - UNIQUE NUGGETS: Capture unique "nuggets" (e.g., a specific new tool, a niche model update, or a unique data point) that might only appear in a single newsletter.
    - STORY TIER: Assign each story exactly one tier (ensure total stories do not exceed 10):
       - "headline": The 1-2 most important tech/product/infrastructure stories of the day. Use extremely sparingly. (Do NOT assign "capital" stories to the headline tier).
       - "standard": Significant stories that belong in a themed section. Target 3-5 stories.
       - "nugget": Smaller but useful items (niche tool launches, minor feature updates, single data points). Target 3-4 stories.
    - CATEGORY: Assign each story exactly one primary category (use these exact snake_case values):
       - "capital", "products", "infrastructure", "industry".
    - SPLIT COMBINED STORIES: When a newsletter summary clearly contains two distinct beats, emit TWO separate JSON objects—one per beat—each with its own title, category, tier, and importance_rank.
    - IMPORTANCE_RANK: Integer 1–10 where 1 is the single most important story in this digest.
    
    **CRITICAL RECENTNESS & GROUNDING RULES:**
    1. ONLY identify stories that are reported as NEW or DEVELOPING breaking news within the provided summaries.
    2. IGNORE analytical essays, historical recaps, weekly summaries of older news, or "looking back" sections.
    3. Ensure every story is grounded in a specific, recent factual event reported in the provided newsletter summaries.
    4. STRICT RECENTNESS FILTER: If a story describes an event that took place, was announced, or broke more than 4 days ago, or is a recap of older events from the past week, you MUST exclude it. Focus exclusively on active, fresh news that broke within the last 72 hours.
 
    **Recent History Context (Last 30 Days):**
    {json.dumps(history_context, indent=2)}
 
    **Output Format:**
    You MUST respond with ONLY valid JSON. Return a JSON object with EXACTLY these keys:
    - "macro_themes": (array of JSON objects) The list of macro themes observed, where each object has these keys:
      * "theme_title": (string) The title of the macro theme.
      * "synthesis": (string) Connecting synthesis paragraph.
    - "top_stories": (array of JSON objects) The list of top stories, where each story object has EXACTLY these keys:
      * "title": (string) The subject title.
      * "tag": (string) Either "🟢 [New Break]", "🔵 [Developing]", or "🔴 [Contradiction]".
      * "tag_reason": (string) One-liner on what it followed or contradicted (if applicable).
      * "news": (string) The concise summary.
      * "impact": (string) The "So What?" impact statement.
      * "source_newsletter_sender": (string) The exact sender of the newsletter summary where this story was found.
      * "contrarian_take": (string) The contrarian take (or empty string if not applicable).
      * "tier": (string) Exactly one of: "headline", "standard", "nugget".
      * "category": (string) Exactly one of: "capital", "products", "infrastructure", "industry".
      * "importance_rank": (integer) Importance rank 1-10.
 
    Newsletter Summaries:
    {combined}"""
        
        try:
            resp = self.retry_with_backoff(
                lambda: self.model.generate_content(
                    prompt, 
                    generation_config={"temperature": 0.3}
                )
            )
 
            raw_text = resp.text if resp and resp.text else "{}"
            raw_text = self._repair_json(raw_text)
            
            data = json.loads(raw_text)
            commentary_themes = data.get("macro_themes", [])
            top_stories_data = data.get("top_stories", [])
            
            if top_stories_data:
                for story in top_stories_data:
                    story['tier'] = normalize_tier(story.get('tier'))
                    story['category'] = normalize_category(story.get('category'))
                    
                    sender_name = story.get('source_newsletter_sender')
                    matched_indices = self._find_all_sender_matches(sender_name, summaries)
                    
                    if matched_indices:
                        specific_link = None
                        best_summary = summaries[matched_indices[0]]
                        best_score_overall = 0.0
                        
                        # Check each matched summary for a specific matching link (e.g., if there are multiple issues)
                        for idx in matched_indices:
                            summary_obj = summaries[idx]
                            link, score = self._extract_specific_story_link(
                                story.get('title', ''),
                                story.get('news', ''),
                                summary_obj.get('summary_text', ''),
                                raw_links=summary_obj.get('raw_links', [])
                            )
                            if link and score > best_score_overall:
                                specific_link = link
                                best_summary = summary_obj
                                best_score_overall = score
                        
                        # Set to specific link if found, otherwise fallback to global newsletter link (sanitized)
                        # CRITICAL: Only allow global fallback links for single-topic newsletters/blogs.
                        # Curated/multi-topic digests should never use the global link as fallback because it leads to highly confusing, unrelated links.
                        fallback_link = ""
                        sender_lower = best_summary.get('sender', '').lower()
                        
                        # Define multi-topic senders that should NEVER fallback to global post URLs
                        multi_topic_senders = [
                            'tldr', 'tldr ai', 'ai breakfast', 'the neuron', 'the rundown ai', 
                            'alphasignal', "ben's bites", 'last week in ai', 'import ai', 'jack clark'
                        ]
                        
                        is_multi_topic = any(x in sender_lower for x in multi_topic_senders) or any(
                            keyword in sender_lower for keyword in ['digest', 'roundup', 'weekly', 'daily', 'curated']
                        )
                        
                        if not is_multi_topic:
                            fallback_link = best_summary.get('link') or ""
                            if fallback_link and not specific_link:
                                fallback_link = sanitize_url(fallback_link, resolve=True)
                                
                        story['source_url'] = specific_link or fallback_link or ""
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
                        'source_newsletter_sender': story.get('source_newsletter_sender', 'unknown'),
                        'contrarian_take': story.get('contrarian_take', ''),
                        'tier': story.get('tier', 'standard'),
                        'category': story.get('category', 'products'),
                        'date': logical_date
                    })
                
                # Save only the active 30-day window + new entries to disk
                updated_history = active_history + new_entries
                with open(HISTORY_FILE, 'w') as f: 
                    json.dump(updated_history, f, indent=2)
            
            return {
                "macro_themes": commentary_themes,
                "top_stories": top_stories_data
            }
        except Exception as e:
            logging.error(f"Error generating digest data: {e}")
            return {"macro_themes": [], "top_stories": []}

    def generate_linkedin_posts(self, summaries):
        """Generates 5 distinct algorithm-optimized LinkedIn post options based on daily news summaries."""
        combined = ""
        for i, item in enumerate(summaries):
            combined += f"Story {i+1}:\nSubject: {item['subject']}\nSummary: {item['summary_text']}\n\n"

        prompt = f"""Act as a seasoned tech founder, engineering leader, and principal strategist (writing with the sharp analytical depth of Ben Thompson / Stratechery or an opinionated startup CTO). 
        Write FIVE highly authentic, insightful, and readable posts for a professional technical audience on LinkedIn. 
        Each post must be grounded directly in the provided newsletter summaries.

    **Narrative Options (Generate exactly these 5 styles):**
    1. **Option 1: The Architectural Tradeoff**: Select a key technical development or release. Focus strictly on the underlying engineering trade-offs (e.g. latency vs accuracy, memory bandwidth vs model size, maintenance overhead vs custom code), NOT vendor product marketing.
    2. **Option 2: The Macro Market Shift**: Analyze how multiple stories connect to reveal broader industry dynamics, capital allocation, hardware vs software leverage, or open-source vs proprietary incentives (Stratechery style).
    3. **Option 3: The Operator's Utility Assessment**: Evaluate today's developments from a lead architect's perspective: what actually changes production workflows versus what is just hype or incremental noise.
    4. **Option 4: The 5-Slide PDF Carousel Strategy Outline**: Formatted as a 5-slide text template for a LinkedIn PDF Carousel (Slide 1: Hook Title -> Slide 2: Structural Context -> Slide 3: Engineering/Market Shift -> Slide 4: Strategic Impact -> Slide 5: Takeaway). Formatted with [Slide 1], [Slide 2], etc.
    5. **Option 5: The Contrarian Pattern Interrupt**: Open with a bold, counter-intuitive thesis that challenges popular tech consensus, driving a high-value discussion in the comments.

    **GOLD STANDARD APPROVED EXEMPLAR (Study this structure & tone):**
    ```
    Nvidia is officially replacing traditional venture capital with the equity + compute playbook.

    Nvidia just committed a reported $5 billion equity investment into Safe Superintelligence—plus a 10x compute boost on its next-gen Vera Rubin GPU platform—for a lab with zero commercial products on the market.

    This isn't an isolated deal, but an established circular financing engine:
    • CoreWeave: Equity backing paired with priority GPU allocations used as debt collateral.
    • Inflection AI & Mistral: Direct equity rounds tied to guaranteed hardware capacity.

    Traditional VCs evaluated user traction, unit economics, and early revenue metrics. Today, chipmakers bypass standard venture structures by funding research labs based almost entirely on founder pedigree.

    Does granting $5 billion and 10x compute to pre-product labs accelerate technical breakthroughs, or does it distort market dynamics by picking winners before product validation? Drop your perspective below. 📉

    (Link in comments)
    #VentureCapital #Semiconductors #Startups
    ```

    **CRITICAL ANTI-ADVERTISING & HUMAN HOOK RULES:**
    - **DEAL STRUCTURE PRECISION**: Distinguish accurately between equity investments (e.g. reported $5B) and hardware access (e.g. 10x compute scale boost on Vera Rubin). Use specific numbers ("10x compute boost", "reported $5 billion equity") rather than vague generalities.
    - **PATTERN & HISTORICAL CONTEXT**: When analyzing market shifts or strategy news, weave in relevant historical precedent and past examples (e.g. CoreWeave, Inflection, Mistral when discussing Nvidia compute deals) to ground the story in a broader pattern rather than a single isolated event.
    - **NATURAL HUMAN OPENERS (NO ACADEMIC JARGON)**: NEVER start posts with dense, robotic, or textbook economics jargon (BANNED: "Hardware vendors are systematically eating software distribution channels...", "Capital allocation strategies are decoupling from standard SaaS operational playbooks...", "Systemic market dynamics are shifting..."). Write the opening line using simple, direct, active English that a real founder or CTO would say out loud to a peer (e.g. "Nvidia is officially replacing traditional venture capital with the equity + compute playbook.").
    - **STRICTLY NO PR OR ADVERTORIAL TONE (BANNED)**: Do NOT write posts that sound like product announcements, press releases, or marketing pitches (e.g. NEVER start or structure a post like "Microsoft just released X model designed explicitly to solve Y"). Write as an independent analyst or CTO sharing strategic principles, not as a PR megaphone for tech vendors.
    - **CONTRAST STRUCTURE**: Contrast *How things used to work* vs *What is happening now* (as shown in the approved exemplar above).
    - **"See-More" Fold Hook**: The first 1-2 sentences (under 12 words) of every post MUST be a sharp, natural pattern interrupt designed to make users click "...see more".
    - **No Outbound Link Penalty**: Do NOT place raw external URLs inside the main post body text (LinkedIn suppresses post reach for outbound links). Append `(Link in comments)` at the end instead.
    - **No "Broetry" Formatting**: Write in clean, cohesive paragraphs (2-4 sentences per paragraph) with logical flow. Avoid single-sentence line-by-line spam.
    - **Factual Grounding**: Ground the posts in real technical facts, numbers, and names from the summaries without fluff.
    - **Story Diversity**: Ensure the 5 options explore distinct stories and diverse angles across the summaries.
    - **Tone**: Conversational, sharp, technical, and human (Stratechery / CTO talking to peers). Use active verbs and active voice.
    - **Emojis & Hashtags**: Use at most 1 emoji per post. Include exactly 3 relevant hashtags at the very end.

    **Formatting Rules (CRITICAL):**
    - NO meta-text, option labels (e.g. do NOT include "Option 1" headers), or conversational filler.
    - Separate the FIVE options using exactly: |||POST_SEPARATOR|||
    - **HUMAN-LIKE WRITING STANDARDS (CRITICAL)**:
      * Do NOT use em dashes (`—` or `--`) under any circumstances. Use commas, parentheses, or separate sentences.
      * Strictly avoid AI jargon and filler words. BANNED: *delve, tapestry, testament, pinnacle, cutting-edge, game-changer, revolutionary, groundbreaking, demystify, catalyst, beacon, underpins, underscores, moreover, furthermore, notably, transform, revolutionize, systematically, decoupling*.

    Summaries:
    {combined}"""
        
        try:
            # Enable Google Search Grounding exclusively for LinkedIn post generation
            try:
                search_model = genai.GenerativeModel('gemini-3.6-flash', tools='google_search_retrieval')
                resp = self.retry_with_backoff(
                    lambda: search_model.generate_content(
                        prompt, 
                        generation_config={"temperature": 0.5}
                    )
                )
            except Exception as search_err:
                logging.warning(f"Google Search Grounding failed for LinkedIn posts ({search_err}), falling back to standard model.")
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

    def generate_weekly_deep_dive(self, weekly_stories):
        """Analyzes a week of top stories and generates a structured tech-analyst deep dive essay."""
        combined = ""
        for i, story in enumerate(weekly_stories):
            combined += f"Story {i+1}:\nTitle: {story['title']}\nTag: {story.get('tag', '')}\nNews: {story['news']}\nImpact: {story['impact']}\nSender: {story.get('source_newsletter_sender', 'unknown')}\n\n"
            
        prompt = f"""You are a world-class technology strategist, venture capitalist, and chief analyst writing with the narrative depth and clear-headed structure of Ben Thompson's Stratechery and the editorial caliber of The Economist.
        
        Analyze the past week of AI & technology stories below and identify the **single most significant thematic storyline or trend** that dominated the industry. 
        
        Write a detailed, structured deep-dive essay on this topic. Your essay should be composed of exactly these three sections, written in clean markdown:
        
        1. **The Catalyst**: Detail the events that occurred this week, citing specific companies and decisions, to outline the facts of the situation.
        2. **Strategic Implications**: Analyze the structural shifts, market changes, developer friction, or economic calculations this theme exposes.
        3. **The Long-Term Outlook**: Provide a forward-looking, realistic forecast on where this trend lands in the next 1-5 years.
        
        **CRITICAL INSTRUCTIONS FOR ESSAY WRITING:**
        - Ground the essay deeply in the facts and numbers of the provided stories. Do NOT write vague, generic marketing summaries.
        - Write in an authoritative, analytical, and highly engaging editorial voice. Vary sentence lengths for narrative rhythm.
        - Do NOT include any meta-introductions (like "Here is your deep dive...") or conclusions outside the essay.
        - Do NOT include any ASCII drawings, block diagrams, or text-based charts. Rely strictly on clean, descriptive text paragraphs, bold terms, and structured bullet lists to explain concepts. The essay must look clean and readable on narrow mobile screens (like Telegram).
        - **HUMAN-LIKE WRITING STANDARDS (CRITICAL)**:
          * Do NOT use em dashes (`—` or `--`) under any circumstances. Use standard commas, parentheses, or separate sentences instead.
          * Strictly avoid AI jargon, filler, and transition buzzwords. BANNED words include: *delve, tapestry, testament, pinnacle, cutting-edge, game-changer, revolutionary, groundbreaking, demystify, catalyst, beacon, underpins, underscores, moreover, furthermore, notably, transform, revolutionize*.
          * Vary your sentence structures. Keep paragraph openers natural and direct.
          * Ground the writing in plain, direct facts. Eliminate all marketing hype and promotional fluff.
        
        **Output Format:**
        You MUST respond with ONLY valid JSON. Return a JSON object with EXACTLY these keys:
        - "topic_title": (string) A concise, highly punchy, and compelling title under 6-8 words max (e.g. "Pax Silica: The Geopolitical AI Cold War" or "The Sovereign AI Enclosure").
        - "essay_markdown": (string) The full markdown-formatted essay containing the three sections.
        
        Weekly Stories:
        {combined}"""
        
        try:
            resp = self.retry_with_backoff(
                lambda: self.model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.5,
                        "response_mime_type": "application/json",
                        "response_schema": {
                            "type": "OBJECT",
                            "properties": {
                                "topic_title": {"type": "STRING"},
                                "essay_markdown": {"type": "STRING"}
                            },
                            "required": ["topic_title", "essay_markdown"]
                        }
                    }
                )
            )
            raw_text = resp.text if resp and resp.text else "{}"
            raw_text = self._repair_json(raw_text)
            data = json.loads(raw_text)
            return {
                "topic_title": data.get("topic_title", "Weekly AI Strategy Deep Dive"),
                "essay_markdown": data.get("essay_markdown", "No analysis generated.")
            }
        except Exception as e:
            logging.error(f"Error generating weekly deep dive: {e}")
            return {
                "topic_title": "Weekly AI Strategy Deep Dive",
                "essay_markdown": "Failed to synthesize weekly analysis due to an error."
            }
