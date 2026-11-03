"""실제 ChatOpenAI · OpenAIEmbeddings 클라이언트가 설정한 base_url로 호출되는지 — OpenAI 형식의 로컬 서버로 확인."""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn
import yaml
from fastapi import FastAPI, Request


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def openai_server():
    app = FastAPI()
    seen = {"chat": [], "emb": [], "auth": []}

    @app.post("/v1/chat/completions")
    async def chat(req: Request):
        body = await req.json()
        seen["chat"].append(body)
        seen["auth"].append(req.headers.get("authorization"))
        return {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "안녕하세요 [근거 1]"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

    @app.post("/v1/embeddings")
    async def emb(req: Request):
        body = await req.json()
        seen["emb"].append(body)
        inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
        return {"object": "list", "model": body["model"], "usage": {"prompt_tokens": 1, "total_tokens": 1},
                "data": [{"object": "embedding", "index": i, "embedding": [0.1 * (i + 1)] * 8} for i in range(len(inputs))]}

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1/", seen
    server.should_exit = True
    t.join(timeout=5)


def test_real_clients_use_config(env, openai_server, monkeypatch):
    base_url, seen = openai_server
    cfg = yaml.safe_load(env.cfg_path.read_text(encoding="utf-8"))
    cfg["llm"]["base_url"] = base_url
    env.cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("GMS_KEY", "test-key-123")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")   # 사내 프록시가 있어도 로컬 서버로
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")

    from core import config, llm
    config.reload_settings()
    llm.set_overrides()          # 가짜 모델 해제 → 진짜 클라이언트

    assert llm.has_api_key()
    reply = llm.chat([("system", "시스템"), ("human", "질문")])
    assert reply == "안녕하세요 [근거 1]"
    body = seen["chat"][0]
    assert body["model"] == "gpt-5.4-nano"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert seen["auth"][0] == "Bearer test-key-123"

    vecs = llm.get_embeddings().embed_documents(["숭례문", "다보탑"])
    assert len(vecs) == 2 and len(vecs[0]) == 8
    assert seen["emb"][0]["model"] == "text-embedding-3-small"
    # 토큰 ID가 아니라 원문 문자열을 보낸다 (check_embedding_ctx_length=False)
    assert seen["emb"][0]["input"] == ["숭례문", "다보탑"]
