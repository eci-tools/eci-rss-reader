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
            
            # --- SCALPEL CLEANUP: Targeted System Phrase Removal ---
            system_phrases = [
                "To be able to add comments",
                "The opinions expressed on the ECI Forum",
                "Want to support an initiative?",
                "Need to know more about current or past initiatives?"
            ]
            # Safely remove only the specific small paragraphs holding these phrases
            for tag in detail_soup.find_all(['p', 'div', 'span', 'em']):
                text = tag.get_text(strip=True)
                if 0 < len(text) < 300: 
                    if any(phrase in text for phrase in system_phrases):
                        tag.decompose()

            # --- FEATURE: Extract & Separate Comments ---
            comments_html = ""
            comment_section = detail_soup.select_one('#comments, .comments-wrapper, section[data-drupal-selector*="comment"]')
            
            if comment_section:
                comments = comment_section.select('article.comment, .comment')
                if comments:
                    # Create a nice visual break for the comments section
                    comments_html = "<br><br><hr><h3>Community Discussion:</h3>"
                    for c in comments:
                        c_author = c.select_one('.username, .author, .field--name-uid')
                        c_author_text = c_author.get_text(strip=True) if c_author else "Anonymous"
                        
                        c_body = c.select_one('.field--name-comment-body, .content')
                        c_body_text = c_body.decode_contents() if c_body else c.get_text(separator="<br>")
                        
                        # Format each comment with a slight indent and a grey line on the left
                        comments_html += f"<div style='margin-bottom: 15px; padding-left: 15px; border-left: 3px solid #ccc;'><b>{c_author_text}</b><br>{c_body_text}</div>"
                
                # CRITICAL: Destroy the comment section so it doesn't bleed into the main text!
                comment_section.decompose()

            # --- EXTRACTION: Author ---
            author_element = detail_soup.select_one('.field--name-field-author, .author, .username, [about*="/user/"]')
            author_name = author_element.get_text(strip=True) if author_element else "ECI Contributor"

            # --- EXTRACTION: Date ---
            pub_date = None
            date_tag = detail_soup.select_one('time, .field--name-created, span.date')
            if date_tag:
                try:
                    if date_tag.has_attr('datetime'):
                        pub_date = parser.parse(date_tag['datetime'])
                    elif date_tag.has_attr('content'):
                        pub_date = parser.parse(date_tag['content'])
                    else:
                        pub_date = parser.parse(date_tag.get_text(strip=True), fuzzy=True)
                except: pass
            
            if not pub_date:
                pub_date = datetime.datetime.now(pytz.utc)
                
            # Timezone Safety Check (Fixes the missing dates issue!)
            if pub_date.tzinfo is None:
                pub_date = pytz.utc.localize(pub_date)

            # --- EXTRACTION: Body ---
            content_block = detail_soup.select_one('.field--name-field-idea-description, .field--name-body, .node__content')
            if content_block:
                main_text = content_block.decode_contents()
            else:
                article_container = detail_soup.select_one('article.node--type-idea, main, .region-content') or detail_soup
                paragraphs = article_container.find_all('p')
                main_text = "<br><br>".join([p.decode_contents() for p in paragraphs if len(p.get_text(strip=True)) > 20])

            # Combine the Main Article and the Formatted Comments
            full_text = main_text + comments_html

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
