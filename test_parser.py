from requests_html import HTMLSession

URL = "https://visa.vfsglobal.com/blr/ru/pol/"

def test_parse_news():
    session = HTMLSession()
    print(f"Fetching news from {URL} ...")
    
    try:
        r = session.get(URL, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/116.0.0.0 Safari/537.36"
        })
        r.html.render(timeout=20)
    except Exception as e:
        print(f"Error fetching/rendering page: {e}")
        return

    news_blocks = r.html.find(".news-li")[:3]
    if not news_blocks:
        print("No news blocks found!")
        return

    print(f"Found {len(news_blocks)} news items:\n")
    for i, block in enumerate(news_blocks, 1):
        date_elem = block.find(".news-date", first=True)
        title_elem = block.find(".renderer-content", first=True)
        link_elem = block.find(".news-link", first=True)

        date = date_elem.text if date_elem else ""
        title = title_elem.text if title_elem else ""
        link = "https://visa.vfsglobal.com" + link_elem.attrs["href"] if link_elem else ""

        print(f"{i}) Date: {date}")
        print(f"   Title: {title}")
        print(f"   Link: {link}\n")

if __name__ == "__main__":
    test_parse_news()
# --- IGNORE ---
# This script periodically checks the specified news website for updates in the main headline.