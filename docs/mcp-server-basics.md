# MCP Server: Basic Knowledge Guide

## 1. What is MCP?

**MCP (Model Context Protocol)** is an open standard introduced by **Anthropic in November 2024**. It provides a universal way for AI applications (LLM hosts like Claude Desktop, Cursor, Windsurf, etc.) to connect with external data sources, tools, and services.

> Think of MCP as the **"USB-C port for AI applications"** — one standardized protocol that lets any AI client plug into any data source or tool, instead of building custom integrations for every combination.

---

## 2. Why MCP Exists (The Problem It Solves)

Before MCP, integrating LLMs with external systems required:

- Custom-built connectors for **every (model × tool) pair** → the **N×M integration problem**.
- Vendor-specific function calling APIs (OpenAI, Anthropic, Google all differed).
- Re-implementing the same integrations across each AI app.

MCP standardizes this into an **N+M problem**: build a server once, any MCP-compatible client can use it.

---

## 3. Core Architecture

MCP follows a **client-server architecture** based on **JSON-RPC 2.0**.

```
┌────────────────┐         JSON-RPC 2.0         ┌────────────────┐
│  MCP Host      │  ◄──────────────────────►   │  MCP Server    │
│ (Claude, Cursor)│       (stdio / HTTP)        │ (your tool)    │
│                │                              │                │
│  ┌──────────┐  │                              │   - Tools      │
│  │MCP Client│  │                              │   - Resources  │
│  └──────────┘  │                              │   - Prompts    │
└────────────────┘                              └────────────────┘
                                                        │
                                                        ▼
                                            External APIs / DBs / Files
```

### Three Key Roles

| Role | Description | Examples |
|------|-------------|----------|
| **Host** | The AI application the user interacts with | Claude Desktop, Cursor, Windsurf, Cline |
| **Client** | The connector inside the host that maintains a 1:1 connection to a server | Built into the host |
| **Server** | A lightweight program exposing capabilities via MCP | GitHub MCP, Filesystem MCP, custom servers |

---

## 4. What an MCP Server Provides

An MCP server can expose **three primitives** to the AI:

### 4.1 Tools (Model-controlled)
Functions the LLM can **invoke** to perform actions.
- Example: `create_github_issue`, `query_database`, `send_slack_message`
- The model decides when to call them (with user approval).

### 4.2 Resources (Application-controlled)
Read-only **data** the AI can pull as context.
- Example: file contents, database records, API responses
- Identified by URIs (e.g., `file:///path/to/doc.txt`)

### 4.3 Prompts (User-controlled)
Reusable **prompt templates** users can invoke explicitly.
- Example: `/summarize-pr`, `/explain-code`
- Often surface as slash commands in the host UI.

---

## 5. Communication & Transports

MCP uses **JSON-RPC 2.0** messages over different transports:

| Transport | Use Case | Notes |
|-----------|----------|-------|
| **stdio** | Local servers running on the same machine | Most common for desktop apps |
| **HTTP + SSE** (legacy) | Remote servers | Server-Sent Events for streaming |
| **Streamable HTTP** | Modern remote servers | Replaced SSE in the 2025 spec revision |

### Typical Lifecycle
1. **Initialize** — handshake, exchange protocol version & capabilities
2. **Discovery** — client calls `tools/list`, `resources/list`, `prompts/list`
3. **Invocation** — client calls `tools/call`, `resources/read`, etc.
4. **Shutdown** — clean disconnection

---

## 6. A Minimal MCP Server Example (Python)

Using the official `mcp` SDK:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-server")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

@mcp.resource("greeting://{name}")
def greeting(name: str) -> str:
    """Return a personalized greeting."""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### TypeScript Equivalent

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "demo-server", version: "1.0.0" });

server.tool(
  "add",
  { a: z.number(), b: z.number() },
  async ({ a, b }) => ({
    content: [{ type: "text", text: String(a + b) }],
  })
);

await server.connect(new StdioServerTransport());
```

---

## 7. Configuring an MCP Server in a Host

Most hosts read a JSON config file. Example for **Cursor** (`.cursor/mcp.json`) or **Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\me\\docs"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"
      }
    }
  }
}
```

---

## 8. Popular MCP Servers (Ecosystem)

| Server | Purpose |
|--------|---------|
| **filesystem** | Read/write local files |
| **github** | Manage repos, issues, PRs |
| **gitlab** | GitLab equivalent |
| **postgres / sqlite** | Run SQL queries |
| **slack** | Send & read messages |
| **puppeteer / playwright** | Browser automation |
| **memory** | Persistent knowledge graph |
| **brave-search** | Web search |
| **google-drive** | Access Drive files |

A full curated list lives at: <https://github.com/modelcontextprotocol/servers>

---

## 9. Security Considerations

MCP servers are **powerful** — they can execute code, hit APIs, and read files. Best practices:

- **Principle of least privilege** — grant servers only the scopes/paths they need.
- **User approval** — hosts should prompt before tool invocation (most do by default).
- **Input validation** — validate every parameter from the LLM; treat it as untrusted.
- **Avoid prompt injection** — sanitize content returned from resources.
- **Pin server versions** — don't auto-update untrusted servers.
- **Run in sandboxes** — prefer Docker / containers for risky servers.
- **Secret management** — pass tokens via environment variables, never hardcode.

---

## 10. MCP vs. Function Calling vs. Plugins

| Aspect | OpenAI Function Calling | ChatGPT Plugins (deprecated) | **MCP** |
|--------|-------------------------|-------------------------------|---------|
| Standard | Vendor-specific | Vendor-specific | **Open & vendor-neutral** |
| Transport | HTTP API only | HTTPS (OpenAPI) | stdio / HTTP / SSE |
| Statefulness | Stateless | Stateless | **Stateful sessions** |
| Primitives | Tools only | Tools only | **Tools + Resources + Prompts** |
| Reusability | Per-vendor | OpenAI-only | **Any compatible host** |

---

## 11. Pros & Cons

### Pros
- Open standard with broad industry adoption (Anthropic, OpenAI, Google DeepMind, Microsoft).
- Write once, run in any compatible host.
- Rich primitives beyond just tools.
- Strong, well-documented SDKs (Python, TypeScript, C#, Java, Kotlin, Swift, Rust).

### Cons
- Still evolving — spec revisions can introduce breaking changes.
- Stdio transport is local-only; remote auth/security is still maturing.
- Tool descriptions count against context window — too many servers degrade model performance.
- Quality varies wildly across community-built servers.

---

## 12. Quick Start Checklist

1. **Pick a host** that supports MCP (Cursor, Claude Desktop, Windsurf, Cline, Zed…).
2. **Browse existing servers** at <https://github.com/modelcontextprotocol/servers>.
3. **Add one to your host's config** (JSON above).
4. **Restart the host** and verify the tools appear.
5. **Build your own** with the `mcp` Python SDK or `@modelcontextprotocol/sdk` for TypeScript.
6. **Test locally** with the **MCP Inspector** (`npx @modelcontextprotocol/inspector`).

---

## 13. Useful Links

- Official spec: <https://spec.modelcontextprotocol.io>
- Docs: <https://modelcontextprotocol.io>
- GitHub org: <https://github.com/modelcontextprotocol>
- Reference servers: <https://github.com/modelcontextprotocol/servers>
- MCP Inspector (debugging tool): <https://github.com/modelcontextprotocol/inspector>

---

*Last updated: May 2026*
