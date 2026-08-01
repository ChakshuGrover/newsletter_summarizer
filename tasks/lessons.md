# Lessons Learned

## Substack Link Redirection & Resolution
- **Pattern**: Substack tracking redirect URLs (`substack.com/redirect/...` or `substack.com/app-link/...`) return a Cloudflare challenge page (status 200) instead of a HTTP 302 redirect when requested using a full browser user-agent.
- **Resolution**: Use a simple User-Agent (`Mozilla/5.0`) when resolving Substack links. This triggers a standard HTTP 302 redirect that the `requests` library can follow automatically to resolve redirects to clean web URLs (like GitHub repositories or actual articles).

## Daily Digest Content Quality
- **Pattern**: Weekly newsletters (like Import AI or Ben Evans) summarize industry events that occurred 5-7 days ago, which readers who track daily news will perceive as "old news."
- **Resolution**: Strengthen prompt recentness constraints. Instruct the AI to explicitly filter out events older than 4 days, focusing exclusively on active, fresh news that broke within the last 72 hours.

## Rate Limit Optimization
- **Pattern**: Manual pipeline dry-runs on live data consume a batch of API calls (summarization chunking, consolidation, and output formatting). Running multiple manual executions back-to-back quickly depletes free-tier daily quotas (20 RPD limit).
- **Resolution**: Group summaries in larger chunks where possible and limit the frequency of manual forced runs. Advise users that daily automated operations remain well within the free quota limits.

## HubSpot / DeepLearning.ai Link Redirection & Resolution
- **Pattern**: HubSpot click-tracking URLs (containing `/e3t/` in the path) serve a JavaScript-based browser fingerprinting challenge (status 200) instead of standard HTTP redirects.
- **Resolution**: Perform a GET request to the tracking link, parse the response body using regex to extract the target URL, replace the fingerprinting query state `_jss=-2` with `_jss=1` (or trailing `-2` with `1`), and make a second request to follow the actual HTTP 307 redirect. Additionally, include `_hsenc` and `_hsmi` in the sanitization configuration to strip the long tracking parameters from the resolved target URL.
