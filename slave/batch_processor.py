import os
import json
import glob
from openai import OpenAI
from dotenv import load_dotenv

class OpenAIBatchProcessor:
    def __init__(self):
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def process_file(self, jsonl_filepath, website_id=None, batch_name=None, on_batch_created=None):
        try:
            with open(jsonl_filepath, "rb") as f:
                uploaded_file = self.client.files.create(
                    file=f,
                    purpose="batch"
                )
            print(f"Successfully uploaded file: {uploaded_file.id}")

            batch = self.client.batches.create(
                input_file_id=uploaded_file.id,
                endpoint="/v1/chat/completions",
                completion_window="24h"
            )
            print(f"Successfully created batch: {batch.id}")

            batch_dir = os.path.dirname(jsonl_filepath)
            batch_response_filepath = os.path.join(batch_dir, 'batch_response.json')
            with open(batch_response_filepath, 'w', encoding='utf-8') as f:
                json.dump(batch.to_dict(), f, indent=4)
            
            print(f"Successfully saved batch response to {batch_response_filepath}")
            
            if callable(on_batch_created):
                on_batch_created(batch.id, website_id, batch_name)
            
            self._cleanup_batch_files(batch_dir, jsonl_filepath)
                

        except Exception as e:
            print(f"An error occurred during batch processing: {e}")
    
    def _cleanup_batch_files(self, batch_dir, jsonl_filepath):
        try:
            html_files = glob.glob(os.path.join(batch_dir, '*.html'))
            for html_file in html_files:
                try:
                    os.remove(html_file)
                    print(f"Removed HTML file: {html_file}")
                except Exception as e:
                    print(f"Error removing {html_file}: {e}")
            
            if os.path.exists(jsonl_filepath):
                try:
                    os.remove(jsonl_filepath)
                    print(f"Removed JSONL file: {jsonl_filepath}")
                except Exception as e:
                    print(f"Error removing {jsonl_filepath}: {e}")
            
            print(f"Cleanup completed for batch directory: {batch_dir}")
        except Exception as e:
            print(f"Error during cleanup: {e}")

    def check_batch_status(self, batch_id):
        try:
            batch = self.client.batches.retrieve(batch_id)
            print("Batch status:")
            print(batch)
            return batch
        except Exception as e:
            print(f"An error occurred while checking batch status: {e}")
            return None

    def get_batch_results(self, batch_id):
        try:
            batch = self.client.batches.retrieve(batch_id)

            if batch.status == 'completed' and batch.output_file_id:
                file_contents = self.client.files.retrieve_content(batch.output_file_id)
                print("Batch results:")
                print(file_contents)

                results_filepath = os.path.join(os.getcwd(), f'{batch.output_file_id}_results.jsonl')
                with open(results_filepath, 'w', encoding='utf-8') as f:
                    f.write(file_contents)
                print(f"Saved results to {results_filepath}")
                return file_contents

            elif batch.status == 'failed' and batch.error_file_id:
                error_contents = self.client.files.retrieve_content(batch.error_file_id)
                print("Batch failed. Error details:")
                print(error_contents)
                return None
            else:
                print(f"Batch is not yet completed. Current status: {batch.status}")
                return None

        except Exception as e:
            print(f"An error occurred while retrieving batch results: {e}")
            return None

