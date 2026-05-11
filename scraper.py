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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 2. Fetch the Forum List (sorted by recent)
base_url = "https://citizens-initiative-forum.europa.eu"
forum_url = f"{base_url}/discussion-forum_en?sort_type=recent"

print(f"Fetching forum list from: {forum_url}")
response = requests.get(forum_url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

# 3. Identify the Idea items
# EU sites usually wrap list items in 'views-row' or 'article' tags
items = soup.select('.views-row, article.node--type-idea')

for item in items[:10]:  # Process the 10 most recent ideas
    try:
        # Find Title and Link
        link_tag = item.select_one('h2 a, h3 a, .field--name-node-title a')
        if not link_tag:
            continue
            
        title = link_tag.text.strip()
        link = link_tag['href']
        if not link.startswith('http'):
            link = base_url + link
            
        # Find Author (from the list view)
        author_tag = item.select_one('.field--name-field-author, .views-field-field-author')
        author_name = author_tag.text.strip() if author_tag else "ECI User"

        # 4. THE "FULL TEXT" STEP (Like Morss.it)
        # We visit the actual idea page to get the body content
        print(f"Scraping full text for: {title}")
        detail_res = requests.get(link, headers=headers)
        detail_soup = BeautifulSoup(detail_res.content, 'html.parser')
        
        # Target the main body text of the Idea
        # Common EU selectors for the body:
        content_block = detail_soup.select_one('.field--name-field-idea-description, .field--name-body, .node__content')
        
        if content_block:
            # We keep the HTML formatting (images, paragraphs) for a rich email experience
            full_text = content_block.decode_contents()
        else:
            full_text = "Full text could not be extracted."

        # Find the specific Date on the detail page if possible
        date_tag = detail_soup.select_one('.field--name-created, time')
        if date_tag and date_tag.get('datetime'):
            pub_date = parser.parse(date_tag['datetime'])
        else:
            pub_date = datetime.datetime.now(pytz.utc)

        # 5. Add to Feed
        fe = fg.add_entry()
        fe.id(link)
        fe.title(title)
        fe.link(href=link)
        fe.author(name=author_name)
        fe.content(full_text, type='html')
        fe.published(pub_date)

    except Exception as e:
        print(f"Error processing item: {e}")
        continue

# 6. Generate the file
fg.rss_file('feed.xml')
print("Feed updated successfully!")
