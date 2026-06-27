import os
import json
from openai import OpenAI
from sqs_client import send_batch_to_sqs

class PriorityProcessor:
    def __init__(self, system_prompt, model="gpt-4.1-nano-2025-04-14", website_id=None, website_url=None):
        self.system_prompt = system_prompt
        self.model = model
        self.website_id = website_id
        self.website_url = website_url
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    def process_html(self, html_content, url, is_sample=False):
        try:
            print(f"Processing HTML from {url} with GPT-4 (priority mode, sample={is_sample})")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": html_content}
                ]
            )
            
            result = response.choices[0].message.content
            
            result_data = {
                'url': url,
                'website_id': self.website_id,
                'website_url': self.website_url,
                'result': result,
                'model': self.model,
                'sample': is_sample
            }
            
            send_batch_to_sqs(result_data, priority=True)
            print(f"Successfully processed and sent result for {url} to priority queue (sample={is_sample})")
            
            return True
        except Exception as e:
            print(f"Error processing HTML with OpenAI: {e}")
            return False

