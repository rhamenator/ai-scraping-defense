# Contributing to AI Scraping Defense Stack

Thank you for considering contributing to this project! We aim to build a robust, ethical, and effective defense against unwanted AI scraping, and community contributions are vital.

## Attribution

If you use this project or its components in your own work (open-source or commercial), you must:

- Credit this repository clearly in your documentation or distribution (e.g., "Based on/Derived from the AI Scraping Defense Stack: [link-to-your-repo]").
- Include a reference in your own LICENSE or README linking back to the original repository.
- Comply with the terms of the [GPL-3.0 License](LICENSE).

## Contribution Guidelines

We welcome meaningful contributions, including but not limited to:

- **Improving Detection Heuristics:** Enhancing Lua scripts, Python logic, or behavioral analysis techniques.
- **Classifier Compatibility:** Adding support for more local LLMs (via llama.cpp, Ollama, etc.) or external classification APIs.
- **Metrics & UI:** Expanding the admin dashboard with more detailed visualizations or filtering capabilities.
- **Tarpit Enhancements:** Creating more sophisticated decoy content (JS, HTML via Markov chains), improving slow-response logic, or adding new trap types.
- **Performance Optimization:** Improving the efficiency of services or resource usage.
- **Documentation:** Clarifying setup, usage, architecture, or API references.
- **Testing:** Adding unit tests, integration tests, or bot simulation tests.
- **Security Hardening:** Identifying and patching potential vulnerabilities.

## Security Culture

This project maintains a strong security culture. All contributors are expected to:

- **Follow Security Best Practices**: Write secure code following our guidelines (see below)
- **Complete Security Training**: New contributors should review security documentation in `docs/security/`
- **Use Security Tools**: Install and run pre-commit hooks for automated security checks
- **Report Security Issues**: Follow responsible disclosure process in `SECURITY.md`
- **Participate in Security Reviews**: Engage constructively in security-focused code reviews
- **Stay Informed**: Keep up with security advisories relevant to our stack

For comprehensive security culture information, see:
- `SECURITY.md` - Security policy and reporting
- `docs/security/security_culture.md` - Security culture programs
- `docs/security/security_awareness_training.md` - Training curriculum
- `docs/security/security_champions.md` - Security Champions program

## How to Contribute

1. **Find an Issue or Propose an Idea:** Look through existing issues or propose a new feature/improvement in the Issues tab or Discussions.
2. **Fork the Repository:** Create your own copy of the project.
3. **Install pre-commit Hooks:** After cloning, run `pre-commit install` so style checks run automatically.
4. **Create a Feature Branch:** `git checkout -b feature/your-new-feature`
5. **Make Your Changes:** Implement your feature or bug fix. Ensure code is linted and follows project style (if defined).
6. **Test Your Changes:** Run existing tests or add new ones as appropriate. Test the functionality locally using Docker Compose.
7. **Commit Your Changes:** Use clear and descriptive commit messages: `git commit -am 'feat: Add advanced header analysis heuristic'`
8. **Push to Your Fork:** `git push origin feature/your-new-feature`
9. **Submit a Pull Request:** Open a PR against the `main` branch of the original repository. Fill out the PR template clearly.

## Code Style

- Follow PEP 8 for Python.
- Keep Lua scripts clean and commented.
- Use consistent formatting for Dockerfiles and YAML.

## Security Coding Guidelines

All code contributions must follow these security practices:

### Input Validation
- Validate and sanitize all user inputs
- Use Pydantic models for API request validation
- Reject invalid input rather than attempting to correct it
- Use allowlists rather than denylists when possible

### Authentication & Authorization
- Never bypass authentication or authorization checks
- Use established authentication mechanisms (don't roll your own crypto)
- Implement proper session management
- Log all authentication and authorization events

### Data Protection
- Never log sensitive data (passwords, tokens, PII)
- Use parameterized queries to prevent SQL injection
- Encrypt sensitive data at rest and in transit
- Handle secrets securely (use environment variables, never commit secrets)

### Error Handling
- Don't expose sensitive information in error messages
- Log errors with sufficient context for debugging
- Fail securely (deny by default)
- Handle all exceptions appropriately

### Dependencies
- Keep dependencies up-to-date
- Review security advisories for dependencies
- Use `pip-audit` and other security scanning tools
- Document reasons for using specific dependency versions

### Code Review
- All PRs require review, security-sensitive PRs require Security Champion review
- Use security review checklist (see `docs/security/security_champions.md`)
- Address security feedback before merging
- Don't merge code with known security vulnerabilities

## Contact

For major changes, architectural discussions, or potential collaborations, please open an Issue first or reach out via the contact methods listed in the repository (if available). For security concerns, follow the `SECURITY.md` policy.
