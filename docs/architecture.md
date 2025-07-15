# System Architecture

The AI Scraping Defense system is designed as a distributed, microservice-based architecture. This design promotes scalability, resilience, and separation of concerns. The system is composed of several key components orchestrated by Docker Compose for local development and Kubernetes for production.

## Core Components

- **Nginx Proxy:** The public-facing entry point for all traffic. It uses Lua scripting for high-performance initial request filtering, such as checking against a blocklist in Redis. Suspicious requests are asynchronously forwarded to the AI Service for deeper analysis.

- **Python Services:** A collection of specialized microservices that form the "brain" of the system. All Python services are built from a single, unified `Dockerfile` to ensure consistency and reduce build times.

  - **AI Service:** A simple webhook that receives suspicious request data from Nginx and queues it for analysis by the Escalation Engine.
  - **Escalation Engine:** The central analysis component. It runs a multi-stage pipeline to score requests, using heuristics, a machine learning model, and optionally a powerful LLM for a final verdict.
  - **Tarpit API:** Provides a set of "tarpits" (e.g., zip bombs, slow responses, nonsensical data) designed to waste the resources of confirmed malicious bots.
  - **Admin UI:** A Flask-based web interface for monitoring system metrics, viewing the blocklist, and managing basic settings.

- **Data Stores:**
  - **Redis:** An in-memory data store used for high-speed operations like caching, managing the IP blocklist, and tracking request frequencies.
  - **PostgreSQL:** A relational database used for storing the persistent data needed for the Markov chain text generator.

- **Background Jobs:**
  - **Corpus Updater & Markov Trainer:** Cron jobs that periodically fetch new text data and retrain the Markov model to keep the tarpit content fresh.
  - **Archive Rotator:** A simple service that manages the "zip bomb" archives used by the Tarpit API.

## Architecture Diagram

This diagram illustrates the high-level relationships between the system's components. It's perfect for providing a visual overview in a presentation.

```mermaid
graph TD
    subgraph "User / Bot Traffic" direction LR
        User[<font size=5>👤</font><br>User]
        Bot[<font size=5>🤖</font><br>Bot]
    end

    subgraph "Defense System"
        direction TB
        Nginx[<font size=5>🛡️</font><br>Nginx Proxy w/ Lua]
        
        subgraph "Analysis & Logic (Python Microservices)"
            direction LR
            AIService[AI Service Webhook]
            EscalationEngine[<font size=5>🧠</font><br>Escalation Engine]
            AdminUI[<font size=5>📊</font><br>Admin UI]
        end

        subgraph "Countermeasures"
            TarpitAPI[<font size=5>🕸️</font><br>Tarpit API]
        end

        subgraph "Data & State Stores"
            direction LR
            Redis[<font size=5>⚡</font><br>Redis<br>(Blocklist, Cache)]
            Postgres[<font size=5>🐘</font><br>PostgreSQL<br>(Markov Data)]
        end
    end
    
    subgraph "External Services"
        LLM[<font size=5>☁️</font><br>LLM APIs<br>(OpenAI, Mistral, etc.)]
    end

    User -- "Legitimate Request" --> Nginx
    Bot -- "Suspicious Request" --> Nginx
    
    Nginx -- "Block Immediately" --> Bot
    Nginx -- "Forward for Analysis" --> AIService
    Nginx -- "Serve Content" --> User
    Nginx -- "Redirect to Tarpit" --> Bot

    AIService -- "Queues Request" --> EscalationEngine
    EscalationEngine -- "Reads/Writes" --> Redis
    EscalationEngine -- "Reads" --> Postgres
    EscalationEngine -- "Calls for Final Verdict" --> LLM
    EscalationEngine -- "Updates" --> AdminUI

    AdminUI -- "Manages" --> Redis

    TarpitAPI -- "Reads" --> Postgres
end
```

## Real-time Request Processing Flow

```mermaid
graph TD
    User[User] -->|Legitimate Request| Nginx
    Bot[Bot] -->|Suspicious Request| Nginx

    Nginx -->|Block Immediately| Bot
    Nginx -->|Forward for Analysis| AIService
    Nginx -->|Serve Content| User
    Nginx -->|Redirect to Tarpit| Bot

    AIService -->|Queues Request| EscalationEngine
    EscalationEngine -->|Reads/Writes| Redis
    EscalationEngine -->|Reads| Postgres
    EscalationEngine -->|Calls for Final Verdict| LLM
    EscalationEngine -->|Updates| AdminUI

    AdminUI -->|Manages| Redis

    TarpitAPI -->|Reads| Postgres
end
```

## Key Data Flows

```mermaid
graph TD
    subgraph "User / Bot Traffic"
        direction LR
        User[<font size=5>👤</font><br>User]
        Bot[<font size=5>🤖</font><br>Bot]
    end

    subgraph "Defense System"
        direction TB
        Nginx[<font size=5>🛡️</font><br>Nginx Proxy w/ Lua]

        subgraph "Analysis & Logic (Python Microservices)"
            direction LR
            AIService[AI Service Webhook]
            EscalationEngine[<font size=5>🧠</font><br>Escalation Engine]
            AdminUI[<font size=5>📊</font><br>Admin UI]
        end

        subgraph "Countermeasures"
            TarpitAPI[<font size=5>🕸️</font><br>Tarpit API]
        end

        subgraph "Data & State Stores"
            direction LR
            Redis[<font size=5>⚡</font><br>Redis<br>(Blocklist, Cache)]
            Postgres[<font size=5>🐘</font><br>PostgreSQL<br>(Markov Data)]
        end
    end

    subgraph "External Services"
        LLM[<font size=5>☁️</font><br>LLM APIs<br>(OpenAI, Mistral, etc.)]
    end

    User -- "Legitimate Request" --> Nginx
    Bot -- "Suspicious Request" --> Nginx

    Nginx -- "Block Immediately" --> Bot
    Nginx -- "Forward for Analysis" --> AIService
    Nginx -- "Serve Content" --> User
    Nginx -- "Redirect to Tarpit" --> Bot

    AIService -- "Queues Request" --> EscalationEngine
    EscalationEngine -- "Reads/Writes" --> Redis
    EscalationEngine -- "Reads" --> Postgres
    EscalationEngine -- "Calls for Final Verdict" --> LLM
    EscalationEngine -- "Updates" --> AdminUI

    AdminUI -- "Manages" --> Redis

    TarpitAPI -- "Reads" --> Postgres
end
```
