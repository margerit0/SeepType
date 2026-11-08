"""Minimal configurable Chat Completions client; credentials never enter artifacts."""
from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tools.lexicon_expand.common import Invalid, canonical, clean_text, read_json, require


class ProviderFailure(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        # Never forward an authorization header to a redirected origin/path.
        return None


def load_config(path):
    config = read_json(path)
    allowed = {"base_url", "model", "api_key_env", "response_format", "token_parameter",
               "max_output_tokens", "timeout_seconds", "temperature", "reasoning_effort"}
    require(isinstance(config, dict) and set(config).issubset(allowed),
            "Unknown config field; API keys belong in the configured environment variable")
    for field in ("base_url", "model"):
        clean_text(config.get(field), field, 1024 if field == "base_url" else 160)
    parts = urlsplit(config["base_url"])
    require(parts.scheme == "https" and parts.hostname and not parts.username and not parts.password
            and not parts.query and not parts.fragment, "Use an HTTPS base URL without credentials or query parameters")
    require(not parts.hostname.endswith(".example") and config["model"] != "YOUR_MODEL_NAME",
            "Replace the example endpoint and model before using this configuration")
    path_part = parts.path.rstrip("/")
    if not path_part:
        path_part = "/v1"
    if not path_part.endswith("/chat/completions"):
        path_part += "/chat/completions"
    result = {"endpoint": urlunsplit((parts.scheme, parts.netloc, path_part, "", "")),
              "model": config["model"], "api_key_env": config.get("api_key_env", "STUDYIME_LEXICON_API_KEY"),
              "response_format": config.get("response_format", "json_object"),
              "token_parameter": config.get("token_parameter", "max_tokens"),
              "max_output_tokens": config.get("max_output_tokens", 4096),
              "timeout_seconds": config.get("timeout_seconds", 90),
              "temperature": config.get("temperature", 0.1)}
    require(re.fullmatch(r"STUDYIME_[A-Z0-9_]+", result["api_key_env"]) is not None,
            "Use a task-specific STUDYIME_ environment variable")
    require(result["response_format"] in ("json_object", "none"), "Unsupported response_format")
    require(result["token_parameter"] in ("max_tokens", "max_completion_tokens"), "Unknown token parameter")
    require(type(result["max_output_tokens"]) is int and 256 <= result["max_output_tokens"] <= 32768,
            "max_output_tokens must be between 256 and 32768")
    require(type(result["timeout_seconds"]) is int and 5 <= result["timeout_seconds"] <= 300,
            "timeout_seconds must be between 5 and 300")
    temperature = result["temperature"]
    require(temperature is None or (type(temperature) in (int, float) and 0 <= temperature <= 2),
            "temperature must be null or between 0 and 2")
    if config.get("reasoning_effort") is not None:
        require(config["reasoning_effort"] in ("low", "medium", "high"), "Unsupported reasoning_effort")
        # Omit absent settings so existing run identities stay unchanged.
        result["reasoning_effort"] = config["reasoning_effort"]
    return result


def read_key(variable):
    key = os.environ.get(variable)
    # A user-level variable set after Codex started is not inherited by its shell.
    if not key and os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
                value, value_type = winreg.QueryValueEx(handle, variable)
                if value_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                    key = value
        except FileNotFoundError:
            pass
    require(isinstance(key, str) and bool(key.strip()), "API key is not configured in the selected environment variable")
    key = key.strip()
    require(len(key) <= 8192 and all(32 < ord(char) < 127 for char in key), "Invalid API key format")
    return key


def request_body(config, job):
    body = {"model": config["model"], "messages": job["messages"], "stream": False,
            config["token_parameter"]: config["max_output_tokens"]}
    if config["temperature"] is not None:
        body["temperature"] = config["temperature"]
    if config["response_format"] == "json_object":
        body["response_format"] = {"type": "json_object"}
    if config.get("reasoning_effort") is not None:
        body["reasoning_effort"] = config["reasoning_effort"]
    return body


def complete(config, key, job):
    request = Request(config["endpoint"], data=canonical(request_body(config, job)), method="POST",
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                               "User-Agent": "StudyIME-lexicon-expansion/0.1"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=config["timeout_seconds"]) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        require(len(raw) <= 4 * 1024 * 1024, "Provider response exceeds the size limit")
        return raw
    except HTTPError as error:
        # Keep a short JSON error message for routing/model failures. Never expose
        # HTML error pages, echoed credentials, headers or whole response bodies.
        detail = ""
        if "application/json" in error.headers.get("Content-Type", "").lower():
            try:
                payload = json.loads(error.read(16384))
                info = payload.get("error", {}) if isinstance(payload, dict) else {}
                message = info.get("message") if isinstance(info, dict) else None
                if isinstance(message, str):
                    message = message.replace(key, "[credential withheld]")
                    message = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[credential withheld]", message)
                    message = " ".join(message.split())[:600]
                    detail = ": " + message
            except (ValueError, OSError):
                pass
        raise ProviderFailure(f"Provider returned HTTP {error.code}" +
                              (detail or "; response body withheld")) from None
    except (URLError, TimeoutError, OSError):
        raise ProviderFailure("Connection failed or timed out; no automatic retry was sent") from None


def token_usage(raw):
    envelope = json.loads(raw)
    require(isinstance(envelope, dict), "Expected a provider response object")
    usage = {}
    reported_usage = envelope.get("usage") or {}
    require(isinstance(reported_usage, dict), "Invalid provider usage object")
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = reported_usage.get(field)
        if value is not None:
            require(type(value) is int and value >= 0, "Invalid provider token usage")
            usage[field] = value
    return usage


def decode_response(raw):
    envelope = json.loads(raw)
    require(isinstance(envelope, dict), "Expected a provider response object")
    choices = envelope.get("choices")
    require(isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict),
            "Expected one provider choice")
    require(choices[0].get("finish_reason") == "stop", "Provider response is incomplete or truncated")
    message = choices[0].get("message")
    require(isinstance(message, dict), "Provider did not return a message")
    content = message.get("content")
    require(isinstance(content, str), "Provider did not return text content")
    model = envelope.get("model")
    if model is not None:
        clean_text(model, "reported model", 160)
    return content, token_usage(raw), model
