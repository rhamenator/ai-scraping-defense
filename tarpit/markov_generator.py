# tarpit/markov_generator.py
# Generates fake HTML content using Markov chains based on scraped text.

import markovify
import requests
from bs4 import BeautifulSoup
import random
import string
import os
import time

# --- Configuration ---
WIKI_URL = "https://en.wikipedia.org/wiki/Special:Random"
MIN_CORPUS_LENGTH = 10000 # Minimum characters needed to build a decent model
MAX_RETRIES = 5
DEFAULT_SENTENCES_PER_PAGE = 15
FAKE_LINK_COUNT = 5
PAGE_SAVE_DIR = "/app/fake_pages" # Directory to save generated pages (if needed)

# Ensure the save directory exists (if saving pages directly)
# os.makedirs(PAGE_SAVE_DIR, exist_ok=True)

# --- Helper Functions ---

def generate_random_page_name(length=8):
    """Generates a random alphanumeric string for page names."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def get_wikipedia_text(url=WIKI_URL, min_length=MIN_CORPUS_LENGTH, max_retries=MAX_RETRIES):
    """Scrapes text content from a Wikipedia page."""
    text_content = ""
    attempts = 0
    while len(text_content) < min_length and attempts < max_retries:
        attempts += 1
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            # Extract text primarily from paragraph tags within the main content area
            content_div = soup.find(id="mw-content-text")
            if content_div:
                paragraphs = content_div.find_all('p')
                current_page_text = "\n".join([p.get_text() for p in paragraphs])
                text_content += current_page_text + "\n"
            else: # Fallback if main content div isn't found
                 text_content += soup.get_text()

            print(f"Scraped {len(current_page_text)} chars (Total: {len(text_content)}). Attempt {attempts}/{max_retries}")
            time.sleep(0.5) # Be polite

        except requests.exceptions.RequestException as e:
            print(f"Error fetching Wikipedia page: {e}")
            time.sleep(1) # Wait before retrying
        except Exception as e:
            print(f"Error parsing Wikipedia page: {e}")

    if len(text_content) < min_length:
        print(f"Warning: Could not scrape enough text ({len(text_content)} chars). Model quality may be low.")
        # Fallback corpus if scraping fails completely
        if not text_content:
            text_content = """Technical documentation often includes setup guides. Installation requires dependencies. Configuration files use YAML syntax. API endpoints follow REST principles. Authentication uses OAuth2 tokens. Databases store user information. Caching improves performance. Logging tracks application events. Monitoring checks system health. Deployment involves Docker containers. Version control uses Git repositories. Continuous integration runs automated tests. Security audits prevent vulnerabilities. Scalability handles increased load. Backup strategies ensure data recovery.""" * 100 # Repeat simple text

    return text_content

def build_markov_model(corpus):
    """Builds a Markov chain model from the provided text corpus."""
    try:
        # state_size=2 is common, higher values need more text but give more coherence
        text_model = markovify.Text(corpus, state_size=2, well_formed=True)
        return text_model
    except Exception as e:
        print(f"Error building Markov model: {e}")
        return None

def generate_fake_links(count=FAKE_LINK_COUNT):
    """Generates a list of plausible but fake internal link targets."""
    links = []
    for _ in range(count):
        # Link to other fake pages or fake JS endpoints
        link_type = random.choice(["page", "js"])
        random_name = generate_random_page_name()
        if link_type == "page":
            links.append(f"/tarpit/page/{random_name}.html")
        else:
            links.append(f"/tarpit/js/{random_name}.js") # Assume NGINX handles serving/generating fake JS
    return links

def generate_deceptive_page_content(text_model, sentences=DEFAULT_SENTENCES_PER_PAGE):
    """Generates paragraphs of Markov text and fake links."""
    if not text_model:
        return "<p>Error generating content.</p>"

    page_content = ""
    for _ in range(random.randint(sentences // 2, sentences)): # Vary paragraph count
        paragraph = text_model.make_sentence(tries=100)
        if paragraph:
            page_content += f"<p>{paragraph}</p>\n"

    fake_links = generate_fake_links()
    link_html = "<ul>\n"
    for link in fake_links:
        link_text = link.split('/')[-1].split('.')[0].replace('_', ' ').title() # Simple readable link text
        link_html += f'    <li><a href="{link}">{link_text}</a></li>\n'
    link_html += "</ul>\n"

    # Assemble the full HTML structure
    html_structure = f"""<!DOCTYPE html>
<html>
<head>
    <title>Resource Not Found - Documentation</title>
    <meta name="robots" content="noindex, nofollow">
    <style>body {{ font-family: monospace; background-color: #eee; color: #111; padding: 1em; }} a {{ color: #0077cc; }}</style>
</head>
<body>
    <h1>Internal Resource Area</h1>
    {page_content}
    <h2>Related Resources:</h2>
    {link_html}
    <div style="margin-top: 50px; visibility: hidden;">
        <a href="/admin/login-internal-special-route">Admin Panel</a>
    </div>
</body>
</html>"""
    return html_structure

# --- Main function to be called by the API ---
def generate_dynamic_tarpit_page():
    """Scrapes data, builds model, and generates a deceptive page."""
    print("Generating new dynamic tarpit page...")
    corpus = get_wikipedia_text()
    model = build_markov_model(corpus)
    html_content = generate_deceptive_page_content(model)
    print("Dynamic tarpit page generated.")
    return html_content

# Example usage (for testing this module directly)
# if __name__ == "__main__":
#    dynamic_html = generate_dynamic_tarpit_page()
#    print("\n--- Generated HTML ---\n")
#    print(dynamic_html)
#
#    # Example of saving to a file
#    # page_name = generate_random_page_name() + ".html"
#    # save_path = os.path.join(PAGE_SAVE_DIR, page_name)
#    # with open(save_path, "w", encoding="utf-8") as f:
#    #     f.write(dynamic_html)
#    # print(f"Saved fake page to {save_path}")