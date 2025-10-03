#!/usr/bin/env python3
"""
job_fetcher.py
Searches job boards for junior software/web dev roles in India and Saudi Arabia,
filters by experience and work mode, outputs CSV+HTML, and can email results.

Requirements:
  pip install requests beautifulsoup4 pandas python-dotenv
Set environment variables (or use .env):
  EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_USER, EMAIL_PASS, EMAIL_TO
"""
import os
import time
import csv
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from urllib.parse import urlencode, quote_plus

load_dotenv()

KEYWORDS = 'software engineer OR "web developer" OR web dev'
LOCATIONS = ['India', 'Saudi Arabia']
WORK_MODES = ['remote', 'hybrid', 'on-site']  # accept any of these
EXPERIENCE_KEYWORDS = ['junior', 'entry level', 'entry-level', 'graduate', 'intern']  # used for filtering

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; job-fetcher/1.0; +https://example.com/bot)'
}

def matches_experience(text):
    t = text.lower()
    return any(k in t for k in EXPERIENCE_KEYWORDS)

def matches_work_mode(text):
    t = text.lower()
    # Accept any of configured modes OR presence of "remote" / "hybrid" / "on-site" synonyms
    return any(m in t for m in WORK_MODES)

def parse_indeed(location):
    """Query Indeed (public search page). Returns list of dicts."""
    results = []
    q = KEYWORDS
    base = 'https://www.indeed.com/jobs'
    # Indeed's query parameter 'q' 'l'
    params = {'q': q, 'l': location, 'fromage': '3'}  # 'fromage' restricts to last 3 days
    url = f"{base}?{urlencode(params, quote_via=quote_plus)}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        print("Indeed fetch failed:", r.status_code)
        return results
    soup = BeautifulSoup(r.text, 'html.parser')
    for card in soup.select('.jobsearch-SerpJobCard, .result'):
        title_el = card.select_one('h2.title, h2.jobTitle')
        title = title_el.get_text(strip=True) if title_el else 'N/A'
        company = (card.select_one('.company') or card.select_one('.companyName'))
        company = company.get_text(strip=True) if company else 'N/A'
        loc = (card.select_one('.location') or card.select_one('.companyLocation'))
        loc = loc.get_text(strip=True) if loc else location
        link_el = card.select_one('a')
        link = 'https://www.indeed.com' + link_el['href'] if link_el and link_el.get('href') else url
        summary = (card.select_one('.summary') or card.select_one('.job-snippet'))
        summary_text = summary.get_text(" ", strip=True) if summary else ''
        # Basic filtering
        if matches_experience(title + ' ' + summary_text) or matches_experience(company):
            results.append({
                'title': title, 'company': company, 'location': loc, 'salary': 'N/A',
                'link': link, 'source': 'Indeed', 'summary': summary_text
            })
    return results

def parse_wellfound(location):
    """Simple AngelList (Wellfound) search using their public search page."""
    results = []
    base = 'https://wellfound.com/jobs'
    # Wellfound's web UI uses querystrings like '?search[locations][]=' for location
    params = {'search[query]': KEYWORDS, 'search[locations][]': location}
    url = f"{base}?{urlencode(params)}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        print("Wellfound fetch failed:", r.status_code)
        return results
    soup = BeautifulSoup(r.text, 'html.parser')
    for job in soup.select('li[data-test="job-card"]')[:30]:
        title = job.select_one('a[data-test="job-link"]') and job.select_one('a[data-test="job-link"]').get_text(strip=True)
        company = job.select_one('[data-test="job-card-company-name"]')
        company = company.get_text(strip=True) if company else 'N/A'
        link_el = job.select_one('a[data-test="job-link"]')
        link = 'https://wellfound.com' + link_el['href'] if link_el else url
        summary = job.get_text(" ", strip=True)
        if matches_experience(title + ' ' + summary):
            results.append({
                'title': title, 'company': company, 'location': location, 'salary': 'N/A',
                'link': link, 'source': 'Wellfound', 'summary': summary
            })
    return results

def parse_glassdoor(location):
    """Glassdoor scraping is limited; return empty or basic approach."""
    # Glassdoor often blocks scraping; recommend using Glassdoor alerts or API.
    print("Glassdoor: recommended to use Glassdoor alerts or their API due to scraping protections.")
    return []

def parse_linkedin(location):
    """LinkedIn scraping is brittle and often requires an authenticated session.
       Recommend using LinkedIn job alerts or the LinkedIn API.
    """
    print("LinkedIn: recommend using LinkedIn job alerts or official API (scraping discouraged).")
    return []

def consolidate_and_filter(entries):
    # Remove duplicates by link, keep relevant modes if detected
    seen = set()
    filtered = []
    for e in entries:
        if e['link'] in seen:
            continue
        seen.add(e['link'])
        # Accept only junior/entry-level matches
        text = (e.get('title','') + ' ' + e.get('summary','')).lower()
        if matches_experience(text):
            filtered.append(e)
    return filtered

def save_results(results):
    if not results:
        print("No results to save.")
        return
    df = pd.DataFrame(results)
    df = df[['title','company','salary','link','source','location']]
    df.to_csv('jobs.csv', index=False)
    # produce simple HTML table
    html = df.to_html(index=False, escape=True)
    with open('jobs.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Saved {len(df)} jobs to jobs.csv and jobs.html")

def send_email_with_attachments(subject="Daily Jobs", body="See attached", attachments=None):
    # Example using smtplib
    import smtplib, ssl
    from email.message import EmailMessage
    SMTP_HOST = os.getenv('EMAIL_SMTP_HOST')
    SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', 587))
    USER = os.getenv('EMAIL_USER')
    PASS = os.getenv('EMAIL_PASS')
    TO = os.getenv('EMAIL_TO')  # comma-separated
    if not (SMTP_HOST and USER and PASS and TO):
        print("Email not configured; skipping email send.")
        return
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = USER
    msg['To'] = TO
    msg.set_content(body)
    # attach CSV
    if attachments:
        for path in attachments:
            with open(path, 'rb') as f:
                data = f.read()
            msg.add_attachment(data, maintype='application', subtype='octet-stream', filename=os.path.basename(path))
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls(context=context)
        smtp.login(USER, PASS)
        smtp.send_message(msg)
    print("Email sent to", TO)

def main():
    entries = []
    for loc in LOCATIONS:
        entries += parse_indeed(loc)
        entries += parse_wellfound(loc)
        entries += parse_glassdoor(loc)  # probably empty
        entries += parse_linkedin(loc)   # probably empty
        time.sleep(1)
    results = consolidate_and_filter(entries)
    save_results(results)
    # Optionally email
    if results:
        send_email_with_attachments(subject="Daily Junior Software/Web Jobs", body="Attached: jobs.csv and jobs.html", attachments=['jobs.csv','jobs.html'])

if __name__ == "__main__":
    main()
