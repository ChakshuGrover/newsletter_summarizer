# Task Plan: Expand to 5 Daily LinkedIn Post Options & Reach Optimization

## Objective
Upgrade `generate_linkedin_posts()` in `ai_summarizer.py` to produce **5 distinct daily post drafts** tailored for Chakshu Grover, including a PDF Carousel format, formatted for 1-tap copying on Telegram.

---

## Daily 5-Draft Matrix
1. **Option 1: The Technical Breakdown** (Engineering trade-offs, architecture, and technical mechanics).
2. **Option 2: The Strategic Shift** (Synthesis of market dynamics, competitive positioning, open vs proprietary).
3. **Option 3: The Pragmatic Builder's Take** (Utility vs noise for tech leads & founders).
4. **Option 4: The 5-Slide PDF Carousel Outline** (Slide 1: Hook Title -> Slides 2-4: Core Insights -> Slide 5: Strategic Takeaway & CTA).
5. **Option 5: The Pattern Interrupt / Discussion Starter** (Contrarian hot take designed to drive high comment section velocity).

---

## Action Items
- [x] **1. Upgrade `generate_linkedin_posts` in `ai_summarizer.py`**:
  - Update prompt to generate 5 distinct post options.
  - Incorporate "See More" fold optimization (first 15 words trigger curiosity/click).
  - Add Option 4 (PDF Carousel outline format).
  - Add Option 5 (Pattern interrupt / discussion starter).
  - Keep link body rules clean (`(Link in comments)`).
- [x] **2. Telegram 1-Tap Copy Formatting in `main.py`**:
  - Wrap each generated post option in `<pre>...</pre>` tags for Telegram dispatch.
  - When copied from Telegram, plain text is placed on the system clipboard without any HTML tags.
- [x] **3. Verification & Testing**:
  - Run test generation with a scratch script to verify all 5 options format cleanly.
  - Check Telegram `<pre>` output and post diversity.

---

## Review & Results
- **Dry-Run Successfully Executed**: Generated 5 distinct LinkedIn post options using live mock newsletter data.
- **Diversity Verified**: Each option focuses on different news angles (Option 1: Llama 3.3 70B inference tech, Option 2: Hardware cooling vs model compression macro shift, Option 3: OpenAI Operator practical utility, Option 4: 5-Slide PDF Carousel outline, Option 5: Contrarian frontier model hot take).
- **Telegram Formatting Ready**: Updated `main.py` so options sent to `TELEGRAM_LINKEDIN_CHAT_ID` are wrapped in `<pre>` tags with clear option headers for 1-tap copy/pasting.
