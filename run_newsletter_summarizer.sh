#!/bin/bash
cd "/Users/chakshugrover/newsletter_summarizer/" || exit 1
/Users/chakshugrover/newsletter_summarizer/.venv/bin/python main.py >> newsletter_summarizer.log 2>&1
