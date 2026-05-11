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

# Look for the article cards directly on the main page
articles = soup.select('article.ecl-card')
count = 0

for article in articles[:10]:
    try:
        # --- EXTRACT LINK & TITLE ---
        a_tag = article.select_one('.ecl-content-block__title a')
        if not a_tag: continue
        title = a_tag.text.strip()
        link = a_tag['href']
        full_url = link if link.startswith('http') else base_url + link
        
        # --- EXTRACT AUTHOR (Directly from main page) ---
        author_div = article.select_one('.ecl-content-block__description .ecl-u-mb-l')
        author_name = author_div.text.strip() if author_div else "ECI Contributor"
        
        # --- EXTRACT DATE (Directly from main page) ---
        date_li = article.select_one('.ecl-content-block__primary-meta-item')
        pub_date = None
        if date_li:
            try:
                pub_date = parser.parse(date_li.text.strip())
                if pub_date.tzinfo is None:
                    pub_date = pytz.utc.localize(pub_date)
            except: pass
        if not pub_date:
            pub_date = datetime.datetime.now(pytz.utc)

        # --- 4. FETCH DETAIL PAGE FOR FULL TEXT ---
        detail_res = requests.get(full_url, headers=headers)
        detail_soup = BeautifulSoup(detail_res.content, 'html.parser')
        
        # --- 5. EXTRACT & FORMAT COMMENTS ---
        comments_html = ""
        comment_divs = detail_soup.select('div[id^="comment-"]')
        
        if comment_divs:
            comments_html += "<br><br><hr><h3>Community Discussion:</h3>"
            for c in comment_divs:
                info_div = c.select_one('.ecl-u-mb-s')
                c_info = info_div.text.replace('\n', '').strip() if info_div else "Comment"
                c_info = " ".join(c_info.split()) 
                
                body_div = c.select_one('.ecl-u-mb-m .ecl')
                c_body = body_div.decode_contents() if body_div else ""
                
                comments_html += f"<div style='margin-bottom: 15px; padding-left: 15px; border-left: 3px solid #ccc;'><b>{c_info}</b><br>{c_body}</div>"

        # --- 6. CLEANUP (Destroy Noise Before Extracting Main Text) ---
        cleanup_selectors = [
            '.comments-section', 'div[id^="comment-"]', 
            '.eci-vote-widget', '.ecl-social-media-share',
            '.ecl-description-list' # Removes the "Categories" block
        ]
        for selector in cleanup_selectors:
            for match in detail_soup.select(selector):
                match.decompose()

        # Destroy Specific System Phrases SAFELY
        system_phrases = [
            "To be able to add comments", 
            "The opinions expressed on the ECI Forum",
            "Want to support an initiative?",
            "Need to know more about current or past initiatives?"
        ]
        # CRITICAL FIX: The "len(text) < 300" prevents the script from accidentally deleting the whole article!
        for tag in detail_soup.find_all(['blockquote', 'p', 'div', 'span', 'footer']):
            text = tag.get_text(strip=True)
            if 0 < len(text) < 300: 
                if any(phrase in text for phrase in system_phrases):
                    tag.decompose()

        # --- 7. EXTRACT MAIN TEXT ---
        # Grab the first match of the main text block so we don't cut anything off
        content_block = detail_soup.select_one('.ecl-row .ecl-col-m-12 .ecl')
        if content_block:
            main_text = content_block.decode_contents()
        else:
            meta_desc = detail_soup.select_one('meta[name="description"]')
            main_text = meta_desc['content'] if meta_desc else "Full text could not be parsed."

        # --- 8. FORMAT FINAL CONTENT ---
        # Inject the author prominently at the top of the email/reader view
        full_text_with_author = f"<div style='margin-bottom: 20px; font-size: 1.1em;'><strong>Author:</strong> {author_name}</div><hr>" + main_text + comments_html

        # --- 9. ADD TO FEED ---
        fe = fg.add_entry()
        fe.id(full_url)
        fe.title(title)
        fe.link(href=full_url)
        # Dummy email ensures strict RSS readers like Thunderbird show the Author column
        fe.author({'name': author_name, 'email': 'noreply@forum.europa.eu'}) 
        fe.content(full_text_with_author, type='html')
        fe.published(pub_date)
        
        count += 1
        
    except Exception as e:
        print(f"Error extracting {full_url}: {e}")
        continue

# 10. Save the XML File
fg.rss_file('feed.xml')
print(f"Done! feed.xml generated with {count} items.")
