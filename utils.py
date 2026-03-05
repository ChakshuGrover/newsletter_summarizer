import logging
from bs4 import BeautifulSoup

def find_article_link(soup):
    """Search for the main article link in email body."""
    logging.debug("Searching for main article link in email body.")
    link_texts = ['read more', 'view online', 'view in browser', 'continue reading', 'read the full story']
    for text in link_texts:
        link = soup.find('a', string=lambda t: t and text in t.lower())
        if link and link.get('href'):
            return link.get('href')

    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if not href:
            continue
        link_text = link.get_text().lower()
        if 'unsubscribe' not in link_text and 'privacy' not in link_text and 'facebook.com' not in href and 'twitter.com' not in href and 'linkedin.com' not in href:
            if href.startswith('http'):
                return href
    return None
