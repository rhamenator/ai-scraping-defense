# Hardware Recommendations

Running the entire AI Scraping Defense stack along with the optional test website can use significant resources. For a smooth experience on a single machine we suggest:

- **CPU:** 4 cores or more
- **Memory:** At least 8&nbsp;GB of RAM
- **Storage:** 10&nbsp;GB of free disk space

These are approximate values for local experimentation on Ubuntu Server. Enabling optional services or collecting large datasets may require additional resources. Use at your own risk.

## Local LLM Containers

Running the optional `llama3` or `mixtral` containers requires significantly more horsepower:

- **Llama 3:** at least 16&nbsp;GB of RAM and roughly 15&nbsp;GB of disk space.
- **Mixtral:** 32&nbsp;GB or more of RAM and over 40&nbsp;GB of disk space. GPU acceleration is recommended.

Both containers store their downloads in `models/shared-data`, so ensure adequate free space before enabling them.
