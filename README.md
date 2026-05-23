# Newsletter Summarizer

An automated tool that curates, summarizes, and digests AI and tech newsletters from your Gmail, delivering a clean daily summary and even preparing social media content.

## Features

- **Smart Filtering**: Automatically fetches emails with the `ai-newsletters` label from Gmail.
- **AI-Powered Summarization**: Uses Google's Gemini API (`gemini-3.5-flash`) to generate concise, bulleted summaries of each newsletter.
- **Daily Digest**: Compiles all summaries into a single, well-formatted HTML email and sends it to a designated recipient.
- **LinkedIn Content Generation**: Automatically drafts three different styles of LinkedIn posts based on the daily news.
- **Telegram Integration**: Delivers the LinkedIn post drafts directly to your Telegram for easy copy-pasting.
- **Robust Execution**: Includes rate limiting, exponential backoff, and API key rotation to handle API quotas effectively.

## Project Structure

- `main.py`: The core logic for fetching, summarizing, and distributing content.
- `run_newsletter_summarizer.sh`: A shell script to execute the summarizer (ideal for cron jobs or launchd).
- `requirements.txt`: Python dependencies.
- `credentials.json`: Google Cloud project credentials (user-provided).
- `token.pickle`: Stored Gmail OAuth tokens after the first successful authentication.
- `.env`: Environment variables for API keys and configurations.

## Setup

### 1. Prerequisites
- Python 3.12+
- A Google Cloud Project with the Gmail API enabled.
- Google Gemini API Key(s).
- (Optional) A Telegram Bot for notifications.

### 2. Installation
```bash
# Clone the repository
git clone <repository-url>
cd newsletter-summarizer

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory with the following:
```env
GEMINI_API_KEY=your_primary_gemini_api_key
GEMINI_API_KEY_2=your_secondary_gemini_api_key (optional)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

Place your `credentials.json` from the Google Cloud Console in the root directory.

### 4. Authentication
Run the script manually for the first time to complete the Gmail OAuth flow:
```bash
python main.py
```
This will open a browser window for you to log in and authorize the application. A `token.pickle` file will be created to save your credentials.

## Usage

### Manual Run
```bash
python main.py
```

### Command Line Arguments
- `--days-offset`: Number of days to go back for the target window (default: 0).
- `--force`: Bypass the `last_run_date.txt` check and run anyway.

### Automation
You can use the provided `run_newsletter_summarizer.sh` script to schedule the summarizer. On macOS, you can set up a `launchd` agent; on Linux, use a `cron` job.

## Logs
The script logs its activity to `filter.log`, while `launchd.log` and `launchd.err` capture execution details when run via the shell script.
