"""Plain-pytest suite for the secret stores (no 1Password, no network).

The `op` CLI is faked with an injected runner so the vault-search, empty-placeholder,
shadowing, and persist behaviours are all exercised deterministically."""
from __future__ import annotations

import subprocess

import pytest
from canopy_runtime.stores import (
    CREDENTIAL_FIELD,
    EnvVarStore,
    OnePasswordStore,
    SecretNotFoundError,
    SecretStore,
    SecretStoreError,
)


class FakeOp:
    """Simulates `op read` / `op item edit` over an in-memory vault map:
    {vault: {name: value}}. Missing item/field → returncode 1 (like the real CLI)."""

    def __init__(self, vaults: dict[str, dict[str, str]]):
        self.vaults = vaults
        self.calls: list[list[str]] = []

    def __call__(self, cmd, capture_output=True, text=True):
        self.calls.append(cmd)
        args = cmd[1:]  # drop 'op'
        if args[0] == "read":
            ref = args[1]  # op://Vault/Name/field
            _, _, vault, name, field = ref.split("/")
            val = self.vaults.get(vault, {}).get(name)
            if val is None:
                return subprocess.CompletedProcess(cmd, 1, "", f"not found: {ref}")
            return subprocess.CompletedProcess(cmd, 0, val + "\n", "")
        if args[0] == "item" and args[1] == "edit":
            name = args[2]
            vault = args[args.index("--vault") + 1]
            assign = args[-1]  # credential=value
            _, _, value = assign.partition("=")
            self.vaults.setdefault(vault, {})[name] = value
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 2, "", "unexpected")


def _store(vaults, order=("Agent-Echo", "Canopy-Shared")):
    fake = FakeOp(vaults)
    return OnePasswordStore(list(order), runner=fake), fake


# --- OnePasswordStore --------------------------------------------------------
def test_resolves_from_first_vault():
    store, _ = _store({"Agent-Echo": {"canopy-pat": "PAT123"}})
    assert store.resolve("canopy-pat") == "PAT123"


def test_falls_back_to_shared_vault():
    store, fake = _store({"Canopy-Shared": {"gog-oauth-client": "CLIENTJSON"}})
    assert store.resolve("gog-oauth-client") == "CLIENTJSON"
    # It tried the agent vault first, then the shared one.
    assert fake.calls[0][2].startswith("op://Agent-Echo/")
    assert fake.calls[1][2].startswith("op://Canopy-Shared/")


def test_per_agent_shadows_shared():
    store, _ = _store(
        {
            "Agent-Echo": {"gog-oauth-client": "ECHO_OWN"},
            "Canopy-Shared": {"gog-oauth-client": "FLEET"},
        }
    )
    assert store.resolve("gog-oauth-client") == "ECHO_OWN"


def test_empty_placeholder_is_not_provisioned():
    # A scaffolded-but-empty item must NOT resolve to "" — it should fall through.
    store, _ = _store(
        {"Agent-Echo": {"gog-token": ""}, "Canopy-Shared": {"gog-token": "REAL"}}
    )
    assert store.resolve("gog-token") == "REAL"


def test_missing_everywhere_raises_secret_not_found():
    store, _ = _store({"Agent-Echo": {}})
    with pytest.raises(SecretNotFoundError):
        store.resolve("claude-oauth-token")


def test_resolve_optional_returns_none_instead_of_raising():
    store, _ = _store({"Agent-Echo": {}})
    assert store.resolve_optional("claude-oauth-token") is None


def test_persist_writes_to_agent_vault_by_default():
    store, fake = _store({"Agent-Echo": {}, "Canopy-Shared": {}})
    store.persist("claude-oauth-token", "TOKENVAL")
    # Written to the FIRST vault (agent's own), never the shared fallback.
    assert fake.vaults["Agent-Echo"]["claude-oauth-token"] == "TOKENVAL"
    assert "claude-oauth-token" not in fake.vaults["Canopy-Shared"]
    assert store.resolve("claude-oauth-token") == "TOKENVAL"


def test_persist_error_surfaces_as_store_error():
    def failing(cmd, capture_output=True, text=True):
        return subprocess.CompletedProcess(cmd, 1, "", "no write access")

    store = OnePasswordStore(["Agent-Echo"], runner=failing)
    with pytest.raises(SecretStoreError):
        store.persist("x", "y")


def test_missing_op_binary_is_store_error():
    def boom(cmd, capture_output=True, text=True):
        raise FileNotFoundError(cmd[0])

    store = OnePasswordStore(["Agent-Echo"], runner=boom)
    with pytest.raises(SecretStoreError):
        store.resolve("anything")


def test_account_flag_is_passed_through():
    store, fake = _store({"Agent-Echo": {"canopy-pat": "P"}})
    store.account = "dimagi.1password.com"
    store.resolve("canopy-pat")
    assert "--account" in fake.calls[0] and "dimagi.1password.com" in fake.calls[0]


def test_requires_at_least_one_vault():
    with pytest.raises(ValueError):
        OnePasswordStore([])


def test_uses_credential_field_reference():
    store, fake = _store({"Agent-Echo": {"canopy-pat": "P"}})
    store.resolve("canopy-pat")
    assert fake.calls[0][2] == f"op://Agent-Echo/canopy-pat/{CREDENTIAL_FIELD}"


# --- EnvVarStore -------------------------------------------------------------
def test_envvar_store_resolves_and_normalizes_name():
    store = EnvVarStore({"CANOPY_SECRET_CANOPY_PAT": "abc"})
    assert store.resolve("canopy-pat") == "abc"
    assert store.resolve_optional("missing") is None
    with pytest.raises(SecretNotFoundError):
        store.resolve("missing")


def test_envvar_store_is_read_only():
    store = EnvVarStore({})
    with pytest.raises(NotImplementedError):
        store.persist("x", "y")


# --- Protocol ----------------------------------------------------------------
def test_stores_satisfy_the_protocol():
    assert isinstance(EnvVarStore({}), SecretStore)
    assert isinstance(OnePasswordStore(["V"]), SecretStore)
