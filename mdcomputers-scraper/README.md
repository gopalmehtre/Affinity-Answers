# mdcomputers-scraper

A small Python script that scrapes product listings from [MDComputers](https://mdcomputers.in) for a given search term (e.g. `external harddrive`), walking through all result pages of:

```
https://mdcomputers.in/?route=product/search&search=<term>
```

For each product it captures name, URL, current price, original (pre-discount) price, discount %, and image URL. With `--details`, it also visits each product page to pull brand, SKU/model, availability, and a short description.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Basic search, saves both CSV and JSON
python mdcomputers_scraper.py "external harddrive"

# Limit to 2 pages, custom output name
python mdcomputers_scraper.py "external harddrive" --pages 2 -o hdd_results

# Also fetch per-product details (slower, one extra request per product)
python mdcomputers_scraper.py "external harddrive" --details

# Only CSV, slower/politer delay
python mdcomputers_scraper.py "rtx 4060" --format csv --delay 2
```

### Options

| Flag | Description |
|---|---|
| `search_term` | Required. The term to search for. |
| `-o, --output` | Output file base name (default: `mdcomputers_results`). |
| `--pages` | Max number of result pages to scrape (default: all). |
| `--delay` | Seconds to wait between requests (default: `1.0`). |
| `--details` | Visit each product page for brand/SKU/availability/description. |
| `--format` | `csv`, `json`, or `both` (default). |

## Output

CSV/JSON with columns: `name, url, price_current, price_original, discount_percent, image, brand, sku, availability, description`.

## Notes

- The site is built on OpenCart; the scraper primarily parses the standard `product-thumb` / `caption` markup, with a regex-based fallback in case class names change.
- Please scrape responsibly: keep a reasonable `--delay`, respect MDComputers' robots.txt and Terms of Use, and use the data for personal/non-commercial purposes.
- Selectors may need small tweaks if the site's theme is updated.
