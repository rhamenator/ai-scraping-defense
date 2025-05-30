## Running with Docker

This project is fully containerized and can be run locally using Docker Compose. The stack includes multiple Python-based services, Redis, and PostgreSQL, each with its own Dockerfile and specific configuration.

### Requirements

- **Docker** and **Docker Compose** installed on your system.
- The project uses **Python 3.11-slim** as the base image for all Python services (as specified in the Dockerfiles).
- A `requirements.txt` file is required for dependency installation in each service directory.
- For persistent data (Redis, Postgres), uncomment the `volumes` sections in the `docker-compose.yml` if you want to retain data between runs.

### Environment Variables

- Default credentials for Postgres are set in the compose file:
  - `POSTGRES_USER=postgres`
  - `POSTGRES_PASSWORD=postgres`
  - `POSTGRES_DB=markov`
- For additional configuration (e.g., API keys, SMTP settings), use `.env` files in the root or service directories as needed. Uncomment the `env_file` lines in the compose file to enable this.
- **Secrets** (API keys, passwords) should be managed via Docker secrets or environment variables and are not included in the images by default.

### Build and Run Instructions

1. **Clone the repository** and ensure you are in the project root directory.
2. **Build and start the stack:**

   ```sh
   docker compose up --build
   ```

   This will build all service images and start the containers as defined in `docker-compose.yml`.

3. **Access the services:**

   - **Admin UI:** [http://localhost:5002/](http://localhost:5002/)
   - **Tarpit API:** [http://localhost:8001/](http://localhost:8001/)
   - **AI Service:** [http://localhost:8000/](http://localhost:8000/)
   - **Escalation Engine:** [http://localhost:8003/](http://localhost:8003/)
   - **Redis:** [localhost:6379](localhost:6379)
   - **PostgreSQL:** [localhost:5432](localhost:5432)
   - **RAG** and **Util** services do not expose ports by default (used for batch jobs/scripts).

4. **Special Configuration:**
   - The stack is designed to run all services on a shared `backend` Docker network.
   - For local development, you may need to provide `.env` files or Docker secrets for sensitive configuration (see the `secrets/` directory for examples of required keys/passwords).
   - The Nginx edge filtering and Lua scripts require a dynamically updated `robots.txt`, managed via Kubernetes CronJob in production. For local Docker use, ensure `config/robots.txt` is present and up to date.
   - If you want to persist Redis or Postgres data, uncomment the `volumes` sections in the compose file.

5. **Rebuilding Images:**
   - If you change dependencies or code, re-run `docker compose up --build` to rebuild the images.

### Exposed Ports (per service)

| Service           | Port  |
|-------------------|-------|
| Admin UI          | 5002  |
| Tarpit API        | 8001  |
| AI Service        | 8000  |
| Escalation Engine | 8003  |
| Redis             | 6379  |
| PostgreSQL        | 5432  |

> **Note:** RAG and Util services do not expose ports by default; they are intended for internal batch processing.

For more detailed setup and advanced configuration, see [`docs/getting_started.md`](docs/getting_started.md).
