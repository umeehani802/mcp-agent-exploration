# MCP Diagrams

All diagrams are [Mermaid](https://mermaid.js.org/) and render automatically on GitHub.

## 1. MCP architecture (Host / Client / Server)

```mermaid
flowchart LR
    U([User]) --> H

    subgraph H["MCP HOST (the AI application)"]
        direction TB
        LLM["LLM + Agent loop<br/>(LangChain agent)"]
        C1["MCP Client 1<br/>(ClientSession)"]
        C2["MCP Client 2"]
        LLM <--> C1
        LLM <--> C2
    end

    C1 <-- "JSON-RPC 2.0<br/>stdio (local)" --> S1
    C2 <-- "JSON-RPC 2.0<br/>Streamable HTTP (remote)" --> S2

    subgraph S1["MCP SERVER A (this repo: inventory-demo)"]
        direction TB
        T1["Tools<br/>calculate, get_product,<br/>list_products, convert_currency,<br/>read_approved_file"]
        R1["Resources<br/>inventory://summary<br/>docs://approved/{name}"]
        P1["Prompts<br/>inventory_report"]
    end

    subgraph S2["MCP SERVER B (any remote server)"]
        T2["Tools / Resources / Prompts"]
    end

    T1 --> DB[("SQLite<br/>inventory.db<br/>(read-only)")]
    T1 --> F[["Approved files<br/>data/approved/"]]
    R1 --> DB
    R1 --> F
    T2 --> EXT[("External API /<br/>business system")]
```

**Rule of thumb:** one Host runs many Clients; each Client keeps a dedicated 1:1 connection to one Server.

## 2. Agent-tool interaction flow

```mermaid
flowchart TD
    A([User question]) --> B[Agent receives task]
    B --> C["Tool discovery<br/>MCP tools/list -> names, descriptions, JSON schemas"]
    C --> D{"LLM reasons:<br/>need a tool?"}
    D -- "No" --> Z([Final answer])
    D -- "Yes: picks tool + arguments" --> E["MCP Client sends tools/call"]
    E --> F["MCP Server validates input<br/>(schema + security checks)"]
    F -- "invalid" --> G["Result with isError=true<br/>(message the LLM can read)"]
    F -- "valid" --> H["Tool runs<br/>DB query / file read / calculation"]
    H --> I[External system returns data]
    I --> J["Server returns result<br/>content blocks"]
    G --> K
    J --> K["Result added to agent context<br/>(ToolMessage)"]
    K --> D
```

## 3. Communication sequence (what is on the wire)

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant A as Agent (LLM) in Host
    participant C as MCP Client
    participant S as MCP Server
    participant X as External system (SQLite / files)

    Note over C,S: Lifecycle phase 1 - initialization
    C->>S: initialize (protocolVersion, capabilities, clientInfo)
    S-->>C: result (protocolVersion, capabilities, serverInfo)
    C->>S: notifications/initialized

    Note over C,S: Phase 2 - operation
    C->>S: tools/list
    S-->>C: tools [name, description, inputSchema]
    C-->>A: tools converted into LangChain tools

    U->>A: "How many LAP-001 are in stock? Value in PKR?"
    A->>C: tool call get_product {sku: "LAP-001"}
    C->>S: tools/call get_product
    S->>X: SELECT ... WHERE sku = ? (read-only)
    X-->>S: row
    S-->>C: result content [{type: text, text: "{...stock: 12, price: 899}"}]
    C-->>A: ToolMessage
    A->>C: tool call convert_currency {amount: 10788, USD -> PKR}
    C->>S: tools/call convert_currency
    S-->>C: result
    C-->>A: ToolMessage
    A-->>U: final answer

    Note over C,S: Phase 3 - shutdown (close stdin / HTTP session)
```

## 4. Local vs remote deployment

```mermaid
flowchart LR
    subgraph Local["Local MCP server (stdio)"]
        H1[Host process] -- "spawns subprocess<br/>stdin / stdout" --> S1[Server process]
    end
    subgraph Remote["Remote MCP server (Streamable HTTP)"]
        H2[Host process] -- "HTTPS POST/GET /mcp<br/>+ OAuth bearer token" --> S2[Server on another machine]
    end
```
