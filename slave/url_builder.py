"""Build master API URLs safely."""
from urllib.parse import quote


def website_url(base, website):
    return f"{base}/websites/{quote(str(website), safe='')}"
