# Troubleshooting Guide

Below are solutions for common issues encountered when setting up or running the stack.

## Docker errors

- **Cannot connect to the Docker daemon**
  - Ensure the daemon is running: `sudo systemctl start docker`
  - Verify with `docker info`
- **Ports already in use**
  - Check running containers with `docker ps`
  - Update the port values in `.env` to unused numbers

## Python issues

- **Module not found**
  - Install dependencies with `pip install -r requirements.txt`
- **Permission denied writing files**
  - Verify file paths exist and adjust ownership with `chown` or run commands with `sudo`
- **Could not build wheels for psycopg2 or llama-cpp-python**
  - Install system build tools inside the container or host: `build-essential`, `cmake`, `python3-dev`, `libpq-dev`, `libxml2-dev`, `libxslt1-dev`

## Rust build failures

- **Toolchain not installed**
  - Install nightly Rust: `rustup default nightly`

## Database connection problems

- Ensure PostgreSQL and Redis containers are healthy with `docker compose ps`
- Review connection settings in `.env`

If problems persist, review logs with `docker compose logs` for more detail.
