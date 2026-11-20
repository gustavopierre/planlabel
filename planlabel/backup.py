"""Backup diário do SQLite para o Google Drive (SPEC §9).

Roda num container separado (`planlabel-backup`, `Dockerfile.backup`) que monta o mesmo
volume do app. Só usa a biblioteca padrão: o container copia este arquivo sozinho, sem o
resto do pacote.

A cada 5 minutos confere se está na hora (`BACKUP_HOUR`, fuso `TZ`) e se o último sucesso
tem mais de 22 h. Se sim: cópia consistente com a API de backup do SQLite (pega também o
que ainda está no `-wal`), `PRAGMA integrity_check` na cópia, gzip, `rclone copyto` para
`BACKUP_REMOTE` e poda das cópias mais velhas que `BACKUP_RETENTION`.

    python backup.py          # serviço (loop)
    python backup.py --now    # uma execução agora; código de saída 0 = ok
    python backup.py --restore planlabel_AAAA-MM-DD_HHMM.sqlite3.gz   # app parado!
"""

from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

Rclone = Callable[[list[str]], bool]

MIN_GAP = timedelta(hours=22)
TICK_S = 300


@dataclass(frozen=True)
class Config:
    db_path: Path
    remote: str
    retention: str
    hour: int
    rclone_config: Path
    marker: Path
    workdir: Path

    @classmethod
    def from_env(cls) -> Config:
        db = Path(os.environ.get("PLANLABEL_DB_PATH", "/app/data/labels.sqlite3"))
        return cls(
            db_path=db,
            remote=os.environ.get("BACKUP_REMOTE", "gdrive:planlabel-test-backups"),
            retention=os.environ.get("BACKUP_RETENTION", "60d"),
            hour=int(os.environ.get("BACKUP_HOUR", "2")),
            rclone_config=Path(os.environ.get("RCLONE_CONFIG", "/config/rclone.conf")),
            marker=db.parent / "backup-last-ok",
            workdir=Path(os.environ.get("BACKUP_WORKDIR", "/tmp/planlabel-backup")),
        )


@dataclass(frozen=True)
class Result:
    status: str  # ok | skip | waiting | error
    message: str
    file: str | None = None


def is_due(now: datetime, hour: int, last_ok: datetime | None) -> bool:
    if now.hour != hour:
        return False
    return last_ok is None or now - last_ok >= MIN_GAP


def read_marker(path: Path) -> datetime | None:
    try:
        return datetime.fromisoformat(path.read_text().strip())
    except (OSError, ValueError):
        return None


def subprocess_rclone(args: list[str]) -> bool:
    return subprocess.run(args, check=False).returncode == 0


def _snapshot(src: Path, dest: Path) -> int:
    """Copia consistente + verificação; devolve o número de rótulos."""
    with closing(sqlite3.connect(src, timeout=30)) as s, closing(sqlite3.connect(dest)) as d:
        s.backup(d)
    with closing(sqlite3.connect(dest)) as d:
        check = d.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise sqlite3.DatabaseError(f"integrity_check: {check}")
        return d.execute("SELECT count(*) FROM labeled_application").fetchone()[0]


def run_once(
    cfg: Config, rclone: Rclone = subprocess_rclone, now: datetime | None = None
) -> Result:
    now = now or datetime.now()
    if not cfg.db_path.exists():
        return Result("skip", f"{cfg.db_path} ainda não existe; nada a copiar")
    if not cfg.rclone_config.exists():
        return Result("waiting", f"{cfg.rclone_config} não existe (runbook backup-sqlite)")

    name = f"planlabel_{now:%Y-%m-%d_%H%M}.sqlite3.gz"
    cfg.workdir.mkdir(parents=True, exist_ok=True)
    raw = cfg.workdir / name.removesuffix(".gz")
    packed = cfg.workdir / name
    try:
        try:
            labels = _snapshot(cfg.db_path, raw)
        except sqlite3.Error as exc:
            return Result("error", f"cópia do SQLite falhou: {exc}")
        with raw.open("rb") as fin, gzip.open(packed, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        base = ["rclone", "--config", str(cfg.rclone_config)]
        if not rclone([*base, "copyto", str(packed), f"{cfg.remote}/{name}"]):
            return Result("error", "envio ao Google Drive falhou (rede ou autorização do rclone)")
        # A poda nunca derruba um backup que já foi enviado.
        rclone([*base, "delete", "--min-age", cfg.retention, cfg.remote])
        cfg.marker.write_text(now.isoformat())
        size = packed.stat().st_size
        return Result("ok", f"{name} ({labels} rótulos, {size} bytes) enviado", name)
    finally:
        raw.unlink(missing_ok=True)
        packed.unlink(missing_ok=True)


def restore(
    cfg: Config, name: str, rclone: Rclone = subprocess_rclone, now: datetime | None = None
) -> Result:
    """Troca o banco pela cópia `name` do Drive. O app tem de estar parado.

    O banco atual (com `-wal`/`-shm`) vai para `pre-restore-<data>/` ao lado; nada é
    tocado se o download ou a verificação falharem.
    """
    if "/" in name or not name.endswith(".sqlite3.gz"):
        raise ValueError(f"nome de backup inválido: {name!r}")
    now = now or datetime.now()
    cfg.workdir.mkdir(parents=True, exist_ok=True)
    packed = cfg.workdir / name
    raw = cfg.workdir / name.removesuffix(".gz")
    try:
        base = ["rclone", "--config", str(cfg.rclone_config)]
        if not rclone([*base, "copyto", f"{cfg.remote}/{name}", str(packed)]):
            return Result("error", f"download de {name} falhou (nome, rede ou autorização)")
        try:
            with gzip.open(packed, "rb") as fin, raw.open("wb") as fout:
                shutil.copyfileobj(fin, fout)
            with closing(sqlite3.connect(raw)) as d:
                check = d.execute("PRAGMA integrity_check").fetchone()[0]
                labels = d.execute("SELECT count(*) FROM labeled_application").fetchone()[0]
        except (OSError, sqlite3.Error) as exc:
            return Result("error", f"{name} não é um banco válido: {exc}")
        if check != "ok":
            return Result("error", f"{name} falhou no integrity_check: {check}")

        saved = cfg.db_path.parent / f"pre-restore-{now:%Y-%m-%d_%H%M}"
        saved.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            current = Path(f"{cfg.db_path}{suffix}")
            if current.exists():
                current.replace(saved / current.name)
        shutil.move(raw, cfg.db_path)
        return Result("ok", f"{name} restaurado ({labels} rótulos); anterior em {saved}", name)
    finally:
        raw.unlink(missing_ok=True)
        packed.unlink(missing_ok=True)


def main(argv: list[str]) -> int:  # pragma: no cover - laço do container
    cfg = Config.from_env()
    if argv[:1] == ["--restore"] and len(argv) == 2:
        result = restore(cfg, argv[1])
        print(f"restore {result.status}: {result.message}", flush=True)
        return 0 if result.status == "ok" else 1
    if "--now" in argv:
        result = run_once(cfg)
        print(f"backup {result.status}: {result.message}", flush=True)
        return 0 if result.status == "ok" else 1
    print(
        f"backup service up (db={cfg.db_path} remote={cfg.remote} hour={cfg.hour} "
        f"retention={cfg.retention} tz={os.environ.get('TZ', 'UTC')})",
        flush=True,
    )
    while True:
        now = datetime.now()
        if is_due(now, cfg.hour, read_marker(cfg.marker)):
            result = run_once(cfg, now=now)
            print(f"{now:%Y-%m-%d %H:%M} backup {result.status}: {result.message}", flush=True)
        time.sleep(TICK_S)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
