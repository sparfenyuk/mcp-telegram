from __future__ import annotations

import logging
import re
import sys
import typing as t
from functools import singledispatch

import httpx

from mcp.types import (
    EmbeddedResource,
    ImageContent,
    TextContent,
    Tool,
)
from pydantic import BaseModel, ConfigDict
from telethon import TelegramClient, custom, functions, types  # type: ignore[import-untyped]

from .telegram import create_client

logger = logging.getLogger(__name__)


# How to add a new tool:
#
# 1. Create a new class that inherits from ToolArgs
#    ```python
#    class NewTool(ToolArgs):
#        """Description of the new tool."""
#        pass
#    ```
#    Attributes of the class will be used as arguments for the tool.
#    The class docstring will be used as the tool description.
#
# 2. Implement the tool_runner function for the new class
#    ```python
#    @tool_runner.register
#    async def new_tool(args: NewTool) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
#        pass
#    ```
#    The function should return a sequence of TextContent, ImageContent or EmbeddedResource.
#    The function should be async and accept a single argument of the new class.
#
# 3. Done! Restart the client and the new tool should be available.


class ToolArgs(BaseModel):
    model_config = ConfigDict()


@singledispatch
async def tool_runner(
    args,  # noqa: ANN001
) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
    raise NotImplementedError(f"Unsupported type: {type(args)}")


def tool_description(args: type[ToolArgs]) -> Tool:
    return Tool(
        name=args.__name__,
        description=args.__doc__,
        inputSchema=args.model_json_schema(),
    )


def tool_args(tool: Tool, *args, **kwargs) -> ToolArgs:  # noqa: ANN002, ANN003
    return sys.modules[__name__].__dict__[tool.name](*args, **kwargs)


### ListDialogs ###


class ListDialogs(ToolArgs):
    """List available dialogs, chats and channels."""

    unread: bool = False
    archived: bool = False
    ignore_pinned: bool = False


@tool_runner.register
async def list_dialogs(
    args: ListDialogs,
) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
    client: TelegramClient
    logger.info("method[ListDialogs] args[%s]", args)

    response: list[TextContent] = []
    async with create_client() as client:
        dialog: custom.dialog.Dialog
        async for dialog in client.iter_dialogs(archived=args.archived, ignore_pinned=args.ignore_pinned):
            if args.unread and dialog.unread_count == 0:
                continue
            msg = (
                f"name='{dialog.name}' id={dialog.id} "
                f"unread={dialog.unread_count} mentions={dialog.unread_mentions_count}"
            )
            response.append(TextContent(type="text", text=msg))

    return response


### ListMessages ###


class ListMessages(ToolArgs):
    """
    List messages in a given dialog, chat or channel. The messages are listed in order from newest to oldest.

    If `unread` is set to `True`, only unread messages will be listed. Once a message is read, it will not be
    listed again.

    If `limit` is set, only the last `limit` messages will be listed. If `unread` is set, the limit will be
    the minimum between the unread messages and the limit.
    """

    dialog_id: int
    unread: bool = False
    limit: int = 100


@tool_runner.register
async def list_messages(
    args: ListMessages,
) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
    client: TelegramClient
    logger.info("method[ListMessages] args[%s]", args)

    response: list[TextContent] = []
    async with create_client() as client:
        result = await client(functions.messages.GetPeerDialogsRequest(peers=[args.dialog_id]))
        if not result:
            raise ValueError(f"Channel not found: {args.dialog_id}")

        if not isinstance(result, types.messages.PeerDialogs):
            raise TypeError(f"Unexpected result: {type(result)}")

        for dialog in result.dialogs:
            logger.debug("dialog: %s", dialog)
        for message in result.messages:
            logger.debug("message: %s", message)

        iter_messages_args: dict[str, t.Any] = {
            "entity": args.dialog_id,
            "reverse": False,
        }
        if args.unread:
            iter_messages_args["limit"] = min(dialog.unread_count, args.limit)
        else:
            iter_messages_args["limit"] = args.limit

        logger.debug("iter_messages_args: %s", iter_messages_args)
        async for message in client.iter_messages(**iter_messages_args):
            logger.debug("message: %s", type(message))
            if isinstance(message, custom.Message) and message.text:
                logger.debug("message: %s", message.text)
                response.append(TextContent(type="text", text=message.text))

    return response


### FetchMessageLink ###


class FetchMessageLink(ToolArgs):
    """
    Fetch content from a URL found in a Telegram message.

    This tool safely retrieves web content from links that appear in Telegram messages.
    It validates that the URL actually came from the specified message before fetching,
    providing security against arbitrary URL access.

    Particularly useful for reading Telegraph articles and other web content shared
    in Telegram channels without triggering web_fetch security restrictions.
    """

    dialog_id: int
    message_id: int
    url: str


@tool_runner.register
async def fetch_message_link(
    args: FetchMessageLink,
) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
    client: TelegramClient
    logger.info("method[FetchMessageLink] args[%s]", args)

    # Step 1: Verify URL comes from the specified message (security check)
    async with create_client() as client:
        message = await client.get_messages(args.dialog_id, ids=args.message_id)

        if not message:
            raise ValueError(f"Message {args.message_id} not found in dialog {args.dialog_id}")

        if not message.text:
            raise ValueError(f"Message {args.message_id} has no text content")

        if args.url not in message.text:
            raise ValueError(
                f"URL '{args.url}' not found in message {args.message_id}. "
                f"Security check failed: URL must be from a verified Telegram message."
            )

    # Step 2: Fetch URL content
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http_client:
        try:
            response = await http_client.get(args.url)
            response.raise_for_status()
            content = response.text

            # Step 3: Extract Telegraph article content if applicable
            if "telegra.ph" in args.url or "telegraph" in args.url.lower():
                # Extract main article content from Telegraph HTML
                match = re.search(
                    r'<article[^>]*id="_tl_editor"[^>]*>(.*?)</article>',
                    content,
                    re.DOTALL | re.IGNORECASE,
                )
                if match:
                    article_html = match.group(1)
                    # Remove HTML tags for cleaner text
                    article_text = re.sub(r"<[^>]+>", " ", article_html)
                    # Clean up whitespace
                    article_text = re.sub(r"\s+", " ", article_text).strip()
                    content = f"📰 Telegraph Article from {args.url}\n\n{article_text}"
                else:
                    # Fallback: basic HTML cleaning
                    content = re.sub(r"<[^>]+>", " ", content)
                    content = re.sub(r"\s+", " ", content).strip()[:10000]

            # Limit content length to avoid context overflow
            if len(content) > 15000:
                content = content[:15000] + "\n\n[Content truncated for length...]"

            return [TextContent(type="text", text=f"✅ Content from {args.url}\n\n{content}")]

        except httpx.HTTPError as e:
            error_msg = f"Failed to fetch {args.url}: {str(e)}"
            logger.error(error_msg)
            return [TextContent(type="text", text=f"❌ {error_msg}")]
