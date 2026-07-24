#!/usr/bin/env python3
"""
mdcomputers_scraper.py

Scrapes product listings from MDComputers (https://mdcomputers.in) for a given
search term, walking through all result pages, and optionally visiting each
product's detail page to pull extra fields (SKU/model, availability, brand,
description). Saves results to CSV and/or JSON.

MDComputers runs on OpenCart, and search results are served at:
    https://mdcomputers.in/?route=product/search&search=<term>&page=<n>

Usage:
    python mdcomputers_scraper.py "external harddrive"
    python mdcomputers_scraper.py "external harddrive" --details -o results
    python mdcomputers_scraper.py "rtx 4060" --pages 2 --delay 1.5

Notes:
    - This is a polite scraper: it identifies itself with a normal browser
      User-Agent, retries on transient errors, and sleeps between requests.
    - Site markup can change over time. Selectors below target the OpenCart
      "product-thumb / caption" structure MDComputers currently uses, with
      regex-based fallbacks in case classes shift slightly.
    - Please check MDComputers' robots.txt / Terms of Use and scrape
      responsibly (reasonable rate, non-commercial/personal use, etc.).
"""

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from typing import List, Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mdcomputers.in"
SEARCH_PATH = "/?route=product/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PRICE_RE = re.compile(r"₹\s*([\d,]+)")
DISCOUNT_RE = re.compile(r"-(\d+)%")


@dataclass
class Product:
    name: str
    url: str
    price_current: Optional[str] = None
    price_original: Optional[str] = None
    discount_percent: Optional[str] = None
    image: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    availability: Optional[str] = None
    description: Optional[str] = None


class MDComputersScraper:
    def __init__(self, delay: float = 1.0, timeout: int = 20, retries: int = 3):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.delay = delay
        self.timeout = timeout
        self.retries = retries

    def _get(self, url: str) -> Optional[BeautifulSoup]:
        """GET a URL with retries, return parsed soup or None on failure."""
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "lxml")
            except requests.RequestException as exc:
                print(f"  [warn] attempt {attempt}/{self.retries} failed for {url}: {exc}", file=sys.stderr)
                time.sleep(self.delay * attempt)
        print(f"  [error] giving up on {url}", file=sys.stderr)
        return None

    def search_url(self, term: str, page: int = 1) -> str:
        url = f"{BASE_URL}{SEARCH_PATH}&search={quote(term)}"
        if page > 1:
            url += f"&page={page}"
        return url

    def parse_listing_page(self, soup: BeautifulSoup) -> List[Product]:
        products: List[Product] = []

        # Primary: standard OpenCart product-thumb blocks
        cards = soup.select("div.product-thumb") or soup.select(".product-layout")

        if cards:
            for card in cards:
                name_tag = card.select_one(".caption h4 a, h4 a, .caption a")
                if not name_tag:
                    continue
                name = name_tag.get_text(strip=True)
                link = urljoin(BASE_URL, name_tag["href"])

                img_tag = card.select_one("img")
                image = urljoin(BASE_URL, img_tag["src"]) if img_tag and img_tag.get("src") else None

                price_block = card.select_one(".price") or card
                price_text = price_block.get_text(" ", strip=True)
                products.append(self._build_product(name, link, image, price_text))
        else:
            # Fallback: no recognizable product cards, try a generic regex
            # sweep over "### [Name](url)" + "₹X ₹Y" patterns (handles
            # markdown-like renders or heavily restyled markup).
            products = self._regex_fallback(str(soup))

        return products

    def _build_product(self, name: str, link: str, image: Optional[str], price_text: str) -> Product:
        prices = PRICE_RE.findall(price_text)
        price_original, price_current = None, None
        if len(prices) >= 2:
            price_original, price_current = prices[0], prices[1]
        elif len(prices) == 1:
            price_current = prices[0]

        discount_percent = None
        if price_original and price_current:
            try:
                orig = float(price_original.replace(",", ""))
                cur = float(price_current.replace(",", ""))
                if orig > 0:
                    discount_percent = str(round((orig - cur) / orig * 100))
            except ValueError:
                pass
        if discount_percent is None:
            # fall back to an on-card "-NN%" badge, restricted to text that
            # appears before the first price (avoids grabbing a neighboring
            # product's badge in the regex-fallback path)
            price_pos = price_text.find("₹")
            search_zone = price_text[:price_pos] if price_pos != -1 else price_text
            discount_match = DISCOUNT_RE.search(search_zone)
            if discount_match:
                discount_percent = discount_match.group(1)

        return Product(
            name=name,
            url=link,
            price_current=price_current,
            price_original=price_original,
            discount_percent=discount_percent,
            image=image,
        )

    def _regex_fallback(self, html: str) -> List[Product]:
        products = []
        # e.g. "### [Product Name](https://mdcomputers.in/product/slug)"
        # followed somewhere nearby by "₹X ₹Y"
        for match in re.finditer(
            r"\[([^\[\]]{5,150})\]\((https://mdcomputers\.in/product/[^\)]+)\)",
            html,
        ):
            name, link = match.group(1).strip(), match.group(2)
            # strip a leading "-NN% " discount badge that sometimes prefixes
            # the link text on listing pages
            name = re.sub(r"^-\d+%\s*", "", name)

            if any(p.url == link for p in products):
                continue

            # look at a window of text right after this match for price info
            window = html[match.end():match.end() + 300]
            products.append(self._build_product(name, link, None, window))
        return products

    def get_total_pages(self, soup: BeautifulSoup) -> int:
        """Best-effort detection of total result pages."""
        text = soup.get_text(" ", strip=True)
        m = re.search(r"\((\d+)\s*Pages?\)", text)
        if m:
            return int(m.group(1))

        pages = set()
        for a in soup.select("ul.pagination a, .pagination a"):
            href = a.get("href", "")
            pm = re.search(r"page=(\d+)", href)
            if pm:
                pages.add(int(pm.group(1)))
        return max(pages) if pages else 1

    def scrape_product_details(self, product: Product) -> None:
        """Visit a product page and fill in extra fields in-place."""
        soup = self._get(product.url)
        if soup is None:
            return

        # Description
        desc_tag = soup.select_one("#tab-description, .tab-content #tab-description")
        if desc_tag:
            product.description = desc_tag.get_text(" ", strip=True)[:2000]

        # Brand
        brand_tag = soup.find(string=re.compile(r"Brand", re.I))
        if brand_tag:
            parent = brand_tag.find_parent()
            if parent:
                link = parent.find("a")
                if link:
                    product.brand = link.get_text(strip=True)

        # SKU / Product code / Model
        page_text = soup.get_text(" ", strip=True)
        sku_match = re.search(r"(?:Product Code|SKU|Model)\s*[:\-]?\s*([A-Za-z0-9\-\._/]+)", page_text)
        if sku_match:
            product.sku = sku_match.group(1)

        # Availability
        avail_match = re.search(r"Availability\s*[:\-]?\s*(In Stock|Out Of Stock|Pre-?[Oo]rder)", page_text)
        if avail_match:
            product.availability = avail_match.group(1)

    def search(self, term: str, max_pages: Optional[int] = None, fetch_details: bool = False) -> List[Product]:
        all_products: List[Product] = []
        page = 1
        total_pages = None

        while True:
            url = self.search_url(term, page)
            print(f"[fetch] page {page}: {url}")
            soup = self._get(url)
            if soup is None:
                break

            if total_pages is None:
                total_pages = self.get_total_pages(soup)
                print(f"[info] detected {total_pages} page(s) of results")

            page_products = self.parse_listing_page(soup)
            if not page_products:
                print(f"[info] no products found on page {page}, stopping")
                break

            all_products.extend(page_products)

            if fetch_details:
                for p in page_products:
                    time.sleep(self.delay)
                    print(f"  [detail] {p.name}")
                    self.scrape_product_details(p)

            page += 1
            if max_pages and page > max_pages:
                break
            if total_pages and page > total_pages:
                break

            time.sleep(self.delay)

        return all_products


def save_csv(products: List[Product], path: str) -> None:
    fields = [
        "name", "url", "price_current", "price_original", "discount_percent",
        "image", "brand", "sku", "availability", "description",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for p in products:
            writer.writerow(asdict(p))


def save_json(products: List[Product], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in products], f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Scrape product listings from MDComputers.")
    parser.add_argument("search_term", help='Search term, e.g. "external harddrive"')
    parser.add_argument("-o", "--output", default="mdcomputers_results", help="Output file base name (no extension)")
    parser.add_argument("--pages", type=int, default=None, help="Max number of result pages to scrape")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between requests (be polite!)")
    parser.add_argument("--details", action="store_true", help="Also visit each product page for extra details")
    parser.add_argument("--format", choices=["csv", "json", "both"], default="both")
    args = parser.parse_args()

    scraper = MDComputersScraper(delay=args.delay)
    products = scraper.search(args.search_term, max_pages=args.pages, fetch_details=args.details)

    print(f"\n[done] scraped {len(products)} products for '{args.search_term}'")

    if not products:
        print("No products found. The site markup may have changed — check the selectors in parse_listing_page().")
        sys.exit(1)

    if args.format in ("csv", "both"):
        csv_path = f"{args.output}.csv"
        save_csv(products, csv_path)
        print(f"[saved] {csv_path}")

    if args.format in ("json", "both"):
        json_path = f"{args.output}.json"
        save_json(products, json_path)
        print(f"[saved] {json_path}")


if __name__ == "__main__":
    main()
