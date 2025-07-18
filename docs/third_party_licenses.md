# Third-Party Licenses and Acknowledgments

This project utilizes various open-source components and libraries. We gratefully acknowledge the contributions of their developers. Below is a list of major dependencies and their likely licenses (please verify licenses independently for full compliance).

| Component / Package         | Typical License | Notes / Link                                                                                  |
|-----------------------------|-----------------|-----------------------------------------------------------------------------------------------|
| **Python Core**             | Python License  | [https://docs.python.org/3/license.html](https://docs.python.org/3/license.html)              |
| **Docker**                  | Apache-2.0      | [https://github.com/docker/docker-ce](https://github.com/docker/docker-ce)                    |
| **NGINX**                   | BSD-2-Clause    | [https://nginx.org/en/LICENSE](https://nginx.org/en/LICENSE)                                  |
| **Lua / LuaJIT**            | MIT             | [https://luajit.org/luajit.html](https://luajit.org/luajit.html)                              |
| **OpenResty Lua Libs**      | BSD / MIT       | e.g., `lua-resty-redis`                                                                       |
| **Redis**                   | BSD-3-Clause    | [https://github.com/redis/redis](https://github.com/redis/redis)                              |
| **GoAccess**                | MIT             | [https://github.com/allinurl/goaccess](https://github.com/allinurl/goaccess)                  |
| **Ubuntu** (Base Image)     | Various Open Src| [https://ubuntu.com/licensing](https://ubuntu.com/licensing)                                  |
| **--- Python Packages ---** |                 |                                                                                               |
| FastAPI                     | MIT             | [https://github.com/tiangolo/fastapi](https://github.com/tiangolo/fastapi)                    |
| Uvicorn                     | BSD-3-Clause    | [https://github.com/encode/uvicorn](https://github.com/encode/uvicorn)                        |
| Requests                    | Apache-2.0      | [https://github.com/psf/requests](https://github.com/psf/requests)                            |
| Httpx                       | BSD-3-Clause    | [https://github.com/encode/httpx](https://github.com/encode/httpx)                            |
| Pydantic                    | MIT             | [https://github.com/pydantic/pydantic](https://github.com/pydantic/pydantic)                  |
| Pandas                      | BSD-3-Clause    | [https://github.com/pandas-dev/pandas](https://github.com/pandas-dev/pandas)                  |
| Joblib                      | BSD-3-Clause    | [https://github.com/joblib/joblib](https://github.com/joblib/joblib)                          |
| Markovify                   | MIT             | [https://github.com/jsvine/markovify](https://github.com/jsvine/markovify)                    |
| Jinja2                      | BSD-3-Clause    | [https://github.com/pallets/jinja](https://github.com/pallets/jinja)                          |
| Schedule                    | MIT             | [https://github.com/dbader/schedule](https://github.com/dbader/schedule)                      |
| Redis (py)                  | MIT             | [https://github.com/redis/redis-py](https://github.com/redis/redis-py)                        |
| Scikit-learn                | BSD-3-Clause    | [https://github.com/scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn)  |
| User-agents                 | MIT             | [https://github.com/selwin/python-user-agents](https://github.com/selwin/python-user-agents)  |
| NumPy                       | BSD-3-Clause    | (Dependency of Pandas/Scikit-learn)                                                           |
| **--- Optional Libs ---**   |                 |                                                                                               |
| BeautifulSoup4              | MIT             | (Used in generator examples)                                                                  |
| Transformers                | Apache-2.0      | (Used in LLM fine-tuning placeholder)                                                         |
| Datasets                    | Apache-2.0      | (Used in LLM fine-tuning placeholder)                                                         |
| Torch                       | BSD-style       | (Dependency for Transformers)                                                                 |
| Evaluate                    | Apache-2.0      | (Used in LLM fine-tuning placeholder)                                                         |
| Accelerate                  | Apache-2.0      | (Used by Transformers Trainer)                                                                |
| Llama-cpp-python            | MIT             | (Optional local LLM backend)                                                                  |
| Slack_SDK                   | MIT             | (If implementing Slack alerts)                                                                |

---
*This list is intended as a guide and may not be exhaustive. Users deploying this stack are responsible for verifying compliance with all applicable licenses.*