import sys
import os
import argparse
from dotenv import load_dotenv
from scraper import Scraper
from prompts import PRODUCT_EXTRACTION_PROMPT

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description='Run HTML scraper for a website')
    parser.add_argument('url', type=str, help='Website URL to scrape')
    parser.add_argument('--selector', type=str, default=None, help='CSS selector for validation')
    parser.add_argument('--threads', type=int, default=10, help='Number of threads (default: 10)')
    parser.add_argument('--batch-size', type=int, default=None, help='Batch size for processing (reads from BATCH_SIZE env var if not provided)')
    parser.add_argument('--website-id', type=int, default=None, help='Website ID (optional, for tracking)')
    
    args = parser.parse_args()
    
    batch_size = args.batch_size if args.batch_size is not None else int(os.getenv('BATCH_SIZE', '50'))
    
    print(f"Using batch size: {batch_size}")
    
    scraper = Scraper(
        start_url=args.url,
        system_prompt=PRODUCT_EXTRACTION_PROMPT,
        selector=args.selector,
        num_threads=args.threads,
        batch_size=batch_size,
        website_id=args.website_id
    )
    
    print(f"Starting scraper for {args.url}")
    scraper.crawl()

if __name__ == "__main__":
    main()

