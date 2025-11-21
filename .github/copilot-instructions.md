# GitHub Copilot Instructions for AI Scraping Defense

This repository contains a sophisticated, multi-layered defense system against AI-powered web scrapers and malicious bots. These instructions help GitHub Copilot coding agent understand the project structure, workflows, and best practices.

## Project Overview

**AI Scraping Defense** is a microservice-based security platform that combines:
- Nginx reverse proxy with Lua scripting for first-line defense
- Python microservices for intelligent traffic analysis
- Machine learning models for bot detection
- LLM integration for advanced behavioral analysis
- Active countermeasures (tarpit, honeypots)
- Redis for caching and blocklists
- PostgreSQL for persistence
- Docker/Kubernetes deployment

## Key Technologies

- **Languages**: Python 3.11+, Lua, Rust (some components), Shell scripts
- **Web Frameworks**: FastAPI, Uvicorn, Gunicorn
- **Databases**: Redis, PostgreSQL
- **ML/AI**: scikit-learn, XGBoost, OpenAI, Anthropic, Google GenAI, Cohere, Mistral
- **Infrastructure**: Docker, Kubernetes, Nginx
- **Testing**: pytest, pytest-asyncio
- **Linting/Formatting**: black, isort, flake8
- **CI/CD**: GitHub Actions

## Repository Structure

```
├── .github/              # GitHub Actions workflows and templates
│   ├── workflows/        # CI/CD pipelines (tests, security audits, autofix)
│   ├── ISSUE_TEMPLATE/   # Issue templates
│   └── PULL_REQUEST_TEMPLATE.md
├── src/                  # Core Python microservices
│   ├── admin_ui/         # Admin dashboard service
│   ├── ai_service/       # AI webhook receiver
│   ├── behavioral/       # Behavioral analysis modules
│   ├── bot_control/      # Bot management and rate limiting
│   ├── captcha/          # CAPTCHA verification service
│   ├── cloud_dashboard/  # Cloud monitoring dashboard
│   ├── config_recommender/ # AI-driven configuration recommendations
│   ├── escalation/       # Escalation engine for threat analysis
│   ├── pay_per_crawl/    # Crawler authentication and billing
│   ├── plugins/          # Plugin API for custom rules
│   ├── public_blocklist/ # Community blocklist service
│   ├── rag/              # RAG (Retrieval-Augmented Generation) tools
│   ├── security/         # Security modules (RBAC, audit logging)
│   ├── tarpit/           # Tarpit API for bot resource waste
│   ├── shared/           # Shared utilities and helpers
│   └── util/             # General utilities
├── test/                 # Unit and integration tests (mirrors src/ structure)
├── scripts/              # Setup, deployment, and maintenance scripts
├── nginx/                # Nginx configuration and Lua scripts
├── helm/                 # Kubernetes Helm charts
├── docs/                 # Project documentation
├── AGENTS.md             # Guidelines for automated agents (includes pre-commit, testing)
├── CONTRIBUTING.md       # Contribution guidelines
├── README.md             # Project overview and setup instructions
└── docker-compose.yaml   # Local development environment
```

## Development Workflow

### 1. Environment Setup

Before making changes:
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pre-commit install
```

### 2. Code Quality and Linting

**Always run pre-commit hooks on modified files:**
```bash
pre-commit run --files <file1> [file2 ...]
```

The project uses:
- **black**: Python code formatting (respects the max line length configured in the repository)
- **isort**: Import sorting
- **flake8**: Python linting (see `.flake8` for configuration including max line length)

Configuration files:
- `.flake8` - Flake8 settings
- `.isort.cfg` - Import sorting configuration
- `.pre-commit-config.yaml` - Pre-commit hook definitions

### 3. Testing

**Run tests before and after changes:**
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest test/path/to/test_file.py

# Run with coverage
python -m pytest --cov=src --cov-report=html
```

Test guidelines:
- Tests are located in `test/` directory, mirroring the `src/` structure
- Use pytest fixtures defined in `test/conftest.py`
- Write unit tests for new functionality
- Integration tests should use Docker Compose when needed
- Mock external services (LLMs, payment gateways, etc.) in tests

### 4. Building and Running Locally

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f [service_name]

# Stop services
docker-compose down
```

### 5. Commit Guidelines

- Use clear, descriptive commit messages in present tense
- Examples: `Add advanced header analysis`, `Fix rate limit daemon crash`, `Update architecture docs`
- Separate unrelated changes into different commits
- Reference issue numbers when applicable: `Fix #123: Resolve memory leak in escalation engine`

## Coding Standards and Best Practices

### Python Code

1. **Follow PEP 8** with these specifics:
   - Line length: Use the max line length configured in the repository's tooling (see `.flake8`, `pyproject.toml` (if present), or formatter-specific configs). Do not assume or hard-code a specific numeric limit.
   - Use type hints for function signatures
   - Docstrings for public functions and classes

2. **FastAPI Services**:
   - Use async/await for I/O operations
   - Implement proper error handling with HTTPException
   - Use dependency injection for shared resources (Redis, DB connections)
   - Add Pydantic models for request/response validation

3. **Security**:
   - Never commit secrets or credentials
   - Use environment variables for configuration
   - Validate all user inputs
   - Follow RBAC (Role-Based Access Control) patterns
   - All sensitive operations must write to `audit.log`

4. **Error Handling**:
   - Use try-except blocks for external calls (Redis, PostgreSQL, LLM APIs)
   - Log errors with appropriate context
   - Use `tenacity` for retry logic on transient failures

5. **Testing**:
   - Aim for high test coverage (currently tracked via codecov)
   - Mock external dependencies
   - Test both success and failure scenarios
   - Use pytest fixtures for common setup

### Lua Scripts (Nginx)

- Keep scripts clean and well-commented
- Follow existing patterns in `nginx/` directory
- Test Nginx configuration changes in Docker environment

### Rust Components

- Some components (frequency-rs, tarpit-rs, markov-train-rs, jszip-rs) are written in Rust
- Follow Rust conventions and use `cargo fmt` and `cargo clippy`
- See `rust-toolchain.toml` for version requirements

## Service-Specific Guidelines

### ML Model Integration

- Models should implement the adapter pattern (see `src/shared/model_provider.py`)
- Support for: OpenAI, Anthropic, Google GenAI, Cohere, Mistral
- Always handle API rate limits and errors gracefully
- Cache predictions when appropriate (use Redis)

### Payment Gateway Integration

- Multiple gateways supported: Stripe, PayPal, Braintree, Square, Adyen, Authorize.Net
- Follow existing gateway patterns in `src/pay_per_crawl/payment_gateway.py`
- Never log full payment details
- Audit all payment operations

### Plugin Development

- Plugins live in `src/plugins/`
- Must follow the plugin API contract
- Document plugin configuration and behavior
- Include tests for custom plugins

## CI/CD and Automation

### GitHub Actions Workflows

The project has extensive CI/CD automation:

1. **Testing**: `ci-tests.yml`, `tests.yml` - Run on every PR
2. **Security Audits**: Multiple comprehensive audits (security, compliance, operations)
3. **Autofix Workflows**: Automated fixes with guardrails
   - `autofix.yml` - Generic autofix launcher
   - `comprehensive-*-audit.yml` - Category-specific audits with autofix
   - `master-problem-detection.yml` - Orchestrates all categories
4. **Deployment**: `deploy-staging.yml`, `deploy-prod.yml`
5. **Code Quality**: `codacy.yml`, `pip-audit.yml`, `security-audit.yml`

### Autofix Guardrails

When autofixes run:
- Pre/post metrics are compared (flake8, bandit, eslint, etc.)
- Tests must pass
- If any metric regresses, an issue is opened and automerge is disabled
- PRs are labeled with `autofix` and the category

## Common Tasks and Patterns

### Adding a New Microservice

1. Create service directory in `src/`
2. Implement FastAPI app with main.py
3. Add dependencies to `requirements.txt`
4. Create corresponding test directory in `test/`
5. Add service to `docker-compose.yaml`
6. Update documentation

### Adding a New Detection Heuristic

1. Implement in appropriate service (usually `src/behavioral/` or `src/escalation/`)
2. Add configuration in environment variables
3. Write unit tests
4. Update relevant documentation
5. Consider adding to plugin API if generally useful

### Updating ML Models

1. Update model files in appropriate service directory
2. Increment model version
3. Update `model_version_info` Prometheus gauge
4. Test predictions against known inputs
5. Update documentation with model changes

### Adding LLM Provider Support

1. Create adapter in escalation engine following existing patterns
2. Add provider-specific configuration
3. Implement error handling and rate limiting
4. Add tests with mocked responses
5. Update documentation

## Environment Variables

Key environment variables (see `sample.env` for complete list):
- `TENANT_ID` - Multi-tenant namespace identifier
- `REDIS_HOST`, `REDIS_PORT` - Redis connection
- `POSTGRES_*` - PostgreSQL connection details
- `ADMIN_UI_ROLE` - RBAC role for admin access
- `ADMIN_UI_CORS_ORIGINS` - CORS policy (no wildcards with credentials)
- LLM API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.
- Payment gateway credentials

## Documentation

When making changes:
- Update relevant documentation in `docs/`
- Update README.md for user-facing changes
- Update architecture diagrams if structure changes
- Reference `CONTRIBUTING.md` for contribution guidelines
- Keep CHANGELOG.md updated with notable changes

## Issue and PR Templates

- Use provided issue templates in `.github/ISSUE_TEMPLATE/`
- Fill out PR template in `.github/PULL_REQUEST_TEMPLATE.md`
- Link PRs to related issues
- Request reviews from appropriate team members

## Security Considerations

- Follow `SECURITY.md` for security vulnerability reporting
- Never expose sensitive data in logs or error messages
- Use RBAC for admin endpoints
- Implement audit logging for sensitive operations
- Set proper CORS and CSP headers
- Follow zero-trust principles

## Additional Resources

- **AGENTS.md**: Guidelines for automated agents (essential reading)
- **CONTRIBUTING.md**: Detailed contribution process
- **README.md**: Project overview and quick start
- **docs/architecture.md**: Deep dive into system architecture
- **Docker.md**: Docker-specific deployment guide

## Tips for Working on This Repository

1. **Start with tests**: Run existing tests to ensure baseline is working
2. **Use pre-commit**: Install and use pre-commit hooks to catch issues early
3. **Test incrementally**: Don't wait until the end to test your changes
4. **Read existing code**: Understand patterns before adding new code
5. **Ask questions**: Open an issue for clarification if needed
6. **Small PRs**: Make focused, small changes that are easy to review
7. **Document**: Update docs for any user-facing or architectural changes
8. **Security first**: Always consider security implications of changes

## Getting Help

- Check existing issues and discussions
- Review documentation in `docs/` directory
- Consult `CONTRIBUTING.md` for contribution process
- For security concerns, follow `SECURITY.md` guidelines
