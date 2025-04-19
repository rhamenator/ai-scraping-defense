# Tarpit Microservice

The **Tarpit API** is a FastAPI-based microservice designed to slow down, mislead, or escalate suspicious automated web traffic. It is a key defensive component in the AI Scraping Defense Stack.

## 🚦 Purpose

- Waste time for AI scrapers, bots, and unauthorized crawlers
- Serve dynamically generated decoy content (e.g., fake HTML, JavaScript ZIPs)
- Escalate metadata to advanced classifiers (e.g., LLMs, heuristics, webhook handlers)
- Rotate honeypot archives to prevent signature-based circumvention

## 📂 Key Files

| File                     | Purpose                                                                 |
|--------------------------|-------------------------------------------------------------------------|
| `tarpit_api.py`          | FastAPI app that serves the `/tarpit` endpoint                          |
| `js_zip_generator.py`    | Creates stealth ZIP files containing obfuscated JavaScript decoys       |
| `rotating_archive.py`    | Periodically refreshes honeypot archives                                |
| `markov_generator.py`    | Generates fake text using a Markov chain model                          |
| `slow_stream_response.py`| Streams slow HTML responses to prolong bot engagement                   |

## 🔄 Usage

Start the microservice locally:

```bash
uvicorn tarpit_api:app --host 0.0.0.0 --port 8001

Or integrate it into a Docker Compose setup behind NGINX.

🛠 NGINX Integration
Ensure traffic to the API is routed through your reverse proxy:

```nginx
location /api/ {
    proxy_pass http://tarpit:8001/;
}```

🎯 Endpoint Summary

| Method      Path        Description
|-----------|-----------|----------------------------------------------------------|
| GET       | /tarpit   | Main bot trap endpoint; slow/fake response

💡 Next Steps
Add randomized delays and stream throttling

Add traps for /robots.txt, /sitemap.xml, /feed.xml, etc.

Integrate entropy filters into payload responses

Expand the rotating archive logic with multi-language support

🔒 Security
The tarpit does not assume authentication or TLS by default. You must secure deployment using HTTPS and firewall rules appropriate to your environment.

This module is part of the full-stack AI Scraping Defense project.
