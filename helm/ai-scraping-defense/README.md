# AI Scraping Defense Helm Chart

This chart deploys a minimal version of the AI Scraping Defense stack. It includes the Nginx proxy and AI service along with optional Horizontal Pod Autoscalers.

## Usage

Update `values.yaml` with your desired image repository and tuning options. Then install the chart:

```bash
helm install ai-defense ./ai-scraping-defense \
  --set image.repository=your-registry/ai-scraping-defense \
  --set image.tag=latest
```

Autoscaling can be toggled via the `nginx.hpa.enabled` and `aiService.hpa.enabled` values.
