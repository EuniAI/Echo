from typing import Sequence

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ToolMessage,
)
from langchain_core.output_parsers import StrOutputParser


def get_last_message_content(messages: Sequence[BaseMessage]) -> str:
    output_parser = StrOutputParser()
    return output_parser.invoke(messages[-1])


def format_agent_tool_message_history(messages: Sequence[BaseMessage]) -> str:
    formatted_messages = []
    for message in messages:
        if isinstance(message, AIMessage):
            if message.content:
                formatted_messages.append(f"Assistant internal thought: {message.content}")
            if (
                message.additional_kwargs
                and "tool_calls" in message.additional_kwargs
                and message.additional_kwargs["tool_calls"]
            ):
                for tool_call in message.additional_kwargs["tool_calls"]:
                    formatted_messages.append(f"Assistant executed tool: {tool_call['function']}")
        elif isinstance(message, ToolMessage):
            formatted_messages.append(f"Tool output: {message.content}")
    return "\n\n".join(formatted_messages)
