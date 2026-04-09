"""Load html from files, clean up, split, ingest into Weaviate."""
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Optional

try:
    from constants import WEAVIATE_DOCS_INDEX_NAME
    from env_utils import load_local_env, normalize_weaviate_url
except ModuleNotFoundError:
    from backend.constants import WEAVIATE_DOCS_INDEX_NAME
    from backend.env_utils import load_local_env, normalize_weaviate_url

try:
    from parser import langchain_docs_extractor
except ModuleNotFoundError:
    # Support running as both script and package import.
    from backend.parser import langchain_docs_extractor

import weaviate
from bs4 import BeautifulSoup, SoupStrainer
import requests

try:
    from langchain_community.document_loaders import RecursiveUrlLoader, SitemapLoader
    from langchain_community.vectorstores import Weaviate
except ModuleNotFoundError as e:
    # region agent log
    import json
    import time

    log_entry = {
        "sessionId": "c00c62",
        "runId": "initial",
        "hypothesisId": "H_langchain_community_missing",
        "location": "backend/ingest.py:langchain_community_import",
        "message": "Failed to import langchain_community loaders/vectorstores",
        "data": {"error": str(e)},
        "timestamp": int(time.time() * 1000),
    }
    with open("debug-c00c62.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
    # endregion
    raise

try:
    from langchain_classic.indexes import SQLRecordManager, index
except ImportError:
    # Backward compatibility for older LangChain versions where indexes
    # live under `langchain.indexes`.
    from langchain.indexes import SQLRecordManager, index

from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from langchain.utils.html import PREFIXES_TO_IGNORE_REGEX, SUFFIXES_TO_IGNORE_REGEX
except ModuleNotFoundError as e:
    # region agent log
    import json
    import time

    log_entry = {
        "sessionId": "c00c62",
        "runId": "initial",
        "hypothesisId": "H_langchain_utils_missing",
        "location": "backend/ingest.py:langchain_utils_import",
        "message": "Failed to import PREFIXES_TO_IGNORE_REGEX/SUFFIXES_TO_IGNORE_REGEX from langchain.utils.html, falling back to defaults",
        "data": {"error": str(e)},
        "timestamp": int(time.time() * 1000),
    }
    with open("debug-c00c62.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
    # endregion
    # Fallback: no special prefix/suffix filtering
    PREFIXES_TO_IGNORE_REGEX = ""
    SUFFIXES_TO_IGNORE_REGEX = ".*?"

from langchain_core.embeddings import Embeddings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from openai import OpenAI
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

CURRENT_DOCS_SITEMAP_URL = "https://docs.langchain.com/sitemap.xml"
CURRENT_DOCS_PREFIXES = (
    "https://docs.langchain.com/oss/python/langchain/",
    "https://docs.langchain.com/oss/python/langgraph/",
    "https://docs.langchain.com/oss/python/common-errors",
)

## QwenEmbeddings模型
def _require_env(*names: str) -> tuple[str, ...]:
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variables: {missing_list}")
    return tuple(os.environ[name] for name in names)


DEFAULT_RECORD_MANAGER_DB_URL = "sqlite:///record_manager_local.db"


def _is_truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_record_manager_db_url() -> str:
    configured_url = os.environ.get("RECORD_MANAGER_DB_URL", "").strip()
    use_configured_record_manager = _is_truthy(
        os.environ.get("USE_CONFIGURED_RECORD_MANAGER")
    )

    if use_configured_record_manager:
        if not configured_url:
            raise RuntimeError(
                "USE_CONFIGURED_RECORD_MANAGER=true but RECORD_MANAGER_DB_URL is empty"
            )
        logger.info("Using configured record manager DB URL")
        return configured_url

    if configured_url.startswith("sqlite:///"):
        logger.info("Using configured SQLite record manager DB URL")
        return configured_url

    if configured_url:
        logger.warning(
            "Ignoring configured RECORD_MANAGER_DB_URL for baseline ingest. "
            "Set USE_CONFIGURED_RECORD_MANAGER=true to use it."
        )

    logger.info(
        "Using local SQLite record manager DB URL: %s",
        DEFAULT_RECORD_MANAGER_DB_URL,
    )
    return DEFAULT_RECORD_MANAGER_DB_URL


load_local_env()


class QwenEmbeddings(Embeddings):
    def __init__(
        self,
        model="text-embedding-v4",
        api_key=None,
        base_url=None,
        batch_size=10,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.batch_size = batch_size

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def embed_documents(self, texts):
        texts = [t.strip() for t in texts if t.strip()]
        if not texts:
            return []

        embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            # 核心修改1：将1024维向量补0到1536维
            for item in resp.data:
                vec = item.embedding  # 1024维
                vec += [0.0] * (1536 - len(vec))  # 补512个0，凑1536维
                embeddings.append(vec)
        return embeddings

    def embed_query(self, text):
        text = text.strip()
        if not text:
            return []

        resp = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        # 核心修改2：查询向量也补0到1536维
        vec = resp.data[0].embedding
        vec += [0.0] * (1536 - len(vec))
        return vec

## 换为Qwen
def get_embeddings_model() -> Embeddings:
    (dashscope_api_key,) = _require_env("DASHSCOPE_API_KEY")
    return QwenEmbeddings(
        model="text-embedding-v4",
        api_key=dashscope_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        batch_size=10,
    )


def metadata_extractor(meta: dict, soup: BeautifulSoup) -> dict:
    title = soup.find("title")
    description = soup.find("meta", attrs={"name": "description"})
    html = soup.find("html")
    return {
        "source": meta["loc"],
        "title": title.get_text() if title else "",
        "description": description.get("content", "") if description else "",
        "language": html.get("lang", "") if html else "",
        **meta,
    }


def load_langchain_docs():
    return SitemapLoader(
        "https://python.langchain.com/sitemap.xml",
        filter_urls=["https://python.langchain.com/"],
        parsing_function=langchain_docs_extractor,
        default_parser="lxml",
        bs_kwargs={
            "parse_only": SoupStrainer(
                name=("article", "title", "html", "lang", "content")
            ),
        },
        meta_function=metadata_extractor,
    ).load()


def _request_with_retries(
    url: str,
    *,
    timeout: int = 30,
    attempts: int = 3,
) -> requests.Response:
    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "chat-langchain-study/1.0"},
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "Request failed for %s on attempt %s/%s: %s",
                url,
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                time.sleep(attempt)

    assert last_error is not None
    raise last_error


def _iter_current_docs_urls() -> list[str]:
    response = _request_with_retries(CURRENT_DOCS_SITEMAP_URL, timeout=30)
    root = ET.fromstring(response.text)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [
        element.text.strip()
        for element in root.findall("sm:url/sm:loc", namespace)
        if element.text
    ]
    return [
        url
        for url in urls
        if any(url.startswith(prefix) for prefix in CURRENT_DOCS_PREFIXES)
    ]


def _extract_current_docs_page(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    content_root = soup.find(id="content") or soup.find(id="content-area") or soup
    return langchain_docs_extractor(content_root).strip()


def load_current_langchain_docs():
    docs = []
    urls = _iter_current_docs_urls()
    logger.info("Found %s current LangChain docs URLs", len(urls))

    for index, url in enumerate(urls, start=1):
        try:
            response = _request_with_retries(url, timeout=45)
            soup = BeautifulSoup(response.text, "lxml")
            title = ""
            title_tag = soup.find("title")
            if title_tag is not None:
                title = title_tag.get_text(strip=True)

            text = _extract_current_docs_page(response.text)
            if not text:
                logger.warning("Skipping empty docs page: %s", url)
                continue

            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": url,
                        "title": title or url,
                    },
                )
            )
            logger.info("Loaded current docs page %s/%s: %s", index, len(urls), url)
        except Exception as exc:
            logger.warning("Skipping docs page %s due to error: %s", url, exc)

    return docs


def load_langsmith_docs():
    return RecursiveUrlLoader(
        url="https://docs.smith.langchain.com/",
        max_depth=8,
        extractor=simple_extractor,
        prevent_outside=True,
        use_async=True,
        timeout=600,
        # Drop trailing / to avoid duplicate pages.
        link_regex=(
            f"href=[\"']{PREFIXES_TO_IGNORE_REGEX}((?:{SUFFIXES_TO_IGNORE_REGEX}.)*?)"
            r"(?:[\#'\"]|\/[\#'\"])"
        ),
        check_response_status=True,
    ).load()


def simple_extractor(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    return re.sub(r"\n\n+", "\n\n", soup.text).strip()


def load_api_docs():
    return RecursiveUrlLoader(
        url="https://api.python.langchain.com/en/latest/",
        max_depth=2,
        extractor=simple_extractor,
        prevent_outside=True,
        use_async=True,
        timeout=600,
        # Drop trailing / to avoid duplicate pages.
        link_regex=(
            f"href=[\"']{PREFIXES_TO_IGNORE_REGEX}((?:{SUFFIXES_TO_IGNORE_REGEX}.)*?)"
            r"(?:[\#'\"]|\/[\#'\"])"
        ),
        check_response_status=True,
        exclude_dirs=(
            "https://api.python.langchain.com/en/latest/_sources",
            "https://api.python.langchain.com/en/latest/_modules",
        ),
    ).load()


def ingest_docs():
    (
        WEAVIATE_URL,
        WEAVIATE_API_KEY,
        _,
    ) = _require_env(
        "WEAVIATE_URL",
        "WEAVIATE_API_KEY",
        "DASHSCOPE_API_KEY",
    )
    record_manager_db_url = get_record_manager_db_url()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=200)
    embedding = get_embeddings_model()

    client = weaviate.Client(
        url=normalize_weaviate_url(WEAVIATE_URL),
        auth_client_secret=weaviate.AuthApiKey(api_key=WEAVIATE_API_KEY),
        timeout_config=(5, 60),
        proxies={},
        trust_env=False,
        startup_period=None,
    )
    logger.info("Weaviate ready: %s", client.is_ready())
    vectorstore = Weaviate(
        client=client,
        index_name=WEAVIATE_DOCS_INDEX_NAME,
        text_key="text",
        embedding=embedding,
        by_text=False,
        attributes=["source", "title"],
    )

    record_manager = SQLRecordManager(
        f"weaviate/{WEAVIATE_DOCS_INDEX_NAME}", db_url=record_manager_db_url
    )
    record_manager.create_schema()

    docs_from_documentation = load_current_langchain_docs()
    logger.info(f"Loaded {len(docs_from_documentation)} docs from current documentation")
    # docs_from_langsmith = load_langsmith_docs()
    # logger.info(f"Loaded {len(docs_from_langsmith)} docs from Langsmith")

    docs_transformed = text_splitter.split_documents(
        docs_from_documentation
    )
    docs_transformed = [doc for doc in docs_transformed if len(doc.page_content) > 10]

    if not docs_transformed:
        raise RuntimeError("No documentation content was loaded for ingest")

    # We try to return 'source' and 'title' metadata when querying vector store and
    # Weaviate will error at query time if one of the attributes is missing from a
    # retrieved document.
    for doc in docs_transformed:
        if "source" not in doc.metadata:
            doc.metadata["source"] = ""
        if "title" not in doc.metadata:
            doc.metadata["title"] = ""

    indexing_stats = index(
        docs_transformed,
        record_manager,
        vectorstore,
        cleanup="full",
        source_id_key="source",
        force_update=(os.environ.get("FORCE_UPDATE") or "false").lower() == "true",
    )

    logger.info(f"Indexing stats: {indexing_stats}")
    num_vecs = client.query.aggregate(WEAVIATE_DOCS_INDEX_NAME).with_meta_count().do()
    logger.info(
        f"LangChain now has this many vectors: {num_vecs}",
    )


if __name__ == "__main__":
    ingest_docs()
