import base64
import logging
import os
import pickle
import socket
import select
import sys
import webbrowser
import urllib.parse
import wsgiref.simple_server
import wsgiref.util
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime, parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth import exceptions
from bs4 import BeautifulSoup, Comment

from config import SECRET_FILE, TOKEN_PICKLE_FILE, SCOPES
from utils import find_article_link

def get_gmail_service():
    logging.info("Entering get_gmail_service")
    creds = None
    try:
        if os.path.exists(TOKEN_PICKLE_FILE):
            with open(TOKEN_PICKLE_FILE, 'rb') as token:
                creds = pickle.load(token)
            logging.info(f"Loaded credentials from {TOKEN_PICKLE_FILE}")

        if creds and not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    logging.info("Refreshing expired token...")
                    creds.refresh(Request())
                    logging.info("Token refreshed successfully")
                except exceptions.RefreshError as e:
                    logging.warning(f"Token refresh failed: {e}. Re-authenticating...")
                    creds = None
        
        if not creds or not creds.valid:
            logging.info("No valid credentials found. Starting OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(SECRET_FILE, SCOPES)
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('localhost', 0))
            port = sock.getsockname()[1]
            sock.close()
            
            redirect_uri = f'http://localhost:{port}/'
            flow.redirect_uri = redirect_uri
            auth_url, _ = flow.authorization_url(access_type='offline')
            webbrowser.open(auth_url)
            
            auth_code = None
            def simple_app(environ, start_response):
                nonlocal auth_code
                query = wsgiref.util.request_uri(environ)
                parsed = urllib.parse.urlparse(query)
                params = urllib.parse.parse_qs(parsed.query)
                if 'code' in params:
                    auth_code = params['code'][0]
                    start_response('200 OK', [('Content-type', 'text/html')])
                    return [b'<html><h1>Authentication successful!</h1><p>You can close this window.</p><script>window.close()</script></html>']
                start_response('404 Not Found', [('Content-type', 'text/plain')])
                return [b'Not Found']

            server = wsgiref.simple_server.make_server('localhost', port, simple_app)
            logging.info(f"Listening for auth callback on port {port}...")
            
            inputs = [server.socket, sys.stdin]
            while auth_code is None:
                try:
                    readable, _, _ = select.select(inputs, [], [], 1.0)
                    if server.socket in readable:
                        server.handle_request()
                    if sys.stdin in readable:
                        line = sys.stdin.readline()
                        if not line:
                            inputs.remove(sys.stdin)
                        else:
                            line = line.strip()
                            if 'code=' in line:
                                try:
                                    parsed = urllib.parse.urlparse(line)
                                    params = urllib.parse.parse_qs(parsed.query)
                                    if 'code' in params:
                                        auth_code = params['code'][0]
                                except:
                                    logging.error("Failed to parse pasted URL")
                            elif line:
                                auth_code = line
                except (ValueError, OSError) as e:
                    logging.warning(f"Select failed ({e}), falling back to blocking server wait.")
                    server.handle_request()
            
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            logging.info("OAuth authentication completed")

        with open(TOKEN_PICKLE_FILE, 'wb') as token:
            pickle.dump(creds, token)
        logging.info(f"Saved credentials to {TOKEN_PICKLE_FILE}")
        return build('gmail', 'v1', credentials=creds)
    except Exception as e:
        logging.error(f"Error in get_gmail_service: {str(e)}")
        raise

def get_user_email(service):
    try:
        profile = service.users().getProfile(userId='me').execute()
        return profile['emailAddress']
    except HttpError as e:
        logging.error(f"Error getting user email: {e}")
        return None

def send_email(service, to, subject, html_body):
    user_email = get_user_email(service)
    if not user_email:
        logging.error("Could not determine user's email address. Sending cancelled.")
        return
    
    message = MIMEText(html_body, 'html')
    message['to'] = to
    message['From'] = user_email
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    try:
        message = (service.users().messages().send(userId='me', body={'raw': raw})
                   .execute())
        logging.info(f"Email sent successfully. Message Id: {message['id']}")
        return message
    except Exception as e:
        logging.error(f"An error occurred while sending email: {e}")

def fetch_newsletter_emails(service, window_start, window_end):
    logging.info(f"Checking for emails between {window_start} and {window_end}.")
    try:
        user_email = get_user_email(service)
        query = f"label:ai-newsletters newer_than:2d -from:{user_email}"
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        logging.info(f"Found {len(messages)} messages matching the filter.")
        
        filtered_emails = []
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()
            headers = msg['payload']['headers']
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')
            
            if date:
                date_obj = parsedate_to_datetime(date)
                if date_obj < window_start or date_obj >= window_end:
                    logging.info(f"Skipping email {message['id']} outside window.")
                    continue
            
            html_body = None
            plain_body = None
            parts_to_search = msg['payload'].get('parts', [msg['payload']])
            
            # Simple recursive search for bodies
            def find_bodies(parts):
                nonlocal html_body, plain_body
                for part in parts:
                    if part.get('mimeType') == 'text/html' and part.get('body', {}).get('data'):
                        html_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', 'ignore')
                    elif part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                        plain_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', 'ignore')
                    if part.get('parts'):
                        find_bodies(part.get('parts'))
            
            find_bodies(parts_to_search)
            
            message_body = ""
            article_link = None
            if html_body:
                soup = BeautifulSoup(html_body, 'html.parser')
                for element in soup(["script", "style", "header", "footer", "nav", "aside", "form"]):
                    element.decompose()
                for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                    comment.extract()
                message_body = soup.get_text(separator=' ', strip=True)
                article_link = find_article_link(soup)
            elif plain_body:
                message_body = plain_body
            
            if message_body:
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
                from_h = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
                sender_name, _ = parseaddr(from_h)
                
                filtered_emails.append({
                    'id': message['id'],
                    'subject': subject,
                    'sender': sender_name or 'Unknown Sender',
                    'body': message_body.strip(),
                    'link': article_link
                })
                logging.info(f"Found an email from '{sender_name}' with subject: {subject}")
        
        logging.info(f"Total filtered emails: {len(filtered_emails)}")
        return filtered_emails
    except Exception as e:
        logging.error(f"Error fetching emails: {e}")
        return []
