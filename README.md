# 📱 Apple App Store Scraper

Apple App Store Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Apple App Store data for free.

## ✨ What Can I Get?

- 📱 **Full details on any app in all 175 storefronts** — price, 5-star histogram, chart rank, 25 versions, privacy labels & screenshots
- ⭐ **Reviews with no 500-review cap** — title, full text, stars, author, date & the developer's reply, in 4 sort orders
- 🏆 **Top charts with 200 ranked apps** — free, paid, grossing & new, per category, on iPhone, iPad, Mac, Apple TV, Watch & Vision
- 💸 **In-app purchase prices, developers & editorial** — subscription tiers & free trials, every app of a developer, Today stories & curated collections

## 🎥 Example: A Full Apple App Store App

```json
{
  "id": "6448311069",
  "name": "ChatGPT",
  "subtitle": "Your everyday AI assistant",
  "bundle_id": "com.openai.chat",
  "link": "https://apps.apple.com/us/app/chatgpt/id6448311069",
  "developer": { "id": "1684349733", "name": "OpenAI OpCo, LLC", "link": "https://apps.apple.com/us/developer/openai-opco-llc/id1684349733" },
  "price": { "amount": 0.0, "currency": "USD", "formatted": "$0.00", "kind": "get" },
  "rating": {
    "average": 4.8,
    "count": 11874173,
    "histogram": { "1": 272613, "2": 68312, "3": 146069, "4": 495094, "5": 10892085 }
  },
  "chart_position": { "chart": "top-free", "position": 2, "category_id": "6007", "category": "Productivity" },
  "version": "1.2026.293",
  "version_released_at": "2026-10-27T16:49:11Z",
  "released_at": "2023-05-18",
  "file_size_bytes": 293212160,
  "age_rating": { "label": "13+" },
  "website_link": "https://openai.com/chatgpt",
  "in_app_purchases": [
    { "name": "ChatGPT Plus", "product_id": "oai_chatgpt_plus_1999_1m", "price": { "amount": 19.99, "currency": "USD" }, "is_subscription": true, "subscription_period": "P1M" }
  ],
  "events": [
    { "name": "New Voices in ChatGPT", "kind": "majorUpdate", "starts_at": "2026-10-16T17:00:00Z", "ends_at": "2026-11-16T17:00:00Z" }
  ],
  "privacy": [
    { "id": "DATA_LINKED_TO_YOU", "name": "Data Linked to You", "data_categories": [{ "id": "LOCATION", "name": "Location" }] }
  ],
  "version_history": [
    { "version": "1.2026.293", "released_at": "2026-10-27T16:49:11Z", "release_notes": "Bug fixes and small improvements." }
  ]
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Apple App Store Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/apple-app-store-scraper
cd apple-app-store-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/apps/details?app=6448311069"
```

```json
{
  "id": "6448311069",
  "name": "ChatGPT",
  "subtitle": "Your everyday AI assistant",
  "bundle_id": "com.openai.chat",
  "link": "https://apps.apple.com/us/app/chatgpt/id6448311069",
  "developer": { "id": "1684349733", "name": "OpenAI OpCo, LLC", "link": "https://apps.apple.com/us/developer/openai-opco-llc/id1684349733" },
  "price": { "amount": 0.0, "currency": "USD", "formatted": "$0.00", "kind": "get" },
  "rating": {
    "average": 4.8,
    "count": 11874173,
    "histogram": { "1": 272613, "2": 68312, "3": 146069, "4": 495094, "5": 10892085 }
  },
  "chart_position": { "chart": "top-free", "position": 2, "category_id": "6007", "category": "Productivity" },
  "category": "Productivity",
  "version": "1.2026.293",
  "file_size_bytes": 293212160,
  "in_app_purchases": [
    { "name": "ChatGPT Plus", "price": { "amount": 19.99, "currency": "USD", "formatted": "$19.99", "kind": "buy" }, "subscription_period": "P1M" },
    { "name": "ChatGPT Go", "price": { "amount": 8.0, "currency": "USD", "formatted": "$8.00", "kind": "buy" }, "subscription_period": "P1M" }
  ]
}
```

All 20 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

20 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| App Details | `/apps/details` | Everything about one app: price, ratings, versions, privacy, IAPs, media |
| Search Suggestions | `/apps/suggestions` | The App Store's own autocomplete terms for any partial query |
| Search Apps | `/apps/search` | Up to 200 apps per keyword with price, rating and developer |
| App Reviews | `/apps/reviews` | Full-text reviews, 20 per page, with stars and developer replies |
| In-App Purchases | `/apps/in-app-purchases` | Subscription and IAP prices, periods, free trials and intro offers |
| Similar Apps | `/apps/similar` | "You Might Also Like" apps plus more by the same developer |
| Version History | `/apps/versions` | The last 25 releases with dates and full release notes |
| Privacy Labels | `/apps/privacy` | What data an app tracks, links to you or keeps anonymous |
| In-App Events | `/apps/events` | Live and upcoming in-app events with dates and deep links |
| Bulk App Lookup | `/apps/lookup` | Up to 100 apps in one call by ID, bundle ID or URL |
| Top Charts | `/charts/list` | Top free, paid, grossing and new: 200 ranked apps per category |
| Categories | `/charts/categories` | Every category ID and subcategory, ready for charts |
| Developer Details | `/developers/details` | A developer's page with every app, grouped by platform |
| Developer Apps | `/developers/apps` | Up to 200 full app records for one developer |
| Bundle Details | `/bundles/details` | Bundle price, rating and every app it includes |
| Browse Store Tabs | `/editorial/browse` | Today, Apps, Games and Arcade tabs: stories, shelves and apps |
| Category Page | `/editorial/category` | A category's curated shelves, collections and top apps |
| Curated Collection | `/editorial/room` | Every app in a See All collection like Editors' Choice |
| Story | `/editorial/story` | Full App Store stories: text, images and featured apps |
| Storefronts | `/storefronts/list` | All 175 storefronts with their supported languages |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-apple-app-store-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-apple-app-store-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-apple-app-store-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/apps/reviews",
    params={"app": "6448311069", "sort": "recent"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Apple App Store Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/apple-app-store-scraper-github-whatsapp)

[![Ask Us by Email about Apple App Store Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](https://www.omkar.cloud/l/apple-app-store-scraper-github-email)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/apple-app-store-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/apple-app-store-scraper)
