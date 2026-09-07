"""Tests for the simple username/password auth (hashing, user store, tokens)."""

from __future__ import annotations

from pathlib import Path

from camera_bridge.auth import TokenManager, UserStore, hash_password, verify_password


def test_hash_and_verify_password_roundtrip():
    stored = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("wrong password", stored)


def test_hash_password_uses_random_salt():
    first = hash_password("same-password")
    second = hash_password("same-password")

    assert first != second
    assert verify_password("same-password", first)
    assert verify_password("same-password", second)


def test_verify_password_rejects_malformed_stored_value():
    assert not verify_password("anything", "not-a-valid-hash")


def test_user_store_add_and_verify(tmp_path: Path):
    store = UserStore(tmp_path / "users.json")

    store.add_user("alice", "hunter2")

    assert store.verify("alice", "hunter2")
    assert not store.verify("alice", "wrong")
    assert not store.verify("bob", "hunter2")


def test_user_store_persists_across_instances(tmp_path: Path):
    path = tmp_path / "users.json"
    store1 = UserStore(path)
    store1.add_user("alice", "hunter2")

    store2 = UserStore(path)

    assert store2.verify("alice", "hunter2")
    assert store2.list_usernames() == ["alice"]


def test_user_store_remove_user(tmp_path: Path):
    store = UserStore(tmp_path / "users.json")
    store.add_user("alice", "hunter2")

    assert store.remove_user("alice") is True
    assert not store.verify("alice", "hunter2")
    assert store.remove_user("alice") is False


def test_user_store_rejects_empty_username_or_password(tmp_path: Path):
    store = UserStore(tmp_path / "users.json")

    try:
        store.add_user("", "hunter2")
        assert False, "expected ValueError"
    except ValueError:
        pass

    try:
        store.add_user("alice", "")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_token_manager_issue_and_validate():
    manager = TokenManager()

    token = manager.issue("alice")

    assert manager.validate(token) == "alice"
    assert manager.validate("not-a-real-token") is None


def test_token_manager_expiry():
    manager = TokenManager(ttl_seconds=-1)

    token = manager.issue("alice")

    assert manager.validate(token) is None


def test_token_manager_revoke():
    manager = TokenManager()
    token = manager.issue("alice")

    manager.revoke(token)

    assert manager.validate(token) is None
