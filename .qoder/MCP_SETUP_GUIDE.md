# MCP Servers & Tools Setup Guide

## ✅ Successfully Installed

### Python Tools
- **pytest** v9.1.0 - Python testing framework
- **ruff** v0.15.17 - Extremely fast Python linter and formatter
- **uv** v0.11.16 - Fast Python package installer

Installed via: `uv pip install pytest ruff`

---

## 🔧 MCP Servers Configuration

MCP servers are **not installed as skills** - they are configured in your Qoder MCP settings and run on-demand via npx/uvx.

### Configuration File Created
📄 `.qoder/mcp-config.json` - Contains all MCP server configurations

### Available MCP Servers

#### ✅ Ready to Use (No API Key Required)
1. **fetch** - Web content fetching for LLMs
2. **memory** - Knowledge graph-based persistent memory
3. **filesystem** - Secure file operations (configured for your workspace)

#### 🔑 Requires API Key/Configuration
1. **postgres** - PostgreSQL database access
   - Update connection string: `postgresql://localhost:5432/your_database`
   - Set `"disabled": false` when ready

2. **redis** - Redis key-value store access
   - Update connection string: `redis://localhost:6379`
   - Note: Official server is archived, may need community alternative
   - Set `"disabled": false` when ready

3. **brave-search** - Web search via Brave API
   - Get API key: https://brave.com/search/api/
   - Add key to `BRAVE_API_KEY` env var
   - Set `"disabled": false` when ready

4. **postman** - Postman API integration
   - Get API key from Postman settings
   - Add key to `POSTMAN_API_KEY` env var
   - Package name may vary - verify on npm registry

5. **docker** - Docker container management
   - May require community implementation
   - Check: https://github.com/modelcontextprotocol/servers

---

## 📋 Next Steps

### 1. Enable MCP Servers in Qoder
Copy the enabled servers from `.qoder/mcp-config.json` to your Qoder MCP settings:
- Open Qoder Settings → MCP
- Add the server configurations you want to use
- Remove `"disabled": true` and `"note"` fields before adding

### 2. Configure Database Connections
For postgres/redis:
```json
{
  "postgres": {
    "command": "cmd",
    "args": ["/c", "npx", "-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@host:5432/dbname"]
  }
}
```

### 3. Get API Keys
- **Brave Search**: https://brave.com/search/api/
- **Postman**: Account Settings → API Keys

### 4. Verify Installation
```powershell
# Test pytest
pytest --version

# Test ruff
ruff --version

# Test MCP servers (they should start and wait for requests)
npx -y @modelcontextprotocol/server-fetch
```

---

## 📚 References
- MCP Servers Repository: https://github.com/modelcontextprotocol/servers
- MCP Registry: https://registry.modelcontextprotocol.io/
- MCP Documentation: https://modelcontextprotocol.io/

---

## ⚠️ Notes
- MCP servers run on-demand via npx - no permanent installation needed
- Servers marked `"disabled": true` need configuration before use
- Docker MCP server may not exist in official repo - check community alternatives
- Redis MCP server is archived in the official repo
- All Windows npx commands require `cmd /c` wrapper in MCP configs
