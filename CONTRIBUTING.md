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

## How to Contribute

1. **Find an Issue or Propose an Idea:** Look through existing issues or propose a new feature/improvement in the Issues tab or Discussions.
2. **Fork the Repository:** Create your own copy of the project.
3. **Create a Feature Branch:** `git checkout -b feature/your-new-feature`
4. **Make Your Changes:** Implement your feature or bug fix. Ensure code is linted and follows project style (if defined).
5. **Test Your Changes:** Run existing tests or add new ones as appropriate. Test the functionality locally using Docker Compose.
6. **Commit Your Changes:** Use clear and descriptive commit messages: `git commit -am 'feat: Add advanced header analysis heuristic'`
7. **Push to Your Fork:** `git push origin feature/your-new-feature`
8. **Submit a Pull Request:** Open a PR against the `main` branch of the original repository. Fill out the PR template clearly.

## Code Style (Example)

- Follow PEP 8 for Python.
- Keep Lua scripts clean and commented.
- Use consistent formatting for Dockerfiles and YAML.

## Contact

For major changes, architectural discussions, or potential collaborations, please open an Issue first or reach out via the contact methods listed in the repository (if available). For security concerns, follow the `SECURITY.md` policy.