"""`python -m planlabel`: sobe o app em PLANLABEL_HOST:PLANLABEL_PORT (padrão 127.0.0.1:8000)."""

import logging

import uvicorn

from planlabel.api import build_app
from planlabel.config import Settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = Settings()
    uvicorn.run(build_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
