#!/usr/bin/env python3
"""
Google Scholar Scraper - Command Line Interface
Simple script to scrape Google Scholar data without web interface.
"""

import sys
import logging
import os

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/scraper.log', mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def main():
    """Run the scraper from command line."""
    
    print("=" * 70)
    print("Google Scholar Scraper - Command Line Interface")
    print("=" * 70)
    print()
    
    # Get profile URL from user
    if len(sys.argv) > 1:
        profile_url = sys.argv[1]
    else:
        profile_url = input("Enter Google Scholar profile URL: ").strip()
    
    if not profile_url:
        print("❌ Error: Google Scholar profile URL is required!")
        print("\nUsage: python run_scraper.py <profile_url>")
        print("Example: python run_scraper.py 'https://scholar.google.com/citations?user=nOUsQPEAAAAJ&hl=en'")
        sys.exit(1)
    
    # Validate URL
    if "scholar.google.com" not in profile_url:
        print("❌ Error: Invalid Google Scholar URL!")
        print("URL should contain 'scholar.google.com'")
        sys.exit(1)
    
    print(f"\n📍 Profile URL: {profile_url}")
    print()
    
    try:
        from .selenium_scraper import SeleniumScholarScraper
        
        # Extract scholar name from URL parameter or use default
        author_name = "scholar"
        if "user=" in profile_url:
            author_name = profile_url.split("user=")[1].split("&")[0]
        
        # Initialize scraper
        scraper = SeleniumScholarScraper(
            profile_url=profile_url,
            headless=False,  # Show browser so you can solve CAPTCHAs if needed
            download_dir=".",
            author_sanitized=author_name
        )
        
        # Run the scraping
        print("🚀 Starting scraper...")
        print("⚠️  Note: If you see a CAPTCHA, solve it manually in the browser window.")
        print("⚠️  The scraper will pause and wait for you to solve it.")
        print()
        
        scraper.scrape_profile()
        
        # Get results
        data = scraper.get_data()
        pubs = data.get("publications", [])
        
        print()
        print("=" * 70)
        print("✅ Scraping Complete!")
        print("=" * 70)
        print(f"📊 Total publications: {len(pubs)}")
        print(f"📁 JSON file: {scraper.json_path}")
        
        # Show citation statistics
        total_citations = sum(pub.get('citation_count', 0) for pub in pubs)
        pubs_with_citations = sum(1 for pub in pubs if len(pub.get('citations', [])) > 0)
        total_citation_details = sum(len(pub.get('citations', [])) for pub in pubs)
        
        print(f"📈 Total citation count: {total_citations}")
        print(f"✅ Publications with citation details: {pubs_with_citations}")
        print(f"📋 Total citation details extracted: {total_citation_details}")
        
        if total_citation_details == 0 and total_citations > 0:
            print()
            print("⚠️  Warning: Citations were not extracted (Google Scholar blocked)")
            print("💡 Tip: Solve CAPTCHAs when the scraper pauses")
        
        print()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Scraping interrupted by user (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        logging.exception("Error during scraping")
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        try:
            scraper.close_driver()
        except:
            pass

if __name__ == "__main__":
    main()
