# Model Context Protocol (MCP) - Technical Manual

**Task 6, Part B - MCP architecture for AI agents, LangChain and Agentic AI**

> Diagrams: see [`architecture.md`](architecture.md). Code: this repository (`mcp_poc/`).
> Official specification and docs: <https://modelcontextprotocol.io> (always check the latest spec version).

---

## 1. What is MCP?

The **Model Context Protocol (MCP)** is an open standard, introduced by Anthropic in November 2024, that defines how AI applications connect to external tools, data and prompts. It is built on **JSON-RPC 2.0** and is often described as *"USB-C for AI applications"*: one standard plug instead of a custom cable for every device.

An MCP **server** advertises capabilities (tools, resources, prompts). An AI application (**host**) uses an MCP **client** to discover and use them, without writing integration code specific to each system.

## 2. Why MCP is used

| Problem before MCP | How MCP helps |
|---|---|
| **N x M integrations:** every AI app needed custom glue code for every tool or data source | Write a server once; any MCP-capable host can use it (N + M) |
| Tool definitions were hand-written in each framework's format | Tools are **self-describing** (name, description, JSON Schema) and **discoverable at runtime** |
| Each vendor/framework used a different function-calling format | One protocol, with adapters (e.g. `langchain-mcp-adapters`) for each framework |
| Agents were hard-wired to a fixed tool list | Tools can be added/changed on the server without redeploying the agent (`tools/list_changed`) |
| No common place to enforce security and approval | Clear boundaries: host controls consent; server enforces its own validation |

## 3. MCP architecture

Three roles (see diagram 1 in `architecture.md`):

| Role | What it is | In this repo |
|---|---|---|
| **MCP Host** | The AI application that coordinates everything: runs the LLM/agent, creates clients, enforces user consent | The LangChain agent process (`agent_langchain.py`) |
| **MCP Client** | A connector *inside* the host that keeps **one dedicated connection to one server**; speaks JSON-RPC, handles the handshake | `mcp.ClientSession` created in `client.py:open_session()` |
| **MCP Server** | A program exposing capabilities to clients | `server.py` (official SDK) and `scratch/mini_server.py` (from scratch) |

A host can run many clients to talk to many servers at once.

### 3.1 Server primitives

| Primitive | Controlled by | Purpose | Discover / use | Example here |
|---|---|---|---|---|
| **Tools** | The **model** decides to call them | Actions / computations / queries with side effects or logic | `tools/list`, `tools/call` | `get_product`, `calculate` |
| **Resources** | The **application** decides what to load | Read-only context data identified by a URI | `resources/list`, `resources/templates/list`, `resources/read` | `inventory://summary`, `docs://approved/returns_policy.md` |
| **Prompts** | The **user** selects them | Reusable prompt templates / workflows | `prompts/list`, `prompts/get` | `inventory_report` |

### 3.2 Client-side features (server -> client requests)

Servers can also ask the client for things: **sampling** (ask the host's LLM to generate text), **roots** (which filesystem/URI boundaries the server may use) and **elicitation** (ask the user for more input). They are part of the protocol but are not needed for this proof of concept.

### 3.3 Transports

| Transport | Use | Notes |
|---|---|---|
| **stdio** | Local servers | Host spawns the server as a subprocess; newline-delimited JSON on stdin/stdout. **Never write logs to stdout** (it corrupts the protocol) - use stderr. |
| **Streamable HTTP** | Remote servers (also usable locally) | A single HTTP endpoint (this repo: `/mcp`); supports streaming responses. Replaces the older HTTP+SSE transport. Authorization is OAuth-based. |

## 4. Tool discovery and tool calling

**Discovery** - the client sends `tools/list`; the server answers with every tool's `name`, `description` and `inputSchema` (JSON Schema). The LLM only "knows" a tool through this metadata, so **descriptions are effectively prompts** - write them carefully. Servers may announce `notifications/tools/list_changed` when the list changes.

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"get_product",
  "description":"Look up one product by SKU (format ABC-123) ...",
  "inputSchema":{"type":"object","properties":{"sku":{"type":"string"}},"required":["sku"]}}]}}
```

**Calling** - the LLM emits a tool call (name + arguments). The client sends `tools/call`; the server validates, runs the tool and returns **content blocks** plus an `isError` flag.

```json
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"get_product","arguments":{"sku":"LAP-001"}}}
{"jsonrpc":"2.0","id":4,"result":{"content":[{"type":"text","text":"{\"sku\":\"LAP-001\",...,\"stock\":12}"}],"isError":false}}
```

**Two kinds of errors (important design point):**

1. **Protocol errors** (JSON-RPC `error`): unknown method / unknown tool / malformed request.
2. **Tool execution errors**: the tool ran but failed (bad SKU, file not found). Returned as a *normal result* with `"isError": true` and a readable message so **the LLM can see the error, correct its arguments and retry**.

Run `python -m mcp_poc.scratch.mini_client` to see every message above live.

## 5. Communication flow (lifecycle)

1. **Initialization** - client sends `initialize` (protocol version, capabilities, client info); server replies with its own; client sends `notifications/initialized`. This is **capability negotiation**.
2. **Operation** - discovery and calls (`tools/list`, `tools/call`, `resources/read`, `prompts/get`, `ping`, notifications).
3. **Shutdown** - close the transport (stdin / HTTP session).

Sequence diagram: diagram 3 in `architecture.md`.

## 6. Data and resource access

* **Tools** reach external systems (SQLite DB, files, APIs) *on behalf of* the model: `get_product` runs a parameterized read-only SQL query.
* **Resources** expose data by URI so the *application* can attach it as context (`inventory://summary`); **resource templates** (`docs://approved/{name}`) describe parameterized URIs.
* The server is the **only** component that touches the data source; the model never receives credentials or raw connections.

## 7. MCP + AI Agents

```
AI Agent -> MCP Client -> MCP Server -> Tool/Resource -> External System -> Result -> AI Agent
```

| Agent needs to reach... | MCP server exposes... | Example |
|---|---|---|
| **APIs** | A tool wrapping the API (auth kept server-side) | `convert_currency` (stand-in for a rates API) |
| **Databases** | Query tools (parameterized, read-only) / summary resources | `get_product`, `list_products`, `inventory://summary` |
| **Files** | File-read tools or file resources inside an approved root | `read_approved_file`, `docs://approved/{name}` |
| **External services** | One tool per service operation (email, calendar, tickets) | - |
| **Python functions** | Plain functions decorated with `@mcp.tool()` | `calculate` |
| **Business systems** (ERP/CRM) | Tools with permissions scoped to the user | - |

Agent loop: **perceive -> reason -> pick tool -> act -> observe result -> reason again**, until the LLM answers without requesting another tool. MCP standardizes the *act/observe* part; the LLM provides the reasoning. Diagram 2 shows the loop.

## 8. MCP + LangChain

[`langchain-mcp-adapters`](https://github.com/langchain-ai/langchain-mcp-adapters) converts MCP tools into LangChain `BaseTool`s. In `agent_langchain.py`:

| Step | Question | What happens in this repo |
|---|---|---|
| 1 | **How does the MCP server expose tools?** | `@mcp.tool()` in `server.py` generates name, description (from docstring) and JSON Schema (from type hints) |
| 2 | **How does the agent discover tools?** | `load_mcp_tools(session)` calls `tools/list` and wraps each result as a LangChain tool |
| 3 | **How does the agent select a tool?** | Tool schemas are sent to the LLM (native function calling); the LLM returns `tool_calls` with a name + arguments |
| 4 | **How is the tool invoked?** | LangChain executes the wrapper, which performs `session.call_tool(name, args)` = JSON-RPC `tools/call` |
| 5 | **How does the result return?** | The server's content blocks become a `ToolMessage` appended to the conversation |
| 6 | **How does the agent use the result?** | The LLM reads it in context and either calls another tool (e.g. `convert_currency`) or writes the final answer |

```python
async with open_session() as session:              # connect + handshake
    tools = await load_mcp_tools(session)          # discovery
    agent = create_agent(llm, tools)               # LLM sees the schemas
    result = await agent.ainvoke({"messages": [("user", question)]})
```

## 9. MCP security concepts

MCP gives models real capabilities, so **treat every tool argument as untrusted input.**

| Risk | Mitigation (implemented here unless noted) |
|---|---|
| **Path traversal** (`../private/secrets.txt`) | `security.safe_join`: strict filename regex, extension allowlist, resolved-path-inside-base check, size cap |
| **SQL injection** | Parameterized queries only; SKU regex; DB opened **read-only** (`mode=ro`) |
| **Code injection** (`eval`) | `calculate` uses an AST walker with an allowlist of nodes; exponent/length limits |
| **Excessive privilege** | Tools are read-only and scoped to one DB and one folder (least privilege) |
| **Prompt injection / tool poisoning** (malicious text in data or tool descriptions steering the model) | Only connect to trusted servers; review tool descriptions; keep a human in the loop for sensitive actions (host responsibility) |
| **Confused deputy / token passthrough** | Servers must validate tokens issued *for them* and not forward client tokens to upstream APIs (remote servers) |
| **Exposed local HTTP server** (DNS rebinding) | Bind to `127.0.0.1`, validate `Origin`/`Host`; never bind `0.0.0.0` without auth |
| **Unauthenticated remote access** | Remote servers use OAuth 2.1-style authorization; use TLS |
| **Secrets leakage** | Keep credentials in server environment, never in tool results or prompts |
| **Auditability** | Log every tool call (to stderr/file) with arguments and outcome |

Tests proving the first four controls: `tests/test_security.py`, `tests/test_tools.py`, `tests/test_mini_mcp.py`.

## 10. Local vs remote MCP servers

| | **Local (stdio)** | **Remote (Streamable HTTP)** |
|---|---|---|
| Process | Spawned by the host on the same machine | Independent service, possibly another machine/cloud |
| Auth | Inherits the user's OS permissions | Needs real authentication/authorization (OAuth), TLS |
| Latency | Very low | Network dependent |
| Sharing | One user | Many users/agents share one server |
| Ops | Nothing to deploy | Needs hosting, scaling, monitoring |
| Typical use | Filesystem, local DB, dev tools | SaaS integrations, enterprise systems |
| Here | `python -m mcp_poc.client` | `python -m mcp_poc.server --transport http` + `--url http://127.0.0.1:8000/mcp` |

## 11. MCP vs traditional API / tool integration

| Aspect | Traditional API / hand-written tools | MCP |
|---|---|---|
| Integration effort | Custom code per API *and* per framework | Server once, any MCP host reuses it |
| Discovery | Static: developer hard-codes tool definitions | Dynamic: `tools/list` at runtime |
| Interface contract | Per-API docs (REST/OpenAPI/GraphQL) written for developers | Self-describing JSON Schema written for models |
| Session / state | Usually stateless per request | Stateful session with capability negotiation |
| Beyond "call a function" | Not standardized | Resources, prompts, sampling, roots, elicitation |
| Interoperability | Locked to one framework's tool format | Open standard across hosts and vendors |
| Security model | Ad hoc | Defined consent and trust boundaries (still requires careful implementation) |

MCP does **not** replace APIs: an MCP server often *wraps* an existing REST API or database. It standardizes how an **AI agent** finds and uses it.

## 12. Proof of concept in this repository

```
LangChain Agent -> MCP Client -> MCP Server (inventory-demo) -> Tool -> SQLite / Files -> Result -> Agent
```

| Component | File |
|---|---|
| Business logic (tools/resources/prompts), transport-independent | `mcp_poc/tools_impl.py` |
| Security helpers | `mcp_poc/security.py` |
| Simulated business system | `mcp_poc/database.py` (SQLite, 10 products) |
| MCP server (official SDK) | `mcp_poc/server.py` |
| MCP client + demo | `mcp_poc/client.py` |
| LangChain agent | `mcp_poc/agent_langchain.py` |
| No-API-key agent (rule-based planner) | `mcp_poc/agent_offline.py` |
| Protocol from scratch (stdlib) | `mcp_poc/scratch/` |

### Design decisions (be ready to explain these)

1. **Why separate `tools_impl.py` from `server.py`?** The server is a thin protocol layer; logic is plain Python, so it is unit-testable without MCP and reused by the from-scratch server.
2. **Why a from-scratch server as well as the SDK one?** To show MCP is "just" JSON-RPC over stdio and to understand what `FastMCP` generates for me (schemas, handshake, error mapping).
3. **Why `isError: true` instead of raising protocol errors for bad input?** So the LLM can read the message and self-correct.
4. **Why read-only SQLite and parameterized queries?** Defense in depth: even a logic bug cannot modify data or inject SQL.
5. **Why an AST evaluator instead of `eval()`?** `eval` on model-produced strings is remote code execution.
6. **Why does `convert_currency` use fixed rates?** A deterministic "test API" keeps the demo reproducible and offline.
7. **Why an offline agent?** To demonstrate discover -> select -> call -> result without an API key; the LLM only replaces the `plan()` function.
8. **Why stdio by default?** Simplest, no network exposure; HTTP mode shows the remote variant.

### Possible viva questions

* Difference between a tool, a resource and a prompt? *(who controls it: model / application / user)*
* What happens during `initialize`? *(version + capability negotiation)*
* Why must a stdio server not print to stdout?
* How does the LLM know which tool to pick? *(it only sees name, description, schema)*
* What is tool poisoning and how do you reduce the risk?
* When would you choose a remote over a local server?

## 13. Limitations and future work

* The LangChain agent needs an LLM API key (or local Ollama); the offline agent uses rules, not reasoning.
* Demo auth is absent (local only). A remote deployment needs OAuth, TLS, rate limiting and audit logs.
* Tools are read-only; write actions (e.g. place order) would need human confirmation.
* Future: multi-server agent via `MultiServerMCPClient`, MCP resource subscriptions, LangGraph human-in-the-loop approval, tool-call evaluation tests, and connecting MCP to the Case Study project (explicitly out of scope for this task).

## 14. References

1. Model Context Protocol - Specification and docs. <https://modelcontextprotocol.io>
2. MCP Python SDK. <https://github.com/modelcontextprotocol/python-sdk>
3. LangChain MCP Adapters. <https://github.com/langchain-ai/langchain-mcp-adapters>
4. LangChain documentation - Model Context Protocol. <https://docs.langchain.com>
5. JSON-RPC 2.0 Specification. <https://www.jsonrpc.org/specification>
6. Anthropic - Introducing the Model Context Protocol (Nov 2024). <https://www.anthropic.com/news/model-context-protocol>
