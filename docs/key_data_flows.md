# Key Data Flows

Understanding how data moves through the system is key to understanding its defense strategy. The primary flow is the lifecycle of an incoming HTTP request.

## Request Lifecycle

The system processes requests in a series of stages, designed to filter out malicious traffic efficiently without impacting legitimate users.

1. **Ingress:** All traffic first hits the Nginx Proxy.
2. **Initial Filtering (Lua):** A Lua script running in Nginx performs initial, high-speed checks:
    - The source IP is checked against the `blocklist` set in Redis. If it's a match, the request is dropped immediately with a `403 Forbidden` error.
    - Basic heuristics (e.g., known malicious User-Agent strings) are applied.
3. **Asynchronous Escalation:** If the request is deemed suspicious by the Lua script, Nginx does two things simultaneously:
    - It forwards the original request to the intended backend service (e.g., your main website), so a legitimate user experiences no delay.
    - It sends a copy of the request metadata (IP, headers, path) to the **AI Service Webhook** for offline analysis.
4. **Deep Analysis (Escalation Engine):** The AI Service passes the request data to the Escalation Engine, which begins its scoring pipeline:
    - It checks the request frequency and other patterns against data in Redis.
    - It uses the trained RandomForest model to generate a bot probability score.
    - If the score is in a "gray area," it can make a final call to an external LLM via the **Model Adapter**.
5. **Action:** Based on the final score, the Escalation Engine takes action:
    - **High Score (Bot):** The IP address is added to the `blocklist` set in Redis. On its next request, the bot will be blocked at Stage 2.
    - **Low Score (Human):** No action is taken.
    - **Tarpit Score:** For certain types of bots, the IP might be flagged for redirection to the Tarpit API instead of being blocked outright.

## Data Flow Diagram

This sequence diagram illustrates the interaction between the components during the analysis of a suspicious request.

```mermaid
sequenceDiagram
    participant B as Bot
    participant N as Nginx Proxy
    participant R as Redis
    participant A as AI Service
    participant E as Escalation Engine
    participant L as LLM API
    
    B->>+N: Makes Suspicious Request
    N->>+R: Check IP in Blocklist
    R-->>-N: IP Not Found
    
    Note over N: Request seems suspicious
    N-->>B: (Proxies request to backend)
    N->>+A: Forward Request Metadata
    A-->>-N: 200 OK (Acknowledged)
    
    A->>+E: Escalate for Analysis
    E-->>-A: 200 OK (Accepted)
    
    E->>+R: Analyze Request Frequency
    R-->>-E: Frequency Data
    
    Note over E: Heuristics & ML Model Score is high
    E->>+L: Request Final Verdict
    L-->>-E: Response: "is_bot: true"
    
    Note over E: Bot confirmed. Add to blocklist.
    E->>+R: SADD blocklist, <Bot_IP>
    R-->>-E: OK
    E-->>B: 403 Forbidden (Blocked)
end
```
