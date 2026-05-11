import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from dateutil import parser
import datetime
import pytz

# 1. Setup the Feed Metadata
fg = FeedGenerator()
fg.id('https://citizens-initiative-forum.europa.eu/discussion-forum_en')
fg.title('ECI Discussion Forum')
fg.link(href='https://citizens-initiative-forum.europa.eu/discussion-forum_en', rel='alternate')
fg.description('Community-driven full-text feed for the European Citizens\' Initiative Forum')
fg.language('en')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

# 2. Fetch the Main Forum List
base_url = "https://citizens-initiative-forum.europa.eu"
forum_url = f"{base_url}/discussion-forum_en?sort_type=recent"

response = requests.get(forum_url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

all_links = soup.find_all('a', href=True)
processed_urls = set()
count = 0

for link_tag in all_links:
    href = link_tag['href']
    if '/discussion-forum/idea/' in href:
        full_url = href if href.startswith('http') else base_url + href
        if full_url in processed_urls: continue
        title = link_tag.text.strip()
        if len(title) < 5: continue
        processed_urls.add(full_url)
        
        try:
            detail_res = requests.get(full_url, headers=headers)
            detail_soup = BeautifulSoup(detail_res.content, 'html.parser')
            
            # --- SCALPEL CLEANUP 1: Targeted System Phrase Removal ---
            # Instead of destroying text, we safely remove the specific HTML tags holding these phrases
            system_phrases = [
                "To be able to add comments",
                "The opinions expressed on the ECI Forum",
                "Want to support an initiative?",
                "Need to know more about current or past initiatives?"
            ]
            
            # Look at paragraphs, links, and small div blocks
            for tag in detail_soup.find_all(['p', 'span', 'a', 'em', 'small', 'div']):
                tag_text = tag.get_text(strip=True)
                # Safety check: Only delete if the block is small (so we don't accidentally delete the whole page)
                if len(tag_text) < 350: 
                    if any(phrase in tag_text for phrase in system_phrases):
                        tag.decompose()

            # --- SCALPEL CLEANUP 2: Remove the comment section & footer entirely ---
            cleanup_selectors = [
                '#comments', '.field--name-comment', '.comments-wrapper',
                'section[data-drupal-selector*="comment"]', '.add-comment-form', 
                '.ecl-footer'
            ]
            for selector in cleanup_selectors:
                for match in detail_soup.select(selector):
                    match.decompose()

            # --- EXTRACTION: Date ---
            pub_date = None
            date_tag = detail_soup.select_one('time, .field--name-created, span.date')
            if date_tag:
                # Try to get the formal datetime attribute first
                if date_tag.has_attr('datetime'):
                    try: 
                        pub_date = parser.parse(date_tag['datetime'])
                    except: pass
                # If that fails, read the text (using fuzzy=True to ignore words like "Submitted on")
                if not pub_date:
                    try: 
                        pub_date = parser.parse(date_tag.get_text(strip=True), fuzzy=True)
                    except: pass
            
            if not pub_date:
                pub_date = datetime.datetime.now(pytz.utc)

            # --- EXTRACTION: Author ---
            # We look for standard author classes or links to user profiles
            author_element = detail_soup.select_one('.field--name-field-author, .author, .username, [about*="/user/"]')
            author_name = author_element.get_text(strip=True) if author_element else "ECI Contributor"

            # --- EXTRACTION: Body ---
            content_block = detail_soup.select_one('.field--name-field-idea-description, .field--name-body, .node__content')
            
            if content_block:
                full_text = content_block.decode_contents()
            else:
                article_container = detail_soup.select_one('article') or detail_soup
                paragraphs = article_container.find_all('p')
                # Filter out tiny text chunks to keep the reading experience clean
                full_text = "<br><br>".join([p.decode_contents() for p in paragraphs if len(p.text.strip()) > 20])

            # 5. Add Entry to the Feed
            fe = fg.add_entry()
            fe.id(full_url)
            fe.title(title)
            fe.link(href=full_url)
            fe.author(name=author_name) 
            fe.content(full_text, type='html')
            fe.published(pub_date)
            
            count += 1
            if count >= 10: break
                
        except Exception as e:
            print(f"Error extracting {full_url}: {e}")
            continue

# 6. Save the XML File
fg.rss_file('feed.xml')
print(f"Done! feed.xml generated with {count} items.")
