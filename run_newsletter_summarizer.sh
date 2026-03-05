#!/bin/bash
cd "/Users/chakshugrover/newsletter_summarizer/" || exit 1
>> launchd.log
>> launchd.err
>> filter.log
/Users/chakshugrover/newsletter_summarizer/.venv/bin/python main.py 