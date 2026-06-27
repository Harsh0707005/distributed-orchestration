import os
import json
import threading
from batch_processor import OpenAIBatchProcessor
from sqs_client import send_batch_to_sqs

class HTMLToJSONLConverter:
    def __init__(self, system_prompt, model="gpt-4.1-nano-2025-04-14", website_id=None, website_url=None):
        self.system_prompt = system_prompt
        self.model = model
        self.batch_processor = OpenAIBatchProcessor()
        self.website_id = website_id
        self.website_url = website_url

    def process_batch(self, batch_dir, batch_name):
        try:
            if not os.path.exists(batch_dir):
                print(f"Batch directory {batch_dir} does not exist")
                return
                
            jsonl_data = []
            html_files = [f for f in os.listdir(batch_dir) if f.endswith('.html')]
            
            print(f"Processing batch {batch_name} with {len(html_files)} HTML files from {batch_dir}")

            if not html_files:
                print(f"No HTML files found in {batch_dir}")
                return

            for i, html_file in enumerate(html_files):
                html_path = os.path.join(batch_dir, html_file)
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()

                request_data = {
                    "custom_id": f"request-{i+1}",
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": html_content}
                        ]
                    }
                }
                jsonl_data.append(json.dumps(request_data))

            jsonl_filepath = os.path.join(batch_dir, 'batch.jsonl')
            with open(jsonl_filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(jsonl_data))
            
            print(f"Successfully created {jsonl_filepath}")

            processing_thread = threading.Thread(
                target=self.batch_processor.process_file,
                args=(jsonl_filepath, self.website_id, batch_name, self._on_batch_created)
            )
            processing_thread.daemon = True
            processing_thread.start()
        except Exception as e:
            print(f"Error processing batch: {e}")
        
    def _on_batch_created(self, openai_batch_id, website_id, batch_name):
        batch_data = {
            'openai_batch_id': openai_batch_id,
            'website_id': website_id,
            'batch_name': batch_name,
            'website_url': self.website_url
        }
        
        send_batch_to_sqs(batch_data)

