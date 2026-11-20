"""Backup do SQLite para o Google Drive (SPEC §9, B-01..B-11)."""

import gzip
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from planlabel import backup
from planlabel.repository import Repository

NOW = datetime(2026, 11, 20, 2, 5)


class FakeRclone:
    """Grava as chamadas e copia o arquivo enviado para inspeção."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.uploaded: dict[str, bytes] = {}
        self.fail_on = fail_on

    def __call__(self, args: list[str]) -> bool:
        self.calls.append(args)
        verb = args[3]
        if verb == self.fail_on:
            return False
        if verb == "copyto":
            src, dest = args[4], args[5]
            if src in self.uploaded:  # download (restauração)
                Path(dest).write_bytes(self.uploaded[src])
            elif ":" in dest:
                self.uploaded[dest] = Path(src).read_bytes()
            else:
                return False  # arquivo inexistente no Drive
        return True


def _db_with_rows(path: Path, n: int) -> sqlite3.Connection:
    Repository(path)  # cria o schema em modo WAL, como o app
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS extra (v INTEGER)")
    conn.executemany("INSERT INTO extra VALUES (?)", [(i,) for i in range(n)])
    conn.commit()
    # conexão aberta de propósito: as linhas ainda estão no -wal, não no arquivo principal
    return conn


@pytest.fixture
def env(tmp_path):
    conf = tmp_path / "rclone.conf"
    conf.write_text("[gdrive]\ntype = drive\n")
    cfg = backup.Config(
        db_path=tmp_path / "data" / "labels.sqlite3",
        remote="gdrive:planlabel-test-backups",
        retention="60d",
        hour=2,
        rclone_config=conf,
        marker=tmp_path / "data" / "backup-last-ok",
        workdir=tmp_path / "work",
    )
    return cfg


def _restore(blob: bytes, tmp_path: Path) -> sqlite3.Connection:
    out = tmp_path / "restored.sqlite3"
    out.write_bytes(gzip.decompress(blob))
    return sqlite3.connect(out)


def test_B01_snapshot_consistente_inclui_dados_do_wal(env, tmp_path):
    env.db_path.parent.mkdir(parents=True)
    keep = _db_with_rows(env.db_path, 50)
    rclone = FakeRclone()
    result = backup.run_once(env, rclone, now=NOW)
    keep.close()
    assert result.status == "ok"
    (blob,) = rclone.uploaded.values()
    conn = _restore(blob, tmp_path)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT count(*) FROM extra").fetchone()[0] == 50
    assert conn.execute("SELECT count(*) FROM labeled_application").fetchone()[0] == 0


def test_B02_nome_do_arquivo_e_gzip(env):
    env.db_path.parent.mkdir(parents=True)
    Repository(env.db_path)
    rclone = FakeRclone()
    result = backup.run_once(env, rclone, now=NOW)
    assert result.file == "planlabel_2026-11-20_0205.sqlite3.gz"
    (dest,) = rclone.uploaded
    assert dest == "gdrive:planlabel-test-backups/planlabel_2026-11-20_0205.sqlite3.gz"
    assert rclone.uploaded[dest][:2] == b"\x1f\x8b"


def test_B03_envia_depois_poda_e_limpa_temporario(env):
    env.db_path.parent.mkdir(parents=True)
    Repository(env.db_path)
    rclone = FakeRclone()
    backup.run_once(env, rclone, now=NOW)
    conf = str(env.rclone_config)
    assert [c[:4] for c in rclone.calls] == [
        ["rclone", "--config", conf, "copyto"],
        ["rclone", "--config", conf, "delete"],
    ]
    assert rclone.calls[1][4:] == ["--min-age", "60d", "gdrive:planlabel-test-backups"]
    assert list(env.workdir.iterdir()) == []


def test_B04_sem_banco_nao_faz_nada(env):
    rclone = FakeRclone()
    result = backup.run_once(env, rclone, now=NOW)
    assert result.status == "skip"
    assert rclone.calls == []
    assert not env.marker.exists()


def test_B05_sem_rclone_conf_espera(env):
    env.db_path.parent.mkdir(parents=True)
    Repository(env.db_path)
    env.rclone_config.unlink()
    rclone = FakeRclone()
    result = backup.run_once(env, rclone, now=NOW)
    assert result.status == "waiting"
    assert rclone.calls == []


def test_B06_falha_no_envio_e_erro_e_falha_na_poda_nao(env):
    env.db_path.parent.mkdir(parents=True)
    Repository(env.db_path)
    failed = backup.run_once(env, FakeRclone(fail_on="copyto"), now=NOW)
    assert failed.status == "error"
    assert not env.marker.exists()
    assert list(env.workdir.iterdir()) == []
    ok = backup.run_once(env, FakeRclone(fail_on="delete"), now=NOW)
    assert ok.status == "ok"


def test_B07_agenda_so_na_hora_e_uma_vez_por_dia():
    last = NOW - timedelta(hours=24)
    assert backup.is_due(NOW, hour=2, last_ok=last)
    assert not backup.is_due(NOW.replace(hour=3), hour=2, last_ok=last)
    assert not backup.is_due(NOW, hour=2, last_ok=NOW - timedelta(minutes=30))
    # 2 h de folga: ontem às 02:55 não impede hoje às 02:05
    assert backup.is_due(NOW, hour=2, last_ok=NOW - timedelta(hours=23, minutes=10))
    assert backup.is_due(NOW, hour=2, last_ok=None)


def test_B08_marca_o_ultimo_sucesso(env):
    env.db_path.parent.mkdir(parents=True)
    Repository(env.db_path)
    assert backup.read_marker(env.marker) is None
    backup.run_once(env, FakeRclone(), now=NOW)
    assert backup.read_marker(env.marker) == NOW


def test_B09_banco_invalido_nao_e_enviado(env):
    env.db_path.parent.mkdir(parents=True)
    env.db_path.write_bytes(b"isto nao e sqlite" * 100)
    rclone = FakeRclone()
    result = backup.run_once(env, rclone, now=NOW)
    assert result.status == "error"
    assert rclone.calls == []
    assert list(env.workdir.iterdir()) == []


def test_B10_config_do_ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANLABEL_DB_PATH", str(tmp_path / "x.sqlite3"))
    monkeypatch.setenv("BACKUP_REMOTE", "gdrive:outra")
    monkeypatch.setenv("BACKUP_HOUR", "4")
    monkeypatch.delenv("BACKUP_RETENTION", raising=False)
    cfg = backup.Config.from_env()
    assert cfg.db_path == tmp_path / "x.sqlite3"
    assert cfg.remote == "gdrive:outra"
    assert cfg.hour == 4
    assert cfg.retention == "60d"
    assert cfg.marker == tmp_path / "backup-last-ok"


def test_B11_restaura_e_guarda_o_banco_anterior(env, tmp_path):
    env.db_path.parent.mkdir(parents=True)
    keep = _db_with_rows(env.db_path, 7)
    keep.close()
    rclone = FakeRclone()
    name = backup.run_once(env, rclone, now=NOW).file
    # o banco atual muda depois do backup (inclusive com -wal pendente)
    later = _db_with_rows(env.db_path, 3)
    later.close()

    restore_at = NOW + timedelta(days=1)
    result = backup.restore(env, name, rclone, now=restore_at)

    assert result.status == "ok"
    conn = sqlite3.connect(env.db_path)
    assert conn.execute("SELECT count(*) FROM extra").fetchone()[0] == 7
    saved = env.db_path.parent / "pre-restore-2026-11-21_0205"
    old = sqlite3.connect(saved / "labels.sqlite3")
    assert old.execute("SELECT count(*) FROM extra").fetchone()[0] == 10
    assert list(env.workdir.iterdir()) == []


def test_B11_restauracao_falha_nao_mexe_no_banco(env):
    env.db_path.parent.mkdir(parents=True)
    Repository(env.db_path)
    before = env.db_path.read_bytes()
    result = backup.restore(env, "planlabel_nao_existe.sqlite3.gz", FakeRclone(), now=NOW)
    assert result.status == "error"
    assert env.db_path.read_bytes() == before
    assert not any(p.name.startswith("pre-restore") for p in env.db_path.parent.iterdir())
    with pytest.raises(ValueError):
        backup.restore(env, "../fora.gz", FakeRclone(), now=NOW)
