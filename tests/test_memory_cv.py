"""
Pytest tests for MemoryCV — in-memory CV store (no DB required).
Run with:  python -m pytest tests/ -v
"""

from datetime import datetime

import pytest

from backend.db.database import MemoryCV


# ── Fixture ───────────────────────────────────────────────────────────────────
@pytest.fixture
def store() -> MemoryCV:
    """Return a fresh empty MemoryCV before each test."""
    return MemoryCV()


@pytest.fixture
def store_with_two(store: MemoryCV) -> MemoryCV:
    """Return a store pre-populated with two records."""
    store.add(job_title="Python Developer", full_name="Ivan")
    store.add(job_title="Backend Engineer", full_name="Maria")
    return store


# ── add() ─────────────────────────────────────────────────────────────────────
def test_add_returns_dict(store):
    record = store.add(job_title="Python Developer", full_name="Ivan")
    assert isinstance(record, dict)


def test_add_assigns_auto_id(store):
    r1 = store.add(job_title="Dev A")
    r2 = store.add(job_title="Dev B")
    assert r1["id"] == 1
    assert r2["id"] == 2


def test_add_stores_provided_fields(store):
    store.add(job_title="Python Developer", full_name="Ivan", email="ivan@example.com")
    record = store.get(record_id=1)
    assert record["job_title"] == "Python Developer"
    assert record["full_name"] == "Ivan"
    assert record["email"] == "ivan@example.com"


def test_add_missing_fields_are_none(store):
    store.add(job_title="Python Developer")
    record = store.get(1)
    assert record["full_name"] is None
    assert record["email"] is None
    assert record["phone"] is None


def test_add_sets_created_at_timestamp(store):
    store.add(job_title="Dev")
    assert isinstance(store.get(1)["created_at"], datetime)


def test_add_sets_updated_at_timestamp(store):
    store.add(job_title="Dev")
    assert isinstance(store.get(1)["updated_at"], datetime)


def test_add_multiple_records(store):
    for i in range(5):
        store.add(job_title=f"Role {i}")
    assert len(store) == 5


# ── get() ─────────────────────────────────────────────────────────────────────
def test_get_existing_record(store_with_two):
    assert store_with_two.get(1)["full_name"] == "Ivan"


def test_get_second_record(store_with_two):
    assert store_with_two.get(2)["full_name"] == "Maria"


def test_get_nonexistent_raises_key_error(store):
    with pytest.raises(KeyError):
        store.get(999)


# ── all() ─────────────────────────────────────────────────────────────────────
def test_all_empty_store(store):
    assert store.all() == []


def test_all_returns_list(store):
    store.add(job_title="Dev")
    assert isinstance(store.all(), list)


def test_all_returns_all_records(store):
    store.add(job_title="Dev A")
    store.add(job_title="Dev B")
    assert len(store.all()) == 2


def test_all_returns_copy_not_reference(store):
    """Mutating the returned list must not affect the internal store."""
    store.add(job_title="Dev")
    result = store.all()
    result.clear()
    assert len(store) == 1


# ── update() ──────────────────────────────────────────────────────────────────
def test_update_changes_field(store):
    store.add(job_title="Dev", email="old@example.com")
    store.update(1, email="new@example.com")
    assert store.get(1)["email"] == "new@example.com"


def test_update_multiple_fields_at_once(store):
    store.add(job_title="Dev", email="old@example.com")
    store.update(1, email="new@example.com", full_name="Ivan Updated")
    record = store.get(1)
    assert record["email"] == "new@example.com"
    assert record["full_name"] == "Ivan Updated"


def test_update_refreshes_updated_at(store):
    store.add(job_title="Dev")
    before = store.get(1)["updated_at"]
    store.update(1, email="new@example.com")
    after = store.get(1)["updated_at"]
    assert after >= before


def test_update_does_not_change_id(store):
    store.add(job_title="Dev")
    store.update(1, email="new@example.com")
    assert store.get(1)["id"] == 1


def test_update_ignores_unknown_fields(store):
    """Unknown keys should be silently ignored and not land in the record."""
    store.add(job_title="Dev")
    store.update(1, nonexistent_field="value")
    assert "nonexistent_field" not in store.get(1)


def test_update_nonexistent_raises_key_error(store):
    with pytest.raises(KeyError):
        store.update(999, email="x@x.com")


# ── delete() ──────────────────────────────────────────────────────────────────
def test_delete_reduces_length(store_with_two):
    store_with_two.delete(1)
    assert len(store_with_two) == 1


def test_delete_removes_correct_record(store_with_two):
    store_with_two.delete(1)
    with pytest.raises(KeyError):
        store_with_two.get(1)


def test_delete_leaves_other_records_intact(store_with_two):
    store_with_two.delete(1)
    assert store_with_two.get(2)["job_title"] == "Backend Engineer"


def test_delete_nonexistent_id_is_silent(store):
    """Deleting a non-existent id should not raise any error."""
    store.delete(999)   # must not raise


# ── clear() ───────────────────────────────────────────────────────────────────
def test_clear_empties_store(store_with_two):
    store_with_two.clear()
    assert len(store_with_two) == 0


def test_clear_resets_id_counter(store_with_two):
    store_with_two.clear()
    record = store_with_two.add(job_title="Fresh start")
    assert record["id"] == 1


# ── __len__ / __repr__ ────────────────────────────────────────────────────────
def test_len_empty(store):
    assert len(store) == 0


def test_len_after_add(store):
    store.add(job_title="Dev")
    assert len(store) == 1


def test_repr_contains_record_count(store):
    store.add(job_title="Dev", full_name="Ivan")
    assert "1 record(s)" in repr(store)


def test_repr_contains_job_title(store):
    store.add(job_title="Python Developer", full_name="Ivan")
    assert "Python Developer" in repr(store)
