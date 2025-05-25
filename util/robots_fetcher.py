# anti-scraping-defense/util/robots_fetcher.py
import os
import requests
import logging
# Note: The 'kubernetes' library import and related functions
# (get_kubernetes_api, update_configmap) will not work directly in a standard Colab notebook
# without significant setup to connect to a Kubernetes cluster.
# For Colab, you'd typically test the fetching logic in isolation.
try:
    from kubernetes import client, config
except ImportError:
    logging.warning("Kubernetes library not found. ConfigMap update features will not work.")
    # Define dummy classes if kubernetes library is not available
    # to prevent NameError if functions are called.
    class client:
        class CoreV1Api:
            pass
        class exceptions:
            class ApiException(Exception):
                def __init__(self, status=0):
                    self.status = status
    class config:
        @staticmethod
        def load_incluster_config():
            raise config.ConfigException("Cannot load in-cluster config outside cluster.")
        @staticmethod
        def load_kube_config():
            raise config.ConfigException("Kube config not available or not set up for this environment.")
        class ConfigException(Exception):
            pass


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# --- Configuration ---
# In a Colab environment, you'd set these manually or via input fields
REAL_BACKEND_HOST = os.getenv("REAL_BACKEND_HOST", "http://example.com") # Replace with a test URL for Colab
CONFIGMAP_NAME = os.getenv("ROBOTS_CONFIGMAP_NAME", "live-robots-txt-config")
CONFIGMAP_NAMESPACE = os.getenv("KUBERNETES_NAMESPACE", "default")
CONFIGMAP_DATA_KEY = "robots.txt"

# Default robots.txt content if fetching fails or original is missing
DEFAULT_ROBOTS_CONTENT = """User-agent: *
Disallow: /wp-admin/
Disallow: /xmlrpc.php
Disallow: /wp-login.php
Disallow: /admin/
Disallow: /administrator/
Disallow: /login/
Disallow: /private/
Disallow: /tmp/
Disallow: /temp/

# Add your sitemap if you have one
# Sitemap: https://your-real-site.com/sitemap.xml

# Disallow common AI crawlers by default as a fallback
User-agent: GPTBot
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Google-Extended
Disallow: /
"""

# User-Agent for the fetcher itself
FETCHER_USER_AGENT = "RobotsTxtFetcher/1.0 (+https://github.com/your-repo/ai-scraping-defense)" # Replace with your repo

def get_kubernetes_api():
    """Initializes and returns Kubernetes API client."""
    # This function is for Kubernetes environments.
    # It won't work in a standard Colab notebook without external K8s access.
    if 'kubernetes' not in globals(): # Check if kubernetes module was imported
        logging.error("Kubernetes library is not available.")
        return None
    try:
        config.load_incluster_config()
        logging.info("Loaded in-cluster Kubernetes configuration.")
    except config.ConfigException:
        try:
            config.load_kube_config()
            logging.info("Loaded local Kubernetes configuration (kube-config).")
        except config.ConfigException:
            logging.error("Could not load Kubernetes configuration.")
            return None
    return client.CoreV1Api()

def fetch_robots_txt(url):
    """Fetches robots.txt content from the given URL."""
    if not url:
        logging.error("REAL_BACKEND_HOST is not set. Cannot fetch robots.txt.")
        return None

    robots_url = f"{url.rstrip('/')}/robots.txt"
    logging.info(f"Attempting to fetch robots.txt from: {robots_url}")
    try:
        headers = {'User-Agent': FETCHER_USER_AGENT}
        response = requests.get(robots_url, timeout=10, headers=headers)
        response.raise_for_status()
        logging.info(f"Successfully fetched robots.txt (status: {response.status_code})")
        return response.text
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logging.warning(f"robots.txt not found at {robots_url} (404). Using default.")
            return DEFAULT_ROBOTS_CONTENT
        logging.error(f"HTTP error fetching robots.txt from {robots_url}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching robots.txt from {robots_url}: {e}")
        return None

def update_configmap(api: client.CoreV1Api, content: str):
    """Creates or updates the ConfigMap with the new robots.txt content."""
    # This function is for Kubernetes environments.
    if not api:
        logging.error("Kubernetes API client not available. Cannot update ConfigMap.")
        return

    if not content:
        logging.warning("No content to update ConfigMap. Using default.")
        content = DEFAULT_ROBOTS_CONTENT

    body = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": CONFIGMAP_NAME,
            "namespace": CONFIGMAP_NAMESPACE,
        },
        "data": {
            CONFIGMAP_DATA_KEY: content
        }
    }

    try:
        api.read_namespaced_config_map(name=CONFIGMAP_NAME, namespace=CONFIGMAP_NAMESPACE)
        api.patch_namespaced_config_map(name=CONFIGMAP_NAME, namespace=CONFIGMAP_NAMESPACE, body=body)
        logging.info(f"ConfigMap '{CONFIGMAP_NAME}' in namespace '{CONFIGMAP_NAMESPACE}' patched successfully.")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            try:
                api.create_namespaced_config_map(namespace=CONFIGMAP_NAMESPACE, body=body)
                logging.info(f"ConfigMap '{CONFIGMAP_NAME}' created successfully in namespace '{CONFIGMAP_NAMESPACE}'.")
            except client.exceptions.ApiException as e_create:
                logging.error(f"Failed to create ConfigMap '{CONFIGMAP_NAME}': {e_create}")
        else:
            logging.error(f"Failed to patch ConfigMap '{CONFIGMAP_NAME}': {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while updating ConfigMap: {e}")

# --- Main execution block for testing the fetching part in Colab ---
if __name__ == "__main__":
    logging.info("Robots.txt Fetcher (Colab Test Mode)")

    # For Colab, REAL_BACKEND_HOST needs to be a publicly accessible URL for testing.
    # Example: test_url = "https://www.wikipedia.org" # Fetches Wikipedia's robots.txt
    test_url = REAL_BACKEND_HOST # Or set this to a specific test URL
    
    if not test_url or test_url == "http://example.com": # Default if not set by user for testing
        logging.warning(f"REAL_BACKEND_HOST is not set to a specific test URL. Using a placeholder or default: {test_url}")
        print("\nPlease set a 'test_url' in the script to a live website to test fetching its robots.txt.")
        print(f"Example: test_url = 'https://www.google.com'")
        # Attempting with a known good URL for demonstration if REAL_BACKEND_HOST is not suitable for a direct test
        if test_url == "http://example.com": # The default from getenv if not set
            print(f"Attempting to fetch from 'https://www.python.org' as an example instead of '{test_url}'")
            test_url = "https://www.python.org"


    if test_url and not (test_url.startswith("http://") or test_url.startswith("https://")):
        print(f"Warning: test_url '{test_url}' does not seem to be a valid http/https URL. Adding 'http://'.")
        test_url = "http://" + test_url

    print(f"\nFetching robots.txt from: {test_url}")
    robots_content = fetch_robots_txt(test_url)

    if robots_content:
        print("\n--- Fetched robots.txt Content ---")
        print(robots_content[:1000]) # Print first 1000 chars
        if len(robots_content) > 1000:
            print("... (content truncated)")
        print("--- End of Fetched Content ---")
    else:
        print("\nFailed to fetch robots.txt or used default content.")
        print("\n--- Default robots.txt Content (if used) ---")
        print(DEFAULT_ROBOTS_CONTENT)
        print("--- End of Default Content ---")

    # The Kubernetes parts (get_kubernetes_api, update_configmap)
    # would not be executed in a typical Colab test of the fetching logic.
    # You could call them if you have configured Colab to connect to a K8s cluster,
    # but that's an advanced setup.
    #
    # Example of how it would be called in the K8s CronJob:
    # k8s_api = get_kubernetes_api()
    # if k8s_api and robots_content:
    #     update_configmap(k8s_api, robots_content)
    # elif k8s_api: # Failed to fetch, use default
    #     update_configmap(k8s_api, DEFAULT_ROBOTS_CONTENT)

    logging.info("Robots.txt Fetcher script finished (Colab Test Mode).")
