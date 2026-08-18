# LLM Deployment Configuration

LLM configuration is deployment-owned. The repository stores only `config/llm.example.conf`; the active `config/llm.conf` is intentionally ignored by Git so Dev, QA, and Production can use different models without changing source control.

## Resolution order

1. `WNG_LLM_CONFIG` points to the active config file.
2. If `WNG_LLM_CONFIG` is not set, the application looks for local `config/llm.conf` for backward compatibility.
3. Individual environment variables such as `OPENAI_MODEL`, `OLLAMA_MODEL`, `OLLAMA_HOST`, and `OLLAMA_EMBEDDING_MODEL` override values read from the config file.
4. Built-in defaults are used only when no deployment config or environment override provides a value.

## Recommended server setup

Copy the example outside the repository and edit it for the server:

```bash
sudo mkdir -p /etc/work-neural-graph
sudo cp config/llm.example.conf /etc/work-neural-graph/llm.conf
sudo nano /etc/work-neural-graph/llm.conf
```

Then point the application to that file:

```bash
export WNG_LLM_CONFIG=/etc/work-neural-graph/llm.conf
```

For systemd, set the same environment variable in the service unit:

```ini
[Service]
Environment="WNG_LLM_CONFIG=/etc/work-neural-graph/llm.conf"
Environment="OPENAI_API_KEY=..."
```

Do not store the OpenAI secret itself in the config file. Keep only `api_key_env = OPENAI_API_KEY` there and provide the secret through the process environment or secret manager.

## Example environment differences

A server may safely use:

```ini
[ollama]
model = qwen2.5:14b

[embedding]
model = bge-m3:latest
```

while another server uses different Ollama models. Unit tests isolate default configuration from deployment files, so a valid server-specific model selection does not make the test suite fail.
