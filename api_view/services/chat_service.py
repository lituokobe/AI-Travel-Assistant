"""Chat invocation and streaming service."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent.schema import ChatResponse, Message
from api_view.agent_loader import (
    create_config,
    create_travel_context,
    lifecycle_manager,
    new_thread_id,
)
from api_view.models.events import StreamInterruptEvent
from api_view.models.requests import ResumeRequest, UserContext
from api_view.services.message_converter import langchain_to_api_message, state_messages_to_api
from api_view.services.session_service import ensure_session, touch_session
from api_view.services.stream_mapper import map_agent_stream, _extract_interrupts
from agent.logger import logger


class ChatService:
    async def chat(
        self,
        message: str,
        thread_id: str | None,
        user: UserContext,
    ) -> ChatResponse:
        agent = await lifecycle_manager.ensure_ready()
        tid = thread_id or new_thread_id()
        ensure_session(tid, user.user_id, message)

        logger.info(
            "[user] thread=%s user=%s(%s) message=%r",
            tid,
            user.user_id,
            user.username,
            message,
        )

        config = create_config(tid, passenger_id=user.passenger_id)
        context = create_travel_context(user.user_id, user.username)

        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config=config,
            context=context,
        )

        touch_session(tid)

        messages = state_messages_to_api(result.get("messages", []))

        interrupts = _extract_interrupts(result, tid)
        state = await agent.aget_state(config)
        if state and state.interrupts:
            for intr in state.interrupts:
                interrupts.extend(_extract_interrupts({"__interrupt__": [intr]}, tid))

        for intr in interrupts:
            messages.append(
                Message(
                    id=f"interrupt-{intr.interrupt_id}",
                    role="interrupt",
                    content=json.dumps(intr.payload, ensure_ascii=False),
                    source="system",
                )
            )

        assistant_replies = [m for m in messages if m.role == "assistant" and m.content]
        if assistant_replies:
            logger.info("[reply|%s] %s", tid, assistant_replies[-1].content)

        return ChatResponse(thread_id=tid, messages=messages)

    async def stream(
        self,
        message: str,
        thread_id: str | None,
        user: UserContext,
    ) -> AsyncIterator[str]:
        agent = await lifecycle_manager.ensure_ready()
        tid = thread_id or new_thread_id()
        ensure_session(tid, user.user_id, message)

        logger.info(
            "[user] thread=%s user=%s(%s) message=%r",
            tid,
            user.user_id,
            user.username,
            message,
        )

        config = create_config(tid, passenger_id=user.passenger_id)
        context = create_travel_context(user.user_id, user.username)

        async for event in map_agent_stream(
            agent,
            {"messages": [HumanMessage(content=message)]},
            config,
            context,
            tid,
        ):
            yield event

        touch_session(tid)

    async def resume(self, request: ResumeRequest) -> ChatResponse:
        agent = await lifecycle_manager.ensure_ready()
        config = create_config(request.thread_id, passenger_id=request.user.passenger_id)
        context = create_travel_context(request.user.user_id, request.user.username)

        logger.info(
            "[resume] thread=%s user=%s(%s) value=%r",
            request.thread_id,
            request.user.user_id,
            request.user.username,
            request.resume_value,
        )

        result = await agent.ainvoke(
            Command(resume=request.resume_value),
            config=config,
            context=context,
        )

        touch_session(request.thread_id)
        messages = state_messages_to_api(result.get("messages", []))
        interrupts = _extract_interrupts(result, request.thread_id)
        state = await agent.aget_state(config)
        if state and state.interrupts:
            for intr in state.interrupts:
                interrupts.extend(
                    _extract_interrupts({"__interrupt__": [intr]}, request.thread_id)
                )
        for intr in interrupts:
            messages.append(
                Message(
                    id=f"interrupt-{intr.interrupt_id}",
                    role="interrupt",
                    content=json.dumps(intr.payload, ensure_ascii=False),
                    source="system",
                )
            )

        assistant_replies = [m for m in messages if m.role == "assistant" and m.content]
        if assistant_replies:
            logger.info("[reply|%s] %s", request.thread_id, assistant_replies[-1].content)

        return ChatResponse(thread_id=request.thread_id, messages=messages)

    async def resume_stream(self, request: ResumeRequest) -> AsyncIterator[str]:
        agent = await lifecycle_manager.ensure_ready()
        config = create_config(request.thread_id, passenger_id=request.user.passenger_id)
        context = create_travel_context(request.user.user_id, request.user.username)

        logger.info(
            "[resume] thread=%s user=%s(%s) value=%r",
            request.thread_id,
            request.user.user_id,
            request.user.username,
            request.resume_value,
        )

        async for event in map_agent_stream(
            agent,
            Command(resume=request.resume_value),
            config,
            context,
            request.thread_id,
        ):
            yield event

        touch_session(request.thread_id)


chat_service = ChatService()
