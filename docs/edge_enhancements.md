# Edge Provider Enhancements

This release adds experimental features inspired by services offered by large CDN providers.

## Crawler Tokens

`src/bot_control/crawler_auth.py` implements a simple in-memory registry for crawl tokens. A crawler can register a token and purpose which is later validated for every request. Combined with `src/bot_control/pricing.py`, usage can be tracked for pay-per-crawl experiments.

## AI Labyrinth Honeypots

`src/tarpit/labyrinth.py` generates deterministic maze pages. When `ENABLE_AI_LABYRINTH=true`, the Tarpit API will serve these pages to suspicious clients.

### Browser Fingerprinting

`src/tarpit.labyrinth.generate_labyrinth_page` can optionally embed a fingerprinting script that collects extensive browser details. Set `ENABLE_FINGERPRINTING=true` in your environment to include this JavaScript in responses.

## Risk and Attack Scoring

`src/security/risk_scoring.py` and `src/security/attack_score.py` provide placeholder scoring logic that can feed into future Zero Trust models and WAF policies.

These modules are intentionally lightweight so they can be replaced by more advanced implementations.
