import os
from bs4 import BeautifulSoup
import re

class Cleaner:
    def __init__(self, classes_file='common_css_classes.txt'):
        try:
            with open(classes_file, 'r') as f:
                self.common_classes = {line.strip().lower() for line in f if line.strip()}
        except FileNotFoundError:
            print("Warning: common_css_classes.txt not found. No common classes will be removed.")
            self.common_classes = set()

    def clean_html(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for comment in soup.find_all(text=lambda text: isinstance(text, str) and text.strip().startswith('<!--')):
            comment.extract()
        
        common_classes = self.common_classes
        
        for footer in soup.find_all('footer'):
            footer.decompose()
        
        for header in soup.find_all('header'):
            header.decompose()
        
        for script in soup.find_all('script'):
            script.decompose()
        
        for style in soup.find_all('style'):
            style.decompose()
        
        for iframe in soup.find_all('iframe'):
            iframe.decompose()
        
        for form in soup.find_all('form'):
            form.decompose()
        
        for noscript in soup.find_all('noscript'):
            noscript.decompose()
        
        for nav in soup.find_all('nav'):
            nav.decompose()
        
        for meta in soup.find_all('meta'):
            meta.decompose()
        
        if soup.head:
            soup.head.decompose()
        
        for button in soup.find_all('button'):
            button.replace_with(button.get_text())
        
        for ul in soup.find_all('ul'):
            ul.replace_with(ul.get_text())
        for li in soup.find_all('li'):
            li.replace_with(li.get_text())

        for tag in soup.find_all(['div', 'span']):
            if not tag.get('class'):
                if not tag.get_text(strip=True) and not tag.find_all():
                    tag.decompose()
                else:
                    tag.unwrap()

        css_keywords = [
            'css', 'flex', 'js', 'justify', 'align', 'center', 'right', 'left',
            'modal', 'col', 'row', 'grid', 'container', 'wrapper', 'layout',
            'margin', 'padding', 'border', 'shadow', 'background', 'color',
            'text', 'font', 'size', 'width', 'height', 'position', 'display',
            'float', 'clear', 'overflow', 'hidden', 'visible', 'block', 'inline',
            'table', 'list', 'menu', 'nav', 'header', 'footer', 'section',
            'article', 'aside', 'main', 'content', 'sidebar', 'widget', 'svg', 'icon', 'scroll'
        ]
        
        for tag in soup.find_all(True):
            if tag.name == 'img':
                attrs_to_keep = ['id', 'class', 'src', 'alt', 'width', 'height']
            else:
                attrs_to_keep = ['id', 'class']
            attrs_to_remove = [attr for attr in tag.attrs if attr not in attrs_to_keep]
            for attr in attrs_to_remove:
                del tag[attr]
            
            if 'class' in tag.attrs:
                filtered_classes = []
                for cls in tag['class']:
                    if cls.lower() in common_classes:
                        continue
                    
                    if any(keyword in cls.lower() for keyword in css_keywords):
                        continue
                    
                    parts = cls.split('-')
                    if any(len(part) <= 3 for part in parts):
                        continue
                    
                    filtered_classes.append(cls)
                
                tag['class'] = filtered_classes
                if not tag['class']:
                    del tag['class']
            
            if 'id' in tag.attrs:
                if any(keyword in tag['id'].lower() for keyword in css_keywords):
                    del tag['id']
        
        cleaned_html = str(soup)
        empty_tags_to_remove = ["div", "span", "article", "section", "ol", "ul", "p", "body"]

        for tag in empty_tags_to_remove:
            cleaned_html = cleaned_html.replace(f"<{tag}>", "")
            cleaned_html = cleaned_html.replace(f"</{tag}>", "")
        
        cleaned_html = re.sub(r'<body[^>]*>', '', cleaned_html)
        
        return cleaned_html

