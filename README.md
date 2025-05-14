[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/sparfenyuk-mcp-telegram-badge.png)](https://mseep.ai/app/sparfenyuk-mcp-telegram)

# Telegram MCP server

- [Telegram MCP server](#telegram-mcp-server)
  - [About](#about)
  - [What is MCP?](#what-is-mcp)
  - [What does this server do?](#what-does-this-server-do)
  - [Practical use cases](#practical-use-cases)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
    - [Telegram API Configuration](#telegram-api-configuration)
    - [Claude Desktop Configuration](#claude-desktop-configuration)
    - [Telegram Configuration](#telegram-configuration)
  - [Development](#development)
    - [Getting started](#getting-started)
    - [Debugging the server in terminal](#debugging-the-server-in-terminal)
    - [Debugging the server in the Inspector](#debugging-the-server-in-the-inspector)
  - [Troubleshooting](#troubleshooting)
    - [Message 'Could not connect to MCP server mcp-telegram'](#message-could-not-connect-to-mcp-server-mcp-telegram)

## About

The server is a bridge between the Telegram API and the AI assistants and is based on the [Model Context Protocol](https://modelcontextprotocol.io).

> [!IMPORTANT]
> Ensure that you have read and understood the [Telegram API Terms of Service](https://core.telegram.org/api/terms) before using this server.
> Any misuse of the Telegram API may result in the suspension of your account.

<a href="https://glama.ai/mcp/servers/484jega1au">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/484jega1au/badge" alt="Telegram Server MCP server" />
</a>

## What is MCP?

The Model Context Protocol (MCP) is a system that lets AI apps, like Claude Desktop, connect to external tools and data sources. It gives a clear and safe way for AI assistants to work with local services and APIs while keeping the user in control.

## What does this server do?

As of not, the server provides read-only access to the Telegram API.

- [x] Get the list of dialogs (chats, channels, groups)
- [x] Get the list of (unread) messages in the given dialog
- [ ] Mark chanel as read
- [ ] Retrieve messages by date and time
- [ ] Download media files
- [ ] Get the list of contacts
- [ ] Draft a message
- ...

## Practical use cases

- [x] Create a summary of the unread messages
- [ ] Find contacts with upcoming birthdays and schedule a greeting
- [ ] Find discussions on a given topic, summarize them and provide a list of links

## Prerequisites

- [`uv` tool](https://docs.astral.sh/uv/getting-started/installation/)

## Installation

```bash
uv tool install git+https://github.com/sparfenyuk/mcp-telegram
```

> [!NOTE]
> If you have already installed the server, you can update it using `uv tool upgrade --reinstall` command.

> [!NOTE]
> If you want to delete the server, use the `uv tool uninstall mcp-telegram` command.

## Configuration

### Telegram API Configuration

Before you can use the server, you need to connect to the Telegram API.

1. Get the API ID and hash from [Telegram API](https://my.telegram.org/auth)
2. Run the following command:

   ```bash
   mcp-telegram sign-in --api-id <your-api-id> --api-hash <your-api-hash> --phone-number <your-phone-number>
   ```

   Enter the code you received from Telegram to connect to the API.

   The password may be required if you have two-factor authentication enabled.

> [!NOTE]
> To log out from the Telegram API, use the `mcp-telegram logout` command.

### Claude Desktop Configuration

Configure Claude Desktop to recognize the Exa MCP server.

1. Open the Claude Desktop configuration file:
   - in MacOS, the configuration file is located at `~/Library/Application Support/Claude/claude_desktop_config.json`
   - in Windows, the configuration file is located at `%APPDATA%\Claude\claude_desktop_config.json`

   > __Note:__
   > You can also find claude_desktop_config.json inside the settings of Claude Desktop app

2. Add the server configuration

    ```json
    {
      "mcpServers": {
        "mcp-telegram": {
            "command": "mcp-server",
            "env": {
              "TELEGRAM_API_ID": "<your-api-id>",
              "TELEGRAM_API_HASH": "<your-api-hash>",
            },
          }
        }
      }
    }
    ```

### Telegram Configuration

Before working with Telegram’s API, you need to get your own API ID and hash:

1. Login to your Telegram account with the phone number of the developer account to use.
1. Click under API Development tools.
1. A 'Create new application' window will appear. Fill in your application details. There is no need to enter any URL, and only the first two fields (App title and Short name) can currently be changed later.
1. Click on 'Create application' at the end. Remember that your API hash is secret and Telegram won’t let you revoke it. __Don’t post it anywhere!__

## Development

### Getting started

1. Clone the repository
2. Install the dependencies

   ```bash
   uv sync
   ```

3. Run the server

   ```bash
   uv run mcp-telegram --help
   ```

Tools can be added to the `src/mcp_telegram/tools.py` file.

How to add a new tool:

1. Create a new class that inherits from ToolArgs

   ```python
   class NewTool(ToolArgs):
       """Description of the new tool."""
       pass
   ```

   Attributes of the class will be used as arguments for the tool.
   The class docstring will be used as the tool description.

2. Implement the tool_runner function for the new class

   ```python
   @tool_runner.register
   async def new_tool(args: NewTool) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
       pass
   ```

   The function should return a sequence of TextContent, ImageContent or EmbeddedResource.
   The function should be async and accept a single argument of the new class.

3. Done! Restart the client and the new tool should be available.

Validation can accomplished either through Claude Desktop or by running the tool directly.

### Debugging the server in terminal

To run the tool directly, use the following command:

```bash

# List all available tools
uv run cli.py list-tools

# Run the concrete tool
uv run cli.py call-tool --name ListDialogs --arguments '{"unread": true}'
```

### Debugging the server in the Inspector

The MCP inspector is a tool that helps to debug the server using fancy UI. To run it, use the following command:

```bash
npx @modelcontextprotocol/inspector uv run mcp-telegram
```

> [!WARNING]
> Do not forget to define Environment Variables TELEGRAM_API_ID and TELEGRAM_API_HASH in the inspector.

## Troubleshooting

### Message 'Could not connect to MCP server mcp-telegram'

If you see the message 'Could not connect to MCP server mcp-telegram' in Claude Desktop, it means that the server configuration is incorrect.

Try the following:

- Use the full path to the `uv` binary in the configuration file
- Check the path to the cloned repository in the configuration file