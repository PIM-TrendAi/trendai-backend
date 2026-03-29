import requests
from bs4 import BeautifulSoup

url = "https://www.facebook.com/Tunisie.Numerique/posts/pfbid0S7wynXcskJycRuhTEKtL4bS8p8x1tV9Y1KKgNgq29jRu4FxmkRv2Ai1s94UshTqcl"
headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36"}
resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.text, 'html.parser')
og_img = soup.find("meta", property="og:image")
if og_img:
    print("Thumbnail URL found:", og_img["content"])
else:
    print("No og:image found.")
