# Hardware Recommendations

Running the entire AI Scraping Defense stack along with the optional test website can use significant resources. For a smooth experience on a single machine we suggest:

- **CPU:** 4 cores or more
- **Memory:** At least 8&nbsp;GB of RAM
- **Storage:** 10&nbsp;GB of free disk space

These are approximate values for local experimentation on Ubuntu Server. Enabling optional services or collecting large datasets may require additional resources. Use at your own risk.

## Recommended Hardware by Use Case

| Scenario | CPU | Memory | Storage |
| -------- | --- | ------ | ------- |
| Development / Evaluation | 4 cores | 8&nbsp;GB | 10&nbsp;GB |
| Small Deployment | 8 cores | 16&nbsp;GB | 20&nbsp;GB |
| Large Scale | 16+ cores | 32&nbsp;GB+ | 40&nbsp;GB+ |

These values are rough guidelines. Heavier traffic or multiple tenants may require additional resources.

## Local LLM Containers

Running the optional `llama3` or `mixtral` containers requires significantly more horsepower:

- **Llama 3:** at least 16&nbsp;GB of RAM and roughly 15&nbsp;GB of disk space.
- **Mixtral:** 32&nbsp;GB or more of RAM and over 40&nbsp;GB of disk space. GPU acceleration is recommended.

Both containers store their downloads in `models/shared-data`, so ensure adequate free space before enabling them.

## Performance Benchmarks

On an 8-core VM with 16&nbsp;GB of RAM the stack handled roughly **3,000 req/s** when only the tarpit service was active. Running the full suite of analysis services reduced throughput to around **1,500 req/s**. Actual performance varies based on network latency and storage speed.

## Scaling Recommendations

For high traffic deployments, run multiple instances of the microservices and Nginx behind a load balancer.
Redis and PostgreSQL can be clustered for reliability. Monitor resource usage with Prometheus and add replicas as needed. **Implement Horizontal Pod Autoscalers (HPAs) for Nginx and AI services to automatically scale based on CPU utilization.**