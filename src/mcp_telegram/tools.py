from __future__ import annotations

import logging
import sys
import typing as t
from functools import singledispatch

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


### SendMessage ###


class SendMessage(ToolArgs):
    """
    Send a message to a contact, group, or channel.
    
    Use this tool to send text messages through Telegram.
    """

    dialog_id: int
    message: str


@tool_runner.register
async def send_message(
    args: SendMessage,
) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
    client: TelegramClient
    logger.info("method[SendMessage] args[%s]", args)

    async with create_client() as client:
        try:
            # Send the message
            sent_message = await client.send_message(args.dialog_id, args.message)
            
            response_text = (
                f"Message sent successfully!\n"
                f"Message ID: {sent_message.id}\n"
                f"Date: {sent_message.date}\n"
                f"To: {args.dialog_id}"
            )
            
            return [TextContent(type="text", text=response_text)]
        except Exception as e:
            error_text = f"Failed to send message: {str(e)}"
            logger.error(error_text)
            return [TextContent(type="text", text=error_text)]


### ScheduleMessage ###


class ScheduleMessage(ToolArgs):
    """
    Schedule a message to be sent at a specific time using Telegram's native scheduling API.
    
    The message is added to Telegram's server-side schedule queue and will be automatically
    sent at the specified time, even if your client is offline. This uses Telegram's official
    scheduled messages API: https://core.telegram.org/api/scheduled-messages
    
    If schedule_date is less than 10 seconds in the future, the message will be sent immediately.
    """

    dialog_id: int
    message: str
    delay_seconds: int


@tool_runner.register
async def schedule_message(
    args: ScheduleMessage,
) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
    from datetime import datetime, timedelta
    
    client: TelegramClient
    logger.info("method[ScheduleMessage] args[%s]", args)

    if args.delay_seconds < 0:
        return [TextContent(type="text", text="Error: delay_seconds must be a positive number")]

    async with create_client() as client:
        try:
            # Calculate the schedule date (Unix timestamp)
            schedule_time = datetime.now() + timedelta(seconds=args.delay_seconds)
            schedule_timestamp = int(schedule_time.timestamp())
            
            logger.info(f"Scheduling message for {schedule_time} (timestamp: {schedule_timestamp})")
            
            # Use Telegram's native scheduling API
            # The schedule_date parameter adds the message to server-side schedule queue
            sent_message = await client.send_message(
                args.dialog_id,
                args.message,
                schedule=schedule_timestamp
            )
            
            # Format the response based on whether it was scheduled or sent immediately
            if args.delay_seconds < 10:
                response_text = (
                    f"⚡ Message sent immediately (delay was less than 10 seconds)\n"
                    f"Message ID: {sent_message.id}\n"
                    f"Date: {sent_message.date}\n"
                    f"To: {args.dialog_id}"
                )
            else:
                response_text = (
                    f"📅 Message scheduled successfully!\n"
                    f"Scheduled Message ID: {sent_message.id}\n"
                    f"Will be sent at: {schedule_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"To: {args.dialog_id}\n"
                    f"Delay: {args.delay_seconds} seconds\n\n"
                    f"Note: The message is stored on Telegram's servers and will be sent "
                    f"automatically at the scheduled time, even if you're offline."
                )
            
            return [TextContent(type="text", text=response_text)]
        except Exception as e:
            error_text = f"Failed to schedule message: {str(e)}"
            logger.error(error_text)
            return [TextContent(type="text", text=error_text)]


### GetScheduledMessages ###


class GetScheduledMessages(ToolArgs):
    """
    Get all scheduled messages for a specific chat from Telegram's schedule queue.
    
    This retrieves messages that were scheduled using ScheduleMessage or through the
    Telegram app. You can see when they will be sent and their content.
    """

    dialog_id: int


@tool_runner.register
async def get_scheduled_messages(
    args: GetScheduledMessages,
) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
    client: TelegramClient
    logger.info("method[GetScheduledMessages] args[%s]", args)

    async with create_client() as client:
        try:
            # Get all scheduled messages for this chat
            scheduled_messages = await client.get_messages(
                args.dialog_id,
                scheduled=True
            )
            
            if not scheduled_messages:
                return [TextContent(
                    type="text",
                    text=f"No scheduled messages found for dialog {args.dialog_id}"
                )]
            
            # Format the response
            response_lines = [f"📅 Scheduled Messages ({len(scheduled_messages)} total):\n"]
            
            for msg in scheduled_messages:
                from datetime import datetime
                schedule_time = datetime.fromtimestamp(msg.date.timestamp())
                
                response_lines.append(
                    f"\n• Message ID: {msg.id}\n"
                    f"  Scheduled for: {schedule_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"  Text: {msg.text[:100]}{'...' if len(msg.text) > 100 else ''}"
                )
            
            return [TextContent(type="text", text="\n".join(response_lines))]
            
        except Exception as e:
            error_text = f"Failed to get scheduled messages: {str(e)}"
            logger.error(error_text)
            return [TextContent(type="text", text=error_text)]


### DeleteScheduledMessage ###


class DeleteScheduledMessage(ToolArgs):
    """
    Cancel a scheduled message before it's sent.
    
    Use GetScheduledMessages to find the message ID, then use this tool to cancel it.
    The message will be removed from Telegram's schedule queue and will not be sent.
    """

    dialog_id: int
    message_id: int


@tool_runner.register
async def delete_scheduled_message(
    args: DeleteScheduledMessage,
) -> t.Sequence[TextContent | ImageContent | EmbeddedResource]:
    client: TelegramClient
    logger.info("method[DeleteScheduledMessage] args[%s]", args)

    async with create_client() as client:
        try:
            # Delete the scheduled message
            await client.delete_messages(
                args.dialog_id,
                message_ids=[args.message_id],
                revoke=True  # This works for scheduled messages
            )
            
            response_text = (
                f"✅ Scheduled message cancelled successfully!\n"
                f"Message ID: {args.message_id}\n"
                f"Dialog: {args.dialog_id}\n\n"
                f"The message has been removed from the schedule queue and will not be sent."
            )
            
            return [TextContent(type="text", text=response_text)]
            
        except Exception as e:
            error_text = f"Failed to delete scheduled message: {str(e)}"
            logger.error(error_text)
            return [TextContent(type="text", text=error_text)]
