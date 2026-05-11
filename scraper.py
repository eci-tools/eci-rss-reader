import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from dateutil import parser
import datetime
import pytz

# 1. Setup the Feed
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

# 2. Fetch the Forum List
base_url = "https://citizens-initiative-forum.europa.eu"
forum_url = f"{base_url}/discussion-forum_en?sort_type=recent"

response = requests.get(forum_url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

# 3. BULLETPROOF SEARCH: Look for ALL links pointing to an "idea"
all_links = soup.find_all('a', href=True)
processed_urls = set()
count = 0

for link_tag in all_links:
    href = link_tag['href']
    
    # We use the URL structure we know exists from your FiveFilters sample
    if '/discussion-forum/idea/' in href:
        full_url = href if href.startswith('http') else base_url + href
        
        # Skip duplicates (sites often link to the same article twice via images and titles)
        if full_url in processed_urls:
            continue
            
        title = link_tag.text.strip()
        
        # If the link is an image without text, skip it and wait for the text link
        if len(title) < 5: 
            continue

        processed_urls.add(full_url)
        print(f"Found Idea: {title}")
        
       try:
            # 4. Open the idea page to get the full text
            detail_res = requests.get(full_url, headers=headers)
            detail_soup = BeautifulSoup(detail_res.content, 'html.parser')
            
            # --- NEW CLEANUP STEP ---
            # Destroy the comments section before we start extracting text!
            # These are the standard Drupal/EU CSS IDs and classes for comments.
            for comment_area in detail_soup.select('#comments, .field--name-comment, section[data-drupal-selector*="comment"], .comments-wrapper'):
                comment_area.decompose()
            # ------------------------
            
            # Extract the main body content
            content_block = None
            possible_selectors = [
                '.field--name-field-idea-description', 
                '.field--name-body', 
                '.node__content > .clearfix.text-formatted', # Targets just the text, not the footer
                'article.node--type-idea .node__content'
            ]
            
            for selector in possible_selectors:
                content_block = detail_soup.select_one(selector)
                if content_block and len(content_block.text.strip()) > 50:
                    break 
            
            if content_block:
                full_text = content_block.decode_contents()
            else:
                # FALLBACK: grab paragraphs, but strictly inside the main article (ignores sidebars/menus)
                article_container = detail_soup.select_one('article, main') or detail_soup
                paragraphs = article_container.find_all('p')
                article_text = [p.decode_contents() for p in paragraphs if len(p.text.strip()) > 30]
                
                if article_text:
                    full_text = "<br><br>".join(article_text)
                else:
                    full_text = "Full text could not be extracted. Please click the link to read."

            # Find the date
            date_tag = detail_soup.select_one('time')
            if date_tag and date_tag.has_attr('datetime'):
                pub_date = parser.parse(date_tag['datetime'])
            else:
                pub_date = datetime.datetime.now(pytz.utc)

            # 5. Add to Feed
            fe = fg.add_entry()
            fe.id(full_url)
            fe.title(title)
            fe.link(href=full_url)
            fe.content(full_text, type='html')
            fe.published(pub_date)
            
            count += 1
            if count >= 10: # Stop after getting the 10 most recent
                break
                
        except Exception as e:
            print(f"Error extracting {full_url}: {e}")
            continue

# 6. Generate the file
fg.rss_file('feed.xml')
print(f"Successfully generated feed.xml with {count} items.")
