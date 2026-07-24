# scripting-toolkit

Two small, standalone command-line tools:

1. **`mdcomputers-scraper/`** — scrapes product listings from [MDComputers](https://mdcomputers.in) for a given search term.
2. **`csv-tools/`** — shell script that downloads a CSV of companies and prints name, location, and founding year, sorted by year.

Each tool lives in its own folder and works independently — no shared code, no cross-dependencies.

---

## 1. MDComputers Product Scraper (`mdcomputers-scraper/`)

### What it is

A Python script that searches [mdcomputers.in](https://mdcomputers.in) for a product term (e.g. `"external harddrive"`), and scrapes every result across all pages of the search results.

MDComputers runs on OpenCart, and search results live at:
```
https://mdcomputers.in/?route=product/search&search=<term>&page=<n>
```

For each product it collects:
- Name
- Product page URL
- Current price
- Original (pre-discount) price
- Discount %
- Image URL

With the `--details` flag, it also opens each individual product page to pull:
- Brand
- SKU / product code / model
- Stock availability
- A short description

Results are saved to CSV and/or JSON.

### How it works

1. Builds the search URL for the given term and requests it with `requests`, using a normal browser `User-Agent` so the request looks like an ordinary visitor.
2. Parses the HTML with `BeautifulSoup`, looking for the site's standard OpenCart product card markup (`div.product-thumb` / `.caption`).
3. If that markup isn't found (e.g. the site's theme changed), it falls back to a regex-based sweep of the raw HTML that looks for `[Product Name](product-url)` + `₹old ₹new` price patterns, so the scraper degrades gracefully instead of failing outright.
4. Reads the "Showing X to Y of Z (N Pages)" text (or the pagination links) to figure out how many result pages exist, and walks through all of them with a polite delay between requests.
5. If `--details` is passed, it revisits each product's own page and extracts brand/SKU/availability/description using targeted selectors and regex.
6. Writes everything out to `mdcomputers_results.csv` and/or `.json` (or whatever name you pass with `-o`).

### Setup

```bash
cd mdcomputers-scraper
pip install -r requirements.txt
```

### Usage

```bash
# Basic search — saves both CSV and JSON
python mdcomputers_scraper.py "external harddrive"

# Limit to 2 pages, custom output file name
python mdcomputers_scraper.py "external harddrive" --pages 2 -o hdd_results

# Also fetch per-product details (slower — one extra request per product)
python mdcomputers_scraper.py "external harddrive" --details

# Only CSV, with a slower/politer delay between requests
python mdcomputers_scraper.py "rtx 4060" --format csv --delay 2
```

| Flag | Description |
|---|---|
| `search_term` | Required. The term to search for. |
| `-o, --output` | Output file base name (default: `mdcomputers_results`). |
| `--pages` | Max number of result pages to scrape (default: all). |
| `--delay` | Seconds to wait between requests (default: `1.0`). |
| `--details` | Visit each product page for brand/SKU/availability/description. |
| `--format` | `csv`, `json`, or `both` (default). |

### Output columns

`name, url, price_current, price_original, discount_percent, image, brand, sku, availability, description`

### Notes

- Scrape responsibly: keep a reasonable `--delay`, check MDComputers' `robots.txt` / Terms of Use, and use the data for personal/non-commercial purposes.
- If the site's theme changes, the primary CSS selectors in `parse_listing_page()` may need small tweaks — the regex fallback should still catch names/URLs/prices in the meantime.

---

## 2. Company Founding-Year Sorter (`csv-tools/`)

### What it is

A shell script, `company_year_sort.sh`, that downloads a CSV of companies and prints **Company, Location, Founded year**, sorted by founding year. It defaults to the [S&P 500 constituents CSV](https://github.com/datasets/s-and-p-500-companies), but works with any CSV that follows the same column layout:

```
Symbol,Security,GICS Sector,GICS Sub-Industry,Headquarters Location,Date added,CIK,Founded
```

### How it works

1. Downloads the CSV with `curl`.
2. Parses it with `gawk`, using `FPAT` (a field-pattern regex) instead of a plain comma split — this correctly handles fields like `"Saint Paul, Minnesota"` that contain a comma inside quotes, which a naive `split(",")` would break on.
3. For each row, pulls out the `Security` (company name) and `Headquarters Location` columns as-is, and extracts the **first 4-digit year** it finds in the `Founded` column. That column is often messy (e.g. `2013 (1888)`, `2020 (1915, United Technologies spinoff)`, `1904/1946/1959`), so grabbing the first 4-digit number is the simplest reliable way to get a sortable year.
4. Sorts all rows numerically by that year (`sort -k3,3n`), ascending by default.
5. Pretty-prints the result as aligned columns (no dependency on the `column` utility — it's done with a small `awk` formatting pass so the script only needs `curl` and `gawk`).

### Usage

```bash
chmod +x company_year_sort.sh

# Default: S&P 500 CSV, oldest founded first
./company_year_sort.sh

# Newest founded first
./company_year_sort.sh -r

# Any other CSV with the same column layout
./company_year_sort.sh https://example.com/other-companies.csv
```

### Requirements

- `curl`
- `gawk` (install with `sudo apt install gawk` on Debian/Ubuntu if it's missing — it's the only non-default dependency)

### Sample output

```
Company                     Location                   Founded
BNY Mellon                  New York City, New York     1784
State Street Corporation    Boston, Massachusetts        1792
Colgate-Palmolive           New York City, New York      1806
...
GE Vernova                  Cambridge, Massachusetts     2024
Paramount Skydance Corp.    Los Angeles, California       2025
Qnity Electronics           Wilmington, Delaware          2025
```

(Verified against the live S&P 500 CSV: 503 companies parsed correctly, spanning 1784–2025.)

---

## Pushing to GitHub

```bash
# unzip this archive, then from the top-level folder:
git init
git add -A
git commit -m "Add MDComputers scraper and CSV company/year sorter"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```
