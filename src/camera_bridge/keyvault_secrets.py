"""Resolve `@keyvault:<secret-name>` references to real values via Microsoft
Entra ID (managed identity), so credentials never have to be stored in
plaintext in cameras.json / users.json / blob-synced config.

Only active when CONFIG_KEYVAULT_URL is set; a field value that isn't in the
`@keyvault:` form is returned unchanged (so plain local values still work for
local/dev use without a vault configured).
"""

from __future__ import annotations

import os

_VAULT_URL = os.environ.get("CONFIG_KEYVAULT_URL", "")
_PREFIX = "@keyvault:"

_client_cache = None


def enabled() -> bool:
    return bool(_VAULT_URL)


def _client():
    global _client_cache
    if _client_cache is not None:
        return _client_cache
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    _client_cache = SecretClient(vault_url=_VAULT_URL, credential=DefaultAzureCredential())
    return _client_cache


def resolve(value: str) -> str:
    """If value is "@keyvault:<secret-name>", fetch that secret's current
    value from Key Vault; otherwise return value unchanged."""
    if not value or not value.startswith(_PREFIX):
        return value
    if not enabled():
        raise RuntimeError(
            f"Config references {value!r} but CONFIG_KEYVAULT_URL is not set"
        )
    secret_name = value[len(_PREFIX):]
    try:
        return _client().get_secret(secret_name).value or ""
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Failed to resolve Key Vault secret {secret_name!r}: {exc}"
        ) from exc
