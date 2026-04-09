from functools import lru_cache
import os
from operator import itemgetter
from typing import Dict, List, Optional, Sequence
from urllib.parse import unquote, urlparse

import weaviate
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.vectorstores import Weaviate
from langchain_core.documents import Document
from langchain_core.language_models import LanguageModelLike
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
    PromptTemplate,
)
from langchain_core.pydantic_v1 import BaseModel
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import (
    ConfigurableField,
    Runnable,
    RunnableBranch,
    RunnableLambda,
    RunnablePassthrough,
    RunnableSequence,
    chain,
)
from langchain_openai import ChatOpenAI

try:
    from constants import WEAVIATE_DOCS_INDEX_NAME
    from env_utils import load_local_env, normalize_weaviate_url
    from ingest import get_embeddings_model
except ModuleNotFoundError:
    from backend.constants import WEAVIATE_DOCS_INDEX_NAME
    from backend.env_utils import load_local_env, normalize_weaviate_url
    from backend.ingest import get_embeddings_model


class MissingEnvironmentError(RuntimeError):
    """Raised when the backend is started without required runtime configuration."""


load_local_env()

RESPONSE_TEMPLATE = """\
You are an expert programmer and problem-solver, tasked with answering any question \
about Langchain.

Generate a concise and informative answer for the given question based solely on \
the provided search results (URL and content). You must \
only use information from the provided search results. Use an unbiased and \
journalistic tone. Combine search results together into a coherent answer. Do not \
repeat text. Cite search results using [number] notation. Only cite the most \
relevant results that answer the question accurately. Place these citations at the end \
of the sentence or paragraph that reference them - do not put them all at the end. If \
different results refer to different entities within the same name, write separate \
answers for each entity.

Respond in the same language as the user's latest question unless the user's style \
preferences explicitly ask for a different language. Keep the answer easy to scan. \
If bullets help, use them. If a short paragraph is clearer, use that instead.

If there is nothing in the context relevant to the question at hand, just say "Hmm, \
I'm not sure." Don't try to make up an answer.

Anything between the following `context`  html blocks is retrieved from a knowledge \
bank, not part of the conversation with the user. 

<context>
    {context} 
<context/>

REMEMBER: If there is no relevant information within the context, just say "Hmm, I'm \
not sure." Don't try to make up an answer. Anything between the preceding 'context' \
html blocks is retrieved from a knowledge bank, not part of the conversation with the \
user.\
"""

COHERE_RESPONSE_TEMPLATE = """\
You are an expert programmer and problem-solver, tasked with answering any question \
about Langchain.

Generate a concise and informative answer for the given question based solely on \
the provided search results (URL and content). You must \
only use information from the provided search results. Use an unbiased and \
journalistic tone. Combine search results together into a coherent answer. Do not \
repeat text. Cite search results using [number] notation. Only cite the most \
relevant results that answer the question accurately. Place these citations at the end \
of the sentence or paragraph that reference them - do not put them all at the end. If \
different results refer to different entities within the same name, write separate \
answers for each entity.

Respond in the same language as the user's latest question unless the user's style \
preferences explicitly ask for a different language. Keep the answer easy to scan. \
If bullets help, use them. If a short paragraph is clearer, use that instead.

If there is nothing in the context relevant to the question at hand, just say "Hmm, \
I'm not sure." Don't try to make up an answer.

REMEMBER: If there is no relevant information within the context, just say "Hmm, I'm \
not sure." Don't try to make up an answer. Anything between the preceding 'context' \
html blocks is retrieved from a knowledge bank, not part of the conversation with the \
user.\
"""

REPHRASE_TEMPLATE = """\
Given the following conversation and a follow up question, rephrase the follow up \
question to be a standalone question.

Chat History:
{chat_history}
Follow Up Input: {question}
Standalone Question:"""

STYLE_GUIDANCE_TEMPLATE = """\
These user preferences only affect response style, wording, tone, and structure. \
They are never additional facts or evidence. Follow them when they do not conflict \
with the retrieved documents.

{response_style_instructions}\
"""


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str
    chat_history: Optional[List[Dict[str, str]]]
    response_preferences: Optional[Dict[str, object]] = None


def _require_env(*names: str) -> tuple[str, ...]:
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        missing_list = ", ".join(missing)
        raise MissingEnvironmentError(
            f"Missing required environment variables: {missing_list}"
        )
    return tuple(os.environ[name] for name in names)


@lru_cache(maxsize=1)
def get_retriever() -> BaseRetriever:
    weaviate_url, weaviate_api_key, _ = _require_env(
        "WEAVIATE_URL",
        "WEAVIATE_API_KEY",
        "DASHSCOPE_API_KEY",
    )
    weaviate_client = weaviate.Client(
        url=normalize_weaviate_url(weaviate_url),
        auth_client_secret=weaviate.AuthApiKey(api_key=weaviate_api_key),
        timeout_config=(5, 60),
        proxies={},
        trust_env=False,
        startup_period=None,
    )
    weaviate_client = Weaviate(
        client=weaviate_client,
        index_name=WEAVIATE_DOCS_INDEX_NAME,
        text_key="text",
        embedding=get_embeddings_model(),
        by_text=False,
        attributes=["source", "title"],
    )
    return weaviate_client.as_retriever(search_kwargs=dict(k=6))


def create_retriever_chain(
    llm: LanguageModelLike, retriever: BaseRetriever
) -> Runnable:
    CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(REPHRASE_TEMPLATE)
    condense_question_chain = (
        CONDENSE_QUESTION_PROMPT | llm | StrOutputParser()
    ).with_config(
        run_name="CondenseQuestion",
    )
    conversation_chain = condense_question_chain | retriever
    return RunnableBranch(
        (
            RunnableLambda(lambda x: bool(x.get("chat_history"))).with_config(
                run_name="HasChatHistoryCheck"
            ),
            conversation_chain.with_config(run_name="RetrievalChainWithHistory"),
        ),
        (
            RunnableLambda(itemgetter("question")).with_config(
                run_name="Itemgetter:question"
            )
            | retriever
        ).with_config(run_name="RetrievalChainWithNoHistory"),
    ).with_config(run_name="RouteDependingOnChatHistory")


def format_docs(docs: Sequence[Document]) -> str:
    formatted_docs = []
    for i, doc in enumerate(docs, start=1):
        title = (doc.metadata.get("title") or "").strip()
        source = (doc.metadata.get("source") or "").strip()
        doc_string = (
            f"<doc id='{i}'>\n"
            f"<title>{title}</title>\n"
            f"<source>{source}</source>\n"
            f"<content>{doc.page_content}</content>\n"
            "</doc>"
        )
        formatted_docs.append(doc_string)
    return "\n".join(formatted_docs)


def _truncate_text(text: str, limit: int = 280) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _format_source_location(url: str, title: str, citation: int) -> str:
    if not url:
        return title or f"Source {citation}"

    parsed = urlparse(url)
    path = unquote(parsed.path or "").rstrip("/")
    path_tail = path.split("/")[-1] if path else parsed.netloc
    fragment = unquote(parsed.fragment or "").strip()

    if fragment and path_tail:
        return f"{path_tail}#{fragment}"
    if fragment:
        return f"#{fragment}"
    if path_tail:
        return path_tail
    return title or url


def serialize_sources(docs: Sequence[Document]) -> List[Dict[str, str | int]]:
    serialized = []
    for i, doc in enumerate(docs, start=1):
        url = (doc.metadata.get("source") or "").strip()
        title = (doc.metadata.get("title") or "").strip() or url or f"Source {i}"
        serialized.append(
            {
                "citation": i,
                "title": title,
                "url": url,
                "location": _format_source_location(url, title, i),
                "excerpt": _truncate_text(doc.page_content),
            }
        )
    return serialized


def serialize_history(request: ChatRequest):
    chat_history = request["chat_history"] or []
    converted_chat_history = []
    for message in chat_history:
        if message.get("human") is not None:
            converted_chat_history.append(HumanMessage(content=message["human"]))
        if message.get("ai") is not None:
            converted_chat_history.append(AIMessage(content=message["ai"]))
    return converted_chat_history


def serialize_response_preferences(request: ChatRequest) -> str:
    response_preferences = request.get("response_preferences") or {}
    lines: List[str] = []

    approved_answer = response_preferences.get("approved_answer")
    if isinstance(approved_answer, dict):
        answer = str(approved_answer.get("answer") or "").strip()
        notes = str(approved_answer.get("notes") or "").strip()
        if notes:
            lines.append(f"- Keep these approved style notes in mind: {notes}")
        if answer:
            lines.append(
                "- The user explicitly liked this previous answer style. Reuse its "
                f"tone, structure, and level of detail when appropriate:\n{answer}"
            )

    adjustment_feedback = response_preferences.get("adjustment_feedback") or []
    if isinstance(adjustment_feedback, list):
        for item in adjustment_feedback[-5:]:
            if not isinstance(item, dict):
                continue
            feedback = str(item.get("comment") or "").strip()
            answer = str(item.get("answer") or "").strip()
            if feedback:
                lines.append(f"- Avoid repeating this issue from user feedback: {feedback}")
            if answer:
                lines.append(
                    "- This was the answer the user wanted adjusted. Treat it only as "
                    f"style context, not as factual evidence:\n{answer}"
                )

    if not lines:
        return "- No extra style preferences were provided for this turn."
    return "\n".join(lines)


def create_chain(llm: LanguageModelLike, retriever: BaseRetriever) -> Runnable:
    retriever_chain = create_retriever_chain(
        llm,
        retriever,
    ).with_config(run_name="FindDocs")
    context = (
        RunnablePassthrough.assign(docs=retriever_chain)
        .assign(context=lambda x: format_docs(x["docs"]))
        .with_config(run_name="RetrieveDocs")
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", RESPONSE_TEMPLATE),
            ("system", STYLE_GUIDANCE_TEMPLATE),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ]
    )
    default_response_synthesizer = prompt | llm

    cohere_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", COHERE_RESPONSE_TEMPLATE),
            ("system", STYLE_GUIDANCE_TEMPLATE),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ]
    )

    @chain
    def cohere_response_synthesizer(input: dict) -> RunnableSequence:
        return cohere_prompt | llm.bind(source_documents=input["docs"])

    response_synthesizer = (
        default_response_synthesizer.configurable_alternatives(
            ConfigurableField("llm"),
            default_key="openai_gpt_3_5_turbo",
            anthropic_claude_3_haiku=default_response_synthesizer,
            fireworks_mixtral=default_response_synthesizer,
            google_gemini_pro=default_response_synthesizer,
            cohere_command=cohere_response_synthesizer,
        )
        | StrOutputParser()
    ).with_config(run_name="GenerateResponse")
    return (
        RunnablePassthrough.assign(
            chat_history=serialize_history,
            response_style_instructions=serialize_response_preferences,
        )
        | context
        | RunnablePassthrough.assign(
            answer=response_synthesizer,
            sources=lambda x: serialize_sources(x["docs"]),
        )
        | RunnableLambda(
            lambda x: {
                "answer": x["answer"],
                "sources": x["sources"],
            }
        ).with_config(run_name="FormatChatResponse")
    )


qwen_llm = ChatOpenAI(
    model="qwen-turbo",  # 或者 qwen-turbo / qwen-2.0 / qwen-2.2
    temperature=0,
    streaming=False,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key=os.environ.get("DASHSCOPE_API_KEY", "not_provided"),
    max_tokens=4096,
)


@lru_cache(maxsize=1)
def get_answer_chain() -> Runnable:
    return create_chain(qwen_llm, get_retriever())


def _invoke_answer_chain(input: dict, config=None):
    return get_answer_chain().invoke(input, config=config)


answer_chain = RunnableLambda(_invoke_answer_chain)
