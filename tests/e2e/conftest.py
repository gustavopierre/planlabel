"""Servidor real (uvicorn em thread) com fontes e modelos falsos, e navegador Chromium."""

from __future__ import annotations

import random
import socket
import threading
import time
from dataclasses import dataclass, field

import pytest
import uvicorn

from planlabel.api import create_app
from planlabel.repository import Repository
from planlabel.usage import QuotaTracker
from tests.conftest import FakeAdvisor, FakeDecider, FakeSource, fake_sources

pytestmark = pytest.mark.e2e


class EchoTranslator:
    def translate(self, text: str) -> str:
        return f"PT: {text}"


@dataclass
class Server:
    url: str
    repo: Repository
    sources: list[FakeSource]
    deciders: dict[int, FakeDecider]
    advisor: FakeAdvisor
    _server: uvicorn.Server = field(repr=False)
    _thread: threading.Thread = field(repr=False)

    def label_count(self) -> int:
        return self.repo.counts().total

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def start_server(tmp_path):
    servers: list[Server] = []

    def start(
        *,
        answer1=("wind", "energy"),
        answer2=("wind", "energy"),
        delay=0.0,
        sources=None,
        advisor=None,
    ) -> Server:
        repo = Repository(tmp_path / f"labels{len(servers)}.sqlite3")
        deciders = {
            1: FakeDecider(
                1,
                "gemini-decision-1",
                answer1,
                delay=delay,
                tracker=QuotaTracker(repo, "gemini-decision-1", rpm=200, rpd=10000),
            ),
            2: FakeDecider(
                2,
                "typesafe/jev-1.14",
                answer2,
                delay=delay,
                tracker=QuotaTracker(repo, "typesafe/jev-1.14"),
            ),
        }
        srcs = sources if sources is not None else fake_sources(100)
        adv = advisor or FakeAdvisor()
        app = create_app(
            repo=repo,
            sources=srcs,
            deciders=deciders,
            advisor=adv,
            translator=EchoTranslator(),
            rng=random.Random(7),
        )
        port = _free_port()
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        s = Server(f"http://127.0.0.1:{port}", repo, srcs, deciders, adv, server, thread)
        servers.append(s)
        return s

    yield start
    for s in servers:
        s.stop()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    pg = context.new_page()
    pg.set_default_timeout(8000)
    yield pg
    context.close()
