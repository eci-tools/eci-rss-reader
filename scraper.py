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

# We use headers to appear like a standard web browser
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

# 2. Fetch the Main Forum List
base_url = "https://citizens-initiative-forum.europa.eu"
forum_url = f"{base_url}/discussion-forum_en?sort_type=recent"

print(f"Fetching forum list from: {forum_url}")
response = requests.get(forum_url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

# 3. Find Idea Links
# This looks for all links that follow the "idea" URL structure
all_links = soup.find_all('a', href=True)
processed_urls = set()
count = 0

for link_tag in all_links:
    href = link_tag['href']
    
    # Target only links that lead to actual Ideas
    if '/discussion-forum/idea/' in href:
        full_url = href if href.startswith('http') else base_url + href
        
        # Avoid processing the same link twice
        if full_url in processed_urls:
            continue
            
        title = link_tag.text.strip()
        
        # Ensure it's a text link and not just a linked image or icon
        if len(title) < 5: 
            continue

        processed_urls.add(full_url)
        print(f"Processing: {title}")
        
        try:
            # 4. Open the Idea page to extract full content
            detail_res = requests.get(full_url, headers=headers)
            detail_soup = BeautifulSoup(detail_res.content, 'html.parser')
            
            # --- CLEANUP: Remove Comments and User Interactions ---
            # We "decompose" these so they aren't accidentally grabbed by the text scraper
            cleanup_selectors = [
                '#comments', 
                '.field--name-comment', 
                '.comments-wrapper',
                'section[data-drupal-selector*="comment"]',
                '.add-comment-form'
            ]
            for selector in cleanup_selectors:
                for match in detail_soup.select(selector):
                    match.decompose()
            
            # --- EXTRACTION: Find the Article Body ---
            content_block = None
            possible_selectors = [
                '.field--name-field-idea-description', 
                '.field--name-body', 
                '.node__content > .clearfix.text-formatted',
                'article.node--type-idea .node__content'
            ]
            
            for selector in possible_selectors:
                content_block = detail_soup.select_one(selector)
                # Check if we found a block with a reasonable amount of content
                if content_block and len(content_block.text.strip()) > 50:
                    break 
            
            if content_block:
                full_text = content_block.decode_contents()
            else:
                # NUCLEAR FALLBACK: Extract all paragraphs within the main container
                article_container = detail_soup.select_one('article, main') or detail_soup
                paragraphs = article_container.find_all('p')
                # Filter out tiny text chunks to avoid grabbing UI buttons or footer links
                article_text = [p.decode_contents() for p in paragraphs if len(p.text.strip()) > 30]
                
                if article_text:
                    full_text = "<br><br>".join(article_text)
                else:
                    full_text = "Full text could not be extracted. Please click the link to read the original article."

            # Find Publication Date
            date_tag = detail_soup.select_one('time')
            if date_tag and date_tag.has_attr('datetime'):
                pub_date = parser.parse(date_tag['datetime'])
            else:
                pub_date = datetime.datetime.now(pytz.utc)

            # 5. Add Entry to the Feed
            fe = fg.add_entry()
            fe.id(full_url)
            fe.title(title)
            fe.link(href=full_url)
            fe.content(full_text, type='html')
            fe.published(pub_date)
            
            count += 1
            if count >= 10: # Limits feed to the top 10 most recent posts
                break
                
        except Exception as e:
            print(f"Error extracting {full_url}: {e}")
            continue

# 6. Save the XML File
fg.rss_file('feed.xml')
print(f"Done! feed.xml generated with {count} items.")
