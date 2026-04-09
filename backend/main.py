"""Main entrypoint for the app."""

import asyncio
import os
from functools import partial
from typing import Literal, Optional, Union
from uuid import UUID, uuid4

import langsmith
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langserve import add_routes
from langsmith import Client
from pydantic import BaseModel

try:
    from env_utils import load_local_env
except ModuleNotFoundError:
    from backend.env_utils import load_local_env

try:
    from chain import ChatRequest, MissingEnvironmentError, answer_chain
except ModuleNotFoundError:
    from backend.chain import ChatRequest, MissingEnvironmentError, answer_chain

try:
    from persistence import get_persistence_store
except ModuleNotFoundError:
    from backend.persistence import get_persistence_store


load_local_env()


def _build_langsmith_client() -> Optional[Client]:
    if not os.environ.get("LANGCHAIN_API_KEY"):
        return None
    return Client()


def _get_cors_origins() -> list[str]:
    configured_origins = os.environ.get("BACKEND_CORS_ORIGINS", "").strip()
    if not configured_origins:
        return ["*"]
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]


client = _build_langsmith_client()


def _require_langsmith_client() -> Client:
    if client is None:
        raise HTTPException(status_code=503, detail="LangSmith is not configured")
    return client


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(MissingEnvironmentError)
async def handle_missing_environment_error(
    request: Request, exc: MissingEnvironmentError
):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


add_routes(
    app,
    answer_chain,
    path="/chat",
    input_type=ChatRequest,
    config_keys=["metadata", "configurable", "tags"],
)


class SendFeedbackBody(BaseModel):
    run_id: UUID
    key: str = "user_score"

    score: Union[float, int, bool, None] = None
    feedback_id: Optional[UUID] = None
    comment: Optional[str] = None


@app.post("/feedback")
async def send_feedback(body: SendFeedbackBody):
    _require_langsmith_client().create_feedback(
        body.run_id,
        body.key,
        score=body.score,
        comment=body.comment,
        feedback_id=body.feedback_id,
    )
    return {"result": "posted feedback successfully", "code": 200}


class UpdateFeedbackBody(BaseModel):
    feedback_id: UUID
    score: Union[float, int, bool, None] = None
    comment: Optional[str] = None


@app.patch("/feedback")
async def update_feedback(body: UpdateFeedbackBody):
    feedback_id = body.feedback_id
    if feedback_id is None:
        return {
            "result": "No feedback ID provided",
            "code": 400,
        }
    _require_langsmith_client().update_feedback(
        feedback_id,
        score=body.score,
        comment=body.comment,
    )
    return {"result": "patched feedback successfully", "code": 200}


class ChatApiRequest(BaseModel):
    client_id: str
    conversation_id: str
    question: str
    llm: str = "openai_gpt_3_5_turbo"


class MessageFeedbackBody(BaseModel):
    client_id: str
    message_id: str
    rating: Literal["good", "bad"]
    comment: Optional[str] = None


def _build_chat_config(body: ChatApiRequest) -> dict:
    return {
        "configurable": {"llm": body.llm},
        "tags": [f"model:{body.llm}"],
        "metadata": {
            "conversation_id": body.conversation_id,
            "client_id": body.client_id,
            "llm": body.llm,
        },
    }


def _sync_langsmith_feedback_if_possible(
    *,
    run_id: Optional[str],
    rating: str,
    comment: Optional[str],
) -> None:
    if client is None or not run_id:
        return

    score = 1 if rating == "good" else 0
    client.create_feedback(
        run_id,
        "user_score",
        score=score,
        comment=comment,
    )


# TODO: Update when async API is available
async def _arun(func, *args, **kwargs):
    bound = partial(func, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(None, bound)


async def aget_trace_url(run_id: str) -> str:
    langsmith_client = _require_langsmith_client()
    for i in range(5):
        try:
            await _arun(langsmith_client.read_run, run_id)
            break
        except langsmith.utils.LangSmithError:
            await asyncio.sleep(1**i)

    if await _arun(langsmith_client.run_is_shared, run_id):
        return await _arun(langsmith_client.read_run_shared_link, run_id)
    return await _arun(langsmith_client.share_run, run_id)


class GetTraceBody(BaseModel):
    run_id: UUID


@app.post("/get_trace")
async def get_trace(body: GetTraceBody):
    run_id = body.run_id
    if run_id is None:
        return {
            "result": "No LangSmith run ID provided",
            "code": 400,
        }
    return await aget_trace_url(str(run_id))


@app.get("/api/session")
async def get_session(
    client_id: str = Query(...),
    conversation_id: str = Query(...),
):
    store = get_persistence_store()
    await _arun(store.ensure_conversation, conversation_id, client_id)
    response_preferences = await _arun(store.get_response_preferences, client_id)
    messages = await _arun(store.list_conversation_messages, conversation_id)

    return {
        "client_id": client_id,
        "conversation_id": conversation_id,
        "response_preferences": response_preferences,
        "messages": messages,
    }


@app.delete("/api/response_preferences/{client_id}")
async def reset_response_preferences(client_id: str):
    store = get_persistence_store()
    response_preferences = await _arun(store.clear_response_preferences, client_id)
    return {
        "client_id": client_id,
        "response_preferences": response_preferences,
    }


@app.post("/api/chat")
async def chat(body: ChatApiRequest):
    store = get_persistence_store()
    await _arun(store.ensure_conversation, body.conversation_id, body.client_id)
    response_preferences = await _arun(store.get_response_preferences, body.client_id)
    chat_history = await _arun(store.build_chat_history, body.conversation_id)

    chain_input = {
        "question": body.question,
        "chat_history": chat_history,
        "response_preferences": response_preferences,
    }
    result = await _arun(answer_chain.invoke, chain_input, _build_chat_config(body))

    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="Chat chain returned an invalid response")

    answer = str(result.get("answer") or "")
    sources = result.get("sources") or []
    assistant_run_id = result.get("run_id")

    user_message = await _arun(
        store.create_message,
        message_id=str(uuid4()),
        conversation_id=body.conversation_id,
        client_id=body.client_id,
        role="user",
        content=body.question,
        run_id=None,
        sources=[],
    )
    assistant_message = await _arun(
        store.create_message,
        message_id=str(uuid4()),
        conversation_id=body.conversation_id,
        client_id=body.client_id,
        role="assistant",
        content=answer,
        run_id=assistant_run_id,
        sources=sources,
    )

    return {
        "client_id": body.client_id,
        "conversation_id": body.conversation_id,
        "response_preferences": response_preferences,
        "user_message": user_message,
        "assistant_message": assistant_message,
    }


@app.post("/api/message_feedback")
async def message_feedback(body: MessageFeedbackBody):
    store = get_persistence_store()
    try:
        response_preferences = await _arun(
            store.apply_feedback,
            client_id=body.client_id,
            message_id=body.message_id,
            rating=body.rating,
            comment=body.comment,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    message = await _arun(store.get_message, body.message_id)
    await _arun(
        _sync_langsmith_feedback_if_possible,
        run_id=message.get("runId"),
        rating=body.rating,
        comment=body.comment,
    )

    return {
        "message_id": body.message_id,
        "response_preferences": response_preferences,
        "message": message,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
