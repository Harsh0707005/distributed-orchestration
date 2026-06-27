import re

def url_to_filename(url):
    url = re.sub(r'^https?://', '', url)
    url = re.sub(r'\?.*$', '', url)
    
    filename = re.sub(r'[^a-zA-Z0-9\.\-]', '_', url)
    
    if len(filename) > 200:
        filename = filename[:200]
        
    if not filename.endswith('.html'):
        filename += '.html'
        
    return filename

