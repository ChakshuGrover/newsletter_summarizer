import logging
import urllib.parse
import requests
from bs4 import BeautifulSoup

def resolve_redirects(url):
    """Resolve tracking links to their final destination URL using a browser User-Agent."""
    redirectors = ['link.mail', 'click.mail', 't.mail', 'tracking.tldrnewsletter.com', 'ben-evans.us6.list-manage.com', 'alphasignal.ai']
    if any(d in url.lower() for d in redirectors):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        try:
            # Many tracking servers require a GET request to process the redirect properly
            response = requests.get(url, allow_redirects=True, timeout=5, headers=headers)
            return response.url
        except Exception as e:
            logging.debug(f"Failed to resolve redirect for {url}: {e}")
    return url

def sanitize_url(url, resolve=False):
    """Clean up a URL by removing newlines, whitespace, and tracking parameters."""
    if not url:
        return url
    
    # 1. Remove newlines and whitespace (both literal and URL-encoded)
    url = url.replace('\n', '').replace('\r', '').replace('%0A', '').replace('%0D', '').strip()
    
    # 2. Resolve tracking redirects to get the real article URL (only if requested)
    if resolve:
        url = resolve_redirects(url)
    
    # 3. Remove tracking parameters
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        
        # Parameters to strip
        unwanted = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'redirect', '_bhlid', '_bhcp', 'jwt_token']
        
        # Filter out any key that starts with utm_ or is in our unwanted list
        clean_query = {k: v for k, v in query.items() if not k.startswith('utm_') and k not in unwanted}
        
        # Rebuild URL
        new_query = urllib.parse.urlencode(clean_query, doseq=True)
        url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
    except Exception as e:
        logging.error(f"Error sanitizing URL {url}: {e}")
        
    return url

def find_article_link(soup, sender_name=None):
    """Search for the main article link in email body."""
    logging.debug("Searching for main article link in email body.")
    
    # 0. Check for canonical link in metadata first (often the cleanest URL)
    canonical = soup.find('link', rel='canonical')
    if canonical and canonical.get('href'):
        return sanitize_url(canonical.get('href'), resolve=True)
    
    # Also check meta tags (common in Beehiiv/Substack)
    og_url = soup.find('meta', property='og:url')
    if og_url and og_url.get('content'):
        return sanitize_url(og_url.get('content'), resolve=True)

    priority_texts = ['view online', 'read online', 'view in browser', 'read in browser', 'read the full story', 'view this email online']
    secondary_texts = ['read more', 'continue reading', 'full story']
    
    all_links = soup.find_all('a', href=True)
    
    def is_tracking_redirect(url):
        # Domains that typically serve only as redirectors
        redirectors = ['link.mail', 'click.mail', 't.mail', 'list-manage', 'forward-to-friend', 'doubleclick.net', 'tracking.tldrnewsletter.com']
        return any(d in url.lower() for d in redirectors)

    # Detect if the email has a primary domain based on sender
    sender_domain_kw = None
    if sender_name:
        sender_lower = sender_name.lower()
        if 'ben thompson' in sender_lower or 'stratechery' in sender_lower:
            sender_domain_kw = 'stratechery.com'
        elif 'zain kahn' in sender_lower or 'superhuman' in sender_lower:
            sender_domain_kw = 'superhuman.ai'
        elif 'neuron' in sender_lower:
            sender_domain_kw = 'theneurondaily.com'
        elif 'breakfast' in sender_lower:
            sender_domain_kw = 'aibreakfast'

    # 1. Best Case: Look for a non-tracking "View online" / "View in browser" priority text link
    for text in priority_texts:
        for link in all_links:
            anchor_text = link.get_text().lower() if link.get_text() else ""
            if text in anchor_text:
                href = link.get('href')
                if href:
                    href = href.replace('\n', '').replace('\r', '').strip()
                    if not is_tracking_redirect(href):
                        if not sender_domain_kw or sender_domain_kw in href.lower():
                            return sanitize_url(href, resolve=True)

    # 2. Look for a non-tracking link that contains /p/ or /posts/ AND matches the sender domain keyword if available
    for link in all_links:
        href = link.get('href')
        if not href: continue
        href = href.replace('\n', '').replace('\r', '').strip()
        
        if not is_tracking_redirect(href) and ('/p/' in href or '/posts/' in href):
            if 'subscribe' not in href and 'comment' not in href:
                if not sender_domain_kw or sender_domain_kw in href.lower():
                    return sanitize_url(href, resolve=True)

    # 3. Fallback to priority text matches (even tracking ones)
    matches = []
    for text in priority_texts:
        for link in all_links:
            anchor_text = link.get_text().lower() if link.get_text() else ""
            if text in anchor_text:
                href = link.get('href')
                if href:
                    href = href.replace('\n', '').replace('\r', '').strip()
                    if sender_domain_kw and sender_domain_kw in href.lower():
                        return sanitize_url(href, resolve=True)
                    matches.append(href)
    if matches:
        return sanitize_url(matches[0], resolve=True)

    # 4. Search for secondary text matches
    for text in secondary_texts:
        for link in all_links:
            anchor_text = link.get_text().lower() if link.get_text() else ""
            if text in anchor_text:
                href = link.get('href')
                if href:
                    href = href.replace('\n', '').replace('\r', '').strip()
                    if not is_tracking_redirect(href):
                        if not sender_domain_kw or sender_domain_kw in href.lower():
                            return sanitize_url(href, resolve=True)
                    matches.append(href)
    if matches:
        return sanitize_url(matches[0], resolve=True)

    # 5. Fallback: Search for any link that looks like a primary article
    best_fallback = None
    for link in all_links:
        href = link.get('href')
        if not href: continue
        href = href.replace('\n', '').replace('\r', '').strip()
        
        text = link.get_text().lower() if link.get_text() else ""
        
        if any(x in text for x in ['unsubscribe', 'privacy', 'preferences', 'update']):
            continue
        if any(x in href.lower() for x in ['facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com']):
            continue
            
        if not is_tracking_redirect(href):
            if sender_domain_kw and sender_domain_kw in href.lower():
                return sanitize_url(href, resolve=True)
            if 'article' in href.lower() and not best_fallback:
                best_fallback = href
            elif not best_fallback:
                best_fallback = href
                
    if best_fallback:
        return sanitize_url(best_fallback, resolve=True)
    elif all_links:
        return sanitize_url(all_links[0].get('href'), resolve=True)
    return None
