# Lessons Learned

## Substack Link Redirection & Resolution
- **Pattern**: Substack tracking redirect URLs (`substack.com/redirect/...` or `substack.com/app-link/...`) return a Cloudflare challenge page (status 200) instead of a HTTP 302 redirect when requested using a full browser user-agent.
- **Resolution**: Use a simple User-Agent (`Mozilla/5.0`) when resolving Substack links. This triggers a standard HTTP 302 redirect that the `requests` library can follow automatically to resolve redirects to clean web URLs.

## Daily Digest Content Quality
- **Pattern**: Weekly newsletters summarize events 5-7 days ago, perceived as "old news."
- **Resolution**: Filter out events older than 4 days, focusing on news that broke within 72 hours.

## LinkedIn Reach & Content Quality (CRITICAL)
- **Human Conversational Openers (NO Clinical Academic Jargon)**: Never start posts with dense, textbook jargon like "Hardware vendors are systematically eating software distribution channels..." or "Capital allocation strategies are decoupling...". Write like a real human engineer/founder talking directly to peers—use simple, punchy, active English ("Hardware companies are taking over the AI stack. The old SaaS playbook doesn't work anymore.").
- **Anti-PR / No Advertorials**: Never write posts that sound like a press release or product advertisement for tech giants ("Microsoft just released X...", "Company Y solves Z"). Focus on the engineering tradeoff, architectural insight, or real developer decision.
- **Preferred Persona & Style**: High-level structural market & engineering analysis (Ben Thompson / Stratechery style). Content analyzing capital allocation, hardware vs software incentives, open-source economics, and infrastructure bottlenecks is heavily preferred by the user.
- **Content Freshness**: Vary daily themes so consecutive daily runs don't repeat the same macro narrative angle.
