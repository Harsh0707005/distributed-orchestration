import os
import random
import requests
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pybloom_live import BloomFilter
from utils import url_to_filename
from cleaner import Cleaner
from priority_processor import PriorityProcessor

class PriorityScraper:
    def __init__(self, start_url, system_prompt, selector=None, num_threads=10, website_id=None, progress_callback=None, sample_size=None, sample_completion_callback=None):
        self.start_url = start_url
        self.base_domain = urlparse(start_url).netloc
        self.urls_to_visit = queue.Queue()
        self.urls_to_visit.put(start_url)
        self.visited_urls = BloomFilter(capacity=1000000, error_rate=0.001)
        self.lock = threading.Lock()
        self.selector = selector
        self.num_threads = num_threads
        self.website_id = website_id
        self.validation_failures = 0
        self.max_validation_failures = int(os.getenv('MAX_VALIDATION_FAILURES', '100'))
        self.should_stop = False
        self.processed_count = 0
        self.sample_count = 0
        self.sample_size = sample_size  # Number of sample products to fetch before pausing
        self.is_sample_mode = sample_size is not None and sample_size > 0
        self.sample_completion_callback = sample_completion_callback  # Callback when sample_size reached
        self.progress_callback = progress_callback  # Callback to notify worker of progress
        
        self.cleaner = Cleaner()
        self.processor = PriorityProcessor(
            system_prompt=system_prompt,
            website_id=website_id,
            website_url=start_url
        )
        
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:53.0) Gecko/20100101 Firefox/53.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) AppleWebKit/603.2.4 (KHTML, like Gecko) Version/10.1.1 Safari/603.2.4',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
        ]

    def _get_random_user_agent(self):
        return random.choice(self.user_agents)
        
    def _get_favicon_url(self, soup, url):
        favicon_tags = soup.find_all('link', rel=['icon', 'shortcut icon', 'apple-touch-icon'])
        if favicon_tags:
            favicon_url = favicon_tags[0].get('href')
            if favicon_url:
                return urljoin(self.start_url, favicon_url)
        
        parsed_url = urlparse(url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}/favicon.ico"

    def _request_url(self, url):
        headers = {'User-Agent': self._get_random_user_agent()}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None

    def _process_html_immediately(self, url, html_content):
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            favicon_url = self._get_favicon_url(soup, url)
            
            cleaned_html = self.cleaner.clean_html(html_content)
            
            full_content = f"Product URL: {url}\nFavicon: {favicon_url}\n{cleaned_html}"
            
            # Check if we're in sample mode and have reached sample size
            is_sample = False
            should_pause = False
            
            with self.lock:
                if self.is_sample_mode and self.sample_count < self.sample_size:
                    is_sample = True
                    self.sample_count += 1
                    if self.sample_count >= self.sample_size:
                        should_pause = True
                        print(f"Reached sample size limit ({self.sample_size}). Pausing scraping.")
                        self.should_stop = True
                self.processed_count += 1
            
            processing_thread = threading.Thread(
                target=self.processor.process_html,
                args=(full_content, url, is_sample)
            )
            processing_thread.daemon = True
            processing_thread.start()
            
            print(f"Sent {url} for immediate processing (#{self.processed_count} in priority mode, sample={is_sample})")
            
            # If we've reached sample size, notify the callback
            if should_pause and self.sample_completion_callback:
                self.sample_completion_callback(self.sample_count)
            
        except Exception as e:
            print(f"Error processing HTML immediately: {e}")

    def _validate_page(self, html_content):
        if not self.selector:
            return True
        soup = BeautifulSoup(html_content, 'lxml')
        if soup.select_one(self.selector):
            return True
        
        with self.lock:
            self.validation_failures += 1
            print(f"Validation failed for page, selector '{self.selector}' not found. Failures: {self.validation_failures}/{self.max_validation_failures}")

            if self.validation_failures >= self.max_validation_failures and not self.should_stop:
                print(f"Reached maximum validation failures ({self.max_validation_failures}). Stopping scraper.")
                self.should_stop = True

        return False
    
    def _stop(self):
        if not self.should_stop:
            self.should_stop = True
            print(f"Stopping priority scraper for {self.start_url}")

    def _find_links(self, url, html_content):
        soup = BeautifulSoup(html_content, 'lxml')
        links = set()
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(url, href)
            if urlparse(full_url).netloc == self.base_domain:
                links.add(full_url)
        return links

    def _worker(self):
        while not self.should_stop:
            try:
                url = self.urls_to_visit.get(timeout=1)
                with self.lock:
                    if url in self.visited_urls:
                        self.urls_to_visit.task_done()
                        continue
                    self.visited_urls.add(url)

                if self.should_stop:
                    self.urls_to_visit.task_done()
                    break

                print(f"Crawling (priority): {url}")
                html_content = self._request_url(url)

                if html_content:
                    if self._validate_page(html_content):
                        with self.lock:
                            self.validation_failures = 0
                        self._process_html_immediately(url, html_content)
                        # Notify worker that progress was made
                        if self.progress_callback:
                            self.progress_callback()
                    else:
                        if self.should_stop:
                            self.urls_to_visit.task_done()
                            break

                    new_links = self._find_links(url, html_content)
                    for link in new_links:
                        if not self.should_stop:
                            self.urls_to_visit.put(link)
                
                self.urls_to_visit.task_done()
            except queue.Empty:
                if self.should_stop:
                    break
                continue

    def crawl(self):
        worker_threads = []
        for i in range(self.num_threads):
            t = threading.Thread(target=self._worker)
            t.daemon = True
            t.start()
            worker_threads.append(t)

        try:
            while not self.should_stop:
                try:
                    self.urls_to_visit.join(timeout=1)
                    if self.urls_to_visit.empty() and self.should_stop:
                        break
                    if self.should_stop:
                        while not self.urls_to_visit.empty():
                            try:
                                self.urls_to_visit.get_nowait()
                                self.urls_to_visit.task_done()
                            except queue.Empty:
                                break
                        break
                except Exception as e:
                    if self.should_stop:
                        break
        except Exception as e:
            print(f"Error during crawl: {e}")
        
        self.should_stop = True
        print(f"Priority crawling finished for {self.start_url}. Processed {self.processed_count} pages.")

