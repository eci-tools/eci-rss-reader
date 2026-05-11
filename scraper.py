import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from dateutil import parser
import datetime
import pytz
import re

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
            
            # --- CLEANUP 1: Remove defined comment and system blocks ---
            cleanup_selectors = [
                '#comments', '.field--name-comment', '.comments-wrapper',
                'section[data-drupal-selector*="comment"]', '.add-comment-form',
                '.ecl-footer', '.ecl-header', 'nav'
            ]
            for selector in cleanup_selectors:
                for match in detail_soup.select(selector):
                    match.decompose()

            # --- EXTRACTION: Find the Article Body ---
            content_block = detail_soup.select_one('.field--name-field-idea-description, .field--name-body, .node__content')
            
            if content_block:
                # Get the HTML
                full_text = content_block.decode_contents()
            else:
                # Fallback to general content
                article_container = detail_soup.select_one('article') or detail_soup
                paragraphs = article_container.find_all('p')
                full_text = "<br><br>".join([p.decode_contents() for p in paragraphs if len(p.text.strip()) > 20])

            # --- CLEANUP 2: Remove specific "System Sentences" via RegEx ---
            # This removes the "To be able to add comments" and "The opinions expressed" blocks
            system_phrases = [
                r"To be able to add comments, you need to authenticate or register\.",
                r"The opinions expressed on the ECI Forum reflect solely the point of view.*",
                r"Want to support an initiative\?.*",
                r"Need to know more about current or past initiatives\?.*"
            ]
            for phrase in system_phrases:
                full_text = re.sub(phrase, "", full_text, flags=re.IGNORECASE | re.DOTALL)

            # --- AUTHOR EXTRACTION ---
            # On the detail page, authors are usually in a field called "field--name-field-author"
            author_element = detail_soup.select_one('.field--name-field-author, .author, .username')
            author_name = author_element.text.strip() if author_element else "ECI Contributor"

            # Find Publication Date
            date_tag = detail_soup.select_one('time')
            pub_date = parser.parse(date_tag['datetime']) if date_tag and date_tag.has_attr('datetime') else datetime.datetime.now(pytz.utc)

            # 5. Add Entry to the Feed
            fe = fg.add_entry()
            fe.id(full_url)
            fe.title(title)
            fe.link(href=full_url)
            fe.author(name=author_name) # This adds the author back!
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
