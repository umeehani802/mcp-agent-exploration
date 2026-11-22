# MCP Architecture for AI Agents - LangChain Proof of Concept

[![tests](../../actions/workflows/tests.yml/badge.svg)](../../actions/workflows/tests.yml)

**Task 6, Part B** - exploring the Model Context Protocol (MCP) and how an AI agent uses it.

```
LangChain Agent -> MCP Client -> MCP Server -> Tool/Resource -> SQLite & Files -> Result -> Agent
```

This repo contains:

| Deliverable | Where |
|---|---|
| MCP technical manual (what/why, host/client/server, tools/resources/prompts, discovery, calling, security, local vs remote, MCP vs APIs, MCP + agents, MCP + LangChain) | [`docs/MCP_MANUAL.md`](docs/MCP_MANUAL.md) |
| MCP architecture diagram, agent-tool flow diagram, sequence diagram, local-vs-remote diagram | [`docs/architecture.md`](docs/architecture.md) |
| MCP server (official SDK): 5 tools, 2 resources, 1 prompt | [`mcp_poc/server.py`](mcp_poc/server.py) |
| MCP client (stdio or Streamable HTTP) | [`mcp_poc/client.py`](mcp_poc/client.py) |
| LangChain agent that discovers and calls MCP tools | [`mcp_poc/agent_langchain.py`](mcp_poc/agent_langchain.py) |
| Offline agent (no API key) | [`mcp_poc/agent_offline.py`](mcp_poc/agent_offline.py) |
| MCP implemented **from scratch** (stdlib only, prints the raw JSON-RPC) | [`mcp_poc/scratch/`](mcp_poc/scratch) |
| Tests (security, tools, protocol, SDK end-to-end) + CI | [`tests/`](tests), [`.github/workflows/tests.yml`](.github/workflows/tests.yml) |

## Architecture at a glance

```
+--------------------------- MCP HOST (agent app) ---------------------------+
|  User -> LangChain Agent (LLM) <-> MCP Client (ClientSession)              |
+------------------------------------|---------------------------------------+
                                     |  JSON-RPC 2.0 over stdio / Streamable HTTP
+------------------------------------v---------------------------------------+
|  MCP SERVER "inventory-demo"                                               |
|   Tools:     calculate | get_product | list_products |                     |
|              convert_currency | read_approved_file                         |
|   Resources: inventory://summary | docs://approved/{name}                  |
|   Prompts:   inventory_report                                              |
+------------------|-------------------------------|-------------------------+
                   v                               v
        SQLite inventory.db (read-only)    data/approved/*.md (sandboxed)
```

Full Mermaid diagrams: [`docs/architecture.md`](docs/architecture.md).

## Quick start

Requires Python 3.10+ (3.11/3.12 recommended).

```bash
git clone <your-repo-url> && cd <repo>
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add your API key (only needed for the LangChain agent)
```

### 1. See the protocol with zero dependencies (stdlib only)

```bash
python -m mcp_poc.scratch.mini_client
```

Prints every JSON-RPC message: `initialize`, `tools/list`, `tools/call`, resources, prompts, and a blocked path-traversal attack.

### 2. Official SDK client + server (no API key)

```bash
python -m mcp_poc.client                 # spawns the server over stdio and exercises everything
python -m mcp_poc.agent_offline "Convert 250 USD to PKR"
python -m mcp_poc.agent_offline "Tell me about LAP-001"
python -m mcp_poc.agent_offline "What is the return policy?"
```

### 3. LangChain agent with a real LLM

```bash
# .env: LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY=...   (or openai / ollama)
python -m mcp_poc.agent_langchain "How many units of LAP-001 are in stock, and what is the total stock value in PKR?"
```

Expected trace (wording varies by model):

```
Discovered MCP tools: calculate, get_product, list_products, convert_currency, read_approved_file
[USER]       How many units of LAP-001 ...
[AGENT]      selects tool  get_product  args={'sku': 'LAP-001'}
[MCP RESULT] {"sku": "LAP-001", ..., "price": 899.0, "stock": 12}
[AGENT]      selects tool  calculate  args={'expression': '899 * 12'}
[MCP RESULT] 10788
[AGENT]      selects tool  convert_currency  args={'amount': 10788, 'from_currency': 'USD', 'to_currency': 'PKR'}
[MCP RESULT] {"result": 3020640.0, ...}
FINAL ANSWER: 12 units ... worth about PKR 3,020,640 (demo rates).
```

For Ollama: install the `langchain-ollama` package, run `ollama pull llama3.1`, and set `LLM_PROVIDER=ollama`. Use a model that supports tool calling.

### 4. Remote-style server (Streamable HTTP)

```bash
# terminal 1
python -m mcp_poc.server --transport http          # listens on http://127.0.0.1:8000/mcp
# terminal 2
python -m mcp_poc.client --url http://127.0.0.1:8000/mcp
python -m mcp_poc.agent_langchain --url http://127.0.0.1:8000/mcp "List electronics in stock"
```

### 5. Inspect the server with the official MCP Inspector (optional)

```bash
npx @modelcontextprotocol/inspector python -m mcp_poc.server
```

## Tests

```bash
python -m unittest discover -s tests -v
```

* `test_security.py` - safe math evaluator, path traversal, SKU validation
* `test_tools.py` - tools against a temporary SQLite DB, SQL-injection inertness, read-only DB
* `test_mini_mcp.py` - full MCP lifecycle over real stdio (no third-party packages)
* `test_sdk_e2e.py` - official SDK server + client (auto-skipped if `mcp` is not installed)

## Tools, resources and prompts

| Type | Name | Description |
|---|---|---|
| Tool | `calculate(expression)` | Safe AST-based math evaluator |
| Tool | `get_product(sku)` | One product from SQLite |
| Tool | `list_products(category?, in_stock_only?, limit?)` | Filtered product list |
| Tool | `convert_currency(amount, from_currency, to_currency)` | Fixed demo FX rates (stand-in for an API) |
| Tool | `read_approved_file(name)` | Read-only access to `data/approved/` |
| Resource | `inventory://summary` | Per-category counts and stock |
| Resource template | `docs://approved/{name}` | Approved documents |
| Prompt | `inventory_report(category)` | Restock-report template |

## Security design

Path-traversal protection, strict input validation, parameterized SQL on a read-only connection, no `eval`, bounded inputs, localhost-only HTTP binding, and logs on stderr (stdout is the protocol channel). See section 9 of the manual. Try the attack yourself: `read_approved_file("../private/secrets.txt")` is rejected.

## Project layout

```
mcp_poc/
  tools_impl.py     business logic (no MCP dependency)
  security.py       validation + sandbox helpers
  database.py       SQLite seed + read-only connection
  server.py         MCP server - official SDK (FastMCP)
  client.py         MCP client - official SDK
  agent_langchain.py   LangChain agent + MCP tools
  agent_offline.py  rule-based agent, no LLM
  scratch/          from-scratch MCP server + client (stdlib)
data/approved/      documents the server may expose
data/private/       dummy secret to prove the sandbox works
docs/               manual + diagrams
tests/              unit + end-to-end tests
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: mcp` | `pip install -r requirements.txt` inside your virtualenv |
| `ImportError: create_agent` | Older LangChain; the code falls back to `langgraph.prebuilt.create_react_agent` automatically (`pip install langgraph`) |
| Auth error from the LLM | Check `.env` key and `LLM_PROVIDER` |
| Model does not call tools (Ollama) | Use a tool-calling-capable model |
| Client hangs / "connection closed" | Something printed to **stdout** in the server; log to stderr only |
| Port 8000 in use | `MCP_PORT=8010 python -m mcp_poc.server --transport http` |

## Notes

* This project is an independent exploration of MCP and is intentionally **not** connected to the Case Study project, as the task requires.
* Demo data and FX rates are fictional.

## License

MIT - see [LICENSE](LICENSE).
