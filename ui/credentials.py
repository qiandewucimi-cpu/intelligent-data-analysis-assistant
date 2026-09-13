from __future__ import annotations

import os

import streamlit as st


def get_config_value(key: str, default: str = "") -> str:
    """Reads Streamlit secrets when available, otherwise falls back to env vars."""

    try:
        value = st.secrets.get(key)
    except Exception:
        value = ""

    if value in (None, ""):
        return os.getenv(key, default)
    return str(value)


def _provider_env_keys(provider: str) -> tuple:
    return {
        "zhipu": ("ZHIPU_API_KEY", "ZHIPU_MODEL", "ZHIPU_BASE_URL"),
        "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL"),
        "dashscope": ("DASHSCOPE_API_KEY", "QWEN_MODEL", "DASHSCOPE_BASE_URL"),
        "openai_compatible": ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"),
    }.get(provider, ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"))


def _env_file_path() -> str:
    # .env lives next to the app entry point (project root), not inside ui/.
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _update_env(updates: dict, remove_keys=()) -> None:
    """Upserts/removes keys in the local .env, preserving other lines."""
    path = _env_file_path()
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    remove = set(remove_keys)
    done = set()
    out = []
    for ln in lines:
        stripped = ln.lstrip()
        name = None
        if "=" in stripped and not stripped.startswith("#"):
            cand = stripped.split("=", 1)[0].strip()
            if cand and (cand[0].isalpha() or cand[0] == "_") and all(c.isalnum() or c == "_" for c in cand):
                name = cand
        if name and name in remove:
            continue
        if name and name in updates:
            out.append(name + "=" + str(updates[name]))
            done.add(name)
        else:
            out.append(ln)
    for k, v in updates.items():
        if k not in done:
            out.append(k + "=" + str(v))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).strip("\n") + "\n")

    # 同步内存中的环境变量，避免改了 .env 文件但进程里仍是旧值，
    # 导致刷新后被删的密钥/勾选状态又被读回来。
    for k, v in updates.items():
        os.environ[k] = str(v)
    for k in remove:
        os.environ.pop(k, None)


def save_credentials(provider: str, api_key: str, model_name: str, base_url: str) -> None:
    k_api, k_model, k_url = _provider_env_keys(provider)
    updates = {"LLM_PROVIDER": provider, "LLM_REMEMBER": "1", k_api: api_key}
    if model_name:
        updates[k_model] = model_name
    if base_url:
        updates[k_url] = base_url
    _update_env(updates)


def forget_credentials(provider: str) -> None:
    k_api, _, _ = _provider_env_keys(provider)
    _update_env({}, remove_keys=(k_api, "LLM_REMEMBER"))
