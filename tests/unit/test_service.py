import threading
from unittest.mock import patch

import pytest

from planlabel.models import Label
from planlabel.repository import DuplicateError, Repository
from planlabel.service import LabelingService, NoApplicationAvailable, UnknownToken
from tests.conftest import FakeSource, fake_deciders, fake_sources, make_application

WIND = Label(category="energy", subcategory="wind")


def service(repo, sources=None, rng=None, deciders=None, **kw) -> LabelingService:
    import random

    return LabelingService(
        repo,
        sources if sources is not None else fake_sources(),
        deciders or fake_deciders(),
        rng=rng or random.Random(42),
        **kw,
    )


def test_S01_next_returns_token_and_valid_application(tmp_db):
    p = service(tmp_db).next_application()
    assert len(p.token) == 36
    assert p.application.description


def test_S02_application_already_in_db_is_discarded(tmp_db):
    src = FakeSource("abp", {1: make_application("abp", 1), 2: make_application("abp", 2)})
    first = make_application("abp", 1)
    svc = service(tmp_db, sources=[src])
    tmp_db.save(first, WIND, *svc.empty_slots())
    for _ in range(5):
        svc2 = service(tmp_db, sources=[src])
        assert svc2.next_application().application.application_number == "ABP-2"


def test_S03_invalid_record_is_skipped(tmp_db):
    src = FakeSource("abp", {1: None, 2: None, 3: make_application("abp", 3)})
    assert service(tmp_db, sources=[src]).next_application().application.source_object_id == 3


def test_S04_all_existing_or_invalid_raises(tmp_db):
    src = FakeSource("abp", dict.fromkeys(range(1, 50)))
    with pytest.raises(NoApplicationAvailable):
        service(tmp_db, sources=[src]).next_application()
    assert len(src.fetched) == LabelingService.MAX_ATTEMPTS_PER_SOURCE


def test_S05_failing_source_uses_the_others(tmp_db):
    abp, epl = fake_sources()
    abp.fail = True
    svc = service(tmp_db, sources=[abp, epl])
    for _ in range(3):
        assert svc.next_application().application.source == "eplanning"


def test_S06_all_sources_failing_raises(tmp_db):
    abp, epl = fake_sources()
    abp.fail = epl.fail = True
    with pytest.raises(NoApplicationAvailable):
        service(tmp_db, sources=[abp, epl]).next_application()


def test_S07_confirm_saves_exact_data_and_removes_pending(tmp_db):
    svc = service(tmp_db)
    p = svc.next_application()
    counts = svc.confirm(p.token, WIND)
    assert counts.total == 1
    assert tmp_db.exists(
        p.application.source, p.application.planning_authority, p.application.application_number
    )
    with pytest.raises(UnknownToken):
        svc.confirm(p.token, WIND)


def test_S08_confirm_unknown_token_saves_nothing(tmp_db):
    with pytest.raises(UnknownToken):
        service(tmp_db).confirm("nope", WIND)
    assert tmp_db.counts().total == 0


def test_S09_confirm_when_already_saved_elsewhere_raises_duplicate(tmp_db):
    svc = service(tmp_db)
    p = svc.next_application()
    tmp_db.save(p.application, WIND, *svc.empty_slots())
    with pytest.raises(DuplicateError):
        svc.confirm(p.token, WIND)


def test_S10_skip_saves_nothing_and_id_not_offered_again(tmp_db):
    src = FakeSource("abp", {i: make_application("abp", i) for i in range(1, 5)})
    svc = service(tmp_db, sources=[src])
    p = svc.next_application()
    svc.skip(p.token)
    assert tmp_db.counts().total == 0
    for _ in range(3):
        q = svc.next_application()
        assert q.application.source_object_id != p.application.source_object_id
        svc.skip(q.token)
    with pytest.raises(UnknownToken):
        svc.skip(p.token)


def test_S11_next_and_skip_never_write_labels(tmp_db):
    svc = service(tmp_db)
    with patch.object(Repository, "save", side_effect=AssertionError("escreveu")) as save:
        p = svc.next_application()
        svc.skip(p.token)
        svc.next_application()
    save.assert_not_called()


def test_S12_sources_alternate_in_fixed_order_shared_by_everyone(tmp_db):
    svc = service(tmp_db)
    served = [svc.next_application().application.source for _ in range(6)]
    assert served == ["abp", "eplanning"] * 3


def test_S12_failing_source_is_skipped_and_rotation_continues(tmp_db):
    abp, epl = fake_sources()
    svc = service(tmp_db, sources=[abp, epl])
    assert svc.next_application().application.source == "abp"
    epl.fail = True
    assert svc.next_application().application.source == "abp"
    epl.fail = False
    assert svc.next_application().application.source == "eplanning"
    assert svc.next_application().application.source == "abp"


def test_S12_source_without_new_records_is_skipped(tmp_db):
    abp = FakeSource("abp", dict.fromkeys(range(1, 30)))  # só inválidos
    epl = fake_sources()[1]
    svc = service(tmp_db, sources=[abp, epl])
    assert [svc.next_application().application.source for _ in range(3)] == ["eplanning"] * 3


def test_S12_concurrent_calls_keep_alternating(tmp_db):
    svc = service(tmp_db, sources=fake_sources(200))
    served: list[str] = []
    lock = threading.Lock()

    def worker():
        for _ in range(5):
            s = svc.next_application().application.source
            with lock:
                served.append(s)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert served.count("abp") == served.count("eplanning") == 10


def test_S13_pending_limit_discards_oldest(tmp_db):
    svc = service(tmp_db, sources=fake_sources(300), max_pending=3)
    tokens = [svc.next_application().token for _ in range(4)]
    with pytest.raises(UnknownToken):
        svc.skip(tokens[0])
    svc.skip(tokens[3])
