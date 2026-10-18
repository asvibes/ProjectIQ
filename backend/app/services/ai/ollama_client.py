"""Client for the local Ollama server, plus the prompt-safety helpers every AI service shares.

Responsibilities
----------------
* Send one prompt to the configured local model (``/api/chat``, non-streaming) and return its
  text, or parsed JSON for tasks that need structured output.
* Turn every expected failure into a typed :class:`OllamaError` (a ``ServiceError``, so routers
  can translate it with ``http_errors``): server not running, model not installed, timeout,
  empty / truncated / malformed response. Error messages are safe to show to a user and never
  contain prompt or document text.
* Provide the small helpers the other AI modules use before and after a model call: fencing
  untrusted text, loading versioned prompt files, and checking that figures in generated text
  come from the supplied data.

Design rules
------------
* **Local only, no new dependency.** Uses ``urllib`` from the standard library. Proxy
  environment variables are ignored and redirects are refused, so document text is only ever
  sent to the configured server. A non-local ``OLLAMA_BASE_URL`` is allowed but logged as a
  warning (docs/SECURITY_PRIVACY.md).
* **Nothing sensitive is logged.** Prompts and responses are never written to logs.
* **The model has no tools and no side effects.** This client only asks for text. Whatever
  comes back is untrusted until the calling service has validated it.
* **Deterministic by default.** Temperature 0 and a fixed seed, so evaluation runs are
  comparable (small local models still vary slightly between runs).
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings
from app.services.errors import ServiceError

__all__ = [
    "DEFAULT_NUM_CTX",
    "GenerationResult",
    "OllamaClient",
    "OllamaError",
    "OllamaModelNotFoundError",
    "OllamaResponseError",
    "OllamaTimeoutError",
    "OllamaUnavailableError",
    "PromptUnavailableError",
    "fence_untrusted",
    "fence_untrusted_json",
    "get_ollama_client",
    "is_local_url",
    "load_prompt",
    "provenance",
    "unsupported_numbers",
]

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
DEFAULT_NUM_CTX = 8192
DEFAULT_SEED = 42
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_PROMPT_CHARS = 200_000  # hard stop against accidentally sending a whole document set
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

#: ``(method, url, body, timeout)`` -> ``(http_status, response_bytes)``. Must raise
#: ``ConnectionError`` if the server cannot be reached and ``TimeoutError`` on timeout.
Transport = Callable[[str, str, Optional[bytes], float], tuple[int, bytes]]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class OllamaError(ServiceError):
    """Base class. ``status_code`` / ``message`` follow the service-layer convention."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(status_code, message)


class OllamaUnavailableError(OllamaError):
    def __init__(self, message: str = "The local AI service (Ollama) is not reachable. Start Ollama and try again.") -> None:
        super().__init__(message, 503)


class OllamaModelNotFoundError(OllamaError):
    def __init__(self, model: str) -> None:
        super().__init__(
            f"The AI model '{model}' is not installed in Ollama. Install it with: ollama pull {model}", 503
        )
        self.model = model


class OllamaTimeoutError(OllamaError):
    def __init__(self, message: str = "The local AI model took too long to respond.") -> None:
        super().__init__(message, 504)


class OllamaResponseError(OllamaError):
    """The model answered, but not with something usable (empty, truncated, not JSON, ...)."""

    def __init__(self, message: str = "The local AI model returned an unusable response.") -> None:
        super().__init__(message, 502)


class PromptUnavailableError(ServiceError):
    def __init__(self, name: str) -> None:
        super().__init__(500, f"The AI prompt '{name}' is missing or empty.")


# ---------------------------------------------------------------------------
# Transport (stdlib only)
# ---------------------------------------------------------------------------
class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        return None


def _urllib_transport(method: str, url: str, body: Optional[bytes], timeout: float) -> tuple[int, bytes]:
    # An empty ProxyHandler ignores HTTP(S)_PROXY: local model traffic must not be proxied.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _RefuseRedirects())
    request = urllib.request.Request(
        url, data=body, method=method, headers={"Content-Type": "application/json", "Accept": "application/json"}
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:  # a real HTTP answer with an error status
        try:
            return exc.code, exc.read(MAX_RESPONSE_BYTES + 1)
        finally:
            exc.close()
    except TimeoutError as exc:
        raise TimeoutError("timed out") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise TimeoutError("timed out") from exc
        raise ConnectionError("unreachable") from exc
    except OSError as exc:  # connection reset, refused, DNS failure, ...
        raise ConnectionError("unreachable") from exc


def is_local_url(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host in _LOCAL_HOSTS or host.startswith("127.")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str
    truncated: bool = False  # the model stopped because it hit the output limit


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 120.0,
        num_ctx: int = DEFAULT_NUM_CTX,
        transport: Optional[Transport] = None,
    ) -> None:
        if not base_url.lower().startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        if not model.strip():
            raise ValueError("model cannot be blank")
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._transport: Transport = transport or _urllib_transport
        if not is_local_url(self.base_url):
            logger.warning(
                "OLLAMA_BASE_URL points to a non-local host; tender and company text will leave this machine."
            )

    # -- low level ---------------------------------------------------------
    def _request(self, method: str, path: str, payload: Optional[Mapping[str, Any]] = None) -> tuple[int, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        try:
            status, raw = self._transport(method, f"{self.base_url}{path}", body, self.timeout)
        except TimeoutError as exc:
            raise OllamaTimeoutError() from exc
        except ConnectionError as exc:
            raise OllamaUnavailableError() from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise OllamaResponseError("The local AI model returned a response that is too large.")
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, ValueError):
            data = None
        return status, data

    # -- public API --------------------------------------------------------
    def list_models(self) -> list[str]:
        """Names of the models installed in Ollama (raises if the server is unreachable)."""
        status, data = self._request("GET", "/api/tags")
        if status != 200 or not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise OllamaResponseError("Ollama did not return a model list.")
        return [m["name"] for m in data["models"] if isinstance(m, dict) and isinstance(m.get("name"), str)]

    def is_available(self) -> bool:
        """True when the server is reachable and the configured model is installed."""
        try:
            names = self.list_models()
        except OllamaError:
            return False
        # Ollama lists an untagged model such as "gemma3" as "gemma3:latest".
        return self.model in names or f"{self.model}:latest" in names

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        json_output: bool = False,
        temperature: float = 0.0,
        max_output_tokens: Optional[int] = 2048,
    ) -> GenerationResult:
        """Send one prompt and return the model's text."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt cannot be empty")
        if len(prompt) + len(system or "") > MAX_PROMPT_CHARS:
            raise OllamaResponseError("The request is too large to send to the local AI model.")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        options: dict[str, Any] = {"temperature": temperature, "seed": DEFAULT_SEED, "num_ctx": self.num_ctx}
        if max_output_tokens:
            options["num_predict"] = max_output_tokens
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False, "options": options}
        if json_output:
            payload["format"] = "json"

        status, data = self._request("POST", "/api/chat", payload)
        if status == 404 and _mentions_missing_model(data):
            raise OllamaModelNotFoundError(self.model)
        if status != 200:
            raise OllamaResponseError(f"The local AI service answered with an error (HTTP {status}).")
        if not isinstance(data, dict):
            raise OllamaResponseError()
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaResponseError("The local AI model returned an empty response.")
        return GenerationResult(
            text=content.strip(),
            model=str(data.get("model") or self.model),
            truncated=data.get("done_reason") == "length",
        )

    def generate_json(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_output_tokens: Optional[int] = 2048,
    ) -> tuple[Any, GenerationResult]:
        """Like :meth:`generate` but the answer must be a JSON document. The parsed value is
        returned **unvalidated**: the caller owns schema validation."""
        result = self.generate(
            prompt, system=system, json_output=True, temperature=temperature, max_output_tokens=max_output_tokens
        )
        if result.truncated:
            raise OllamaResponseError("The local AI model's answer was cut off before it finished.")
        return _parse_json(result.text), result


def _mentions_missing_model(data: Any) -> bool:
    text = data.get("error") if isinstance(data, dict) else None
    return isinstance(text, str) and "not found" in text.lower()


_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def _parse_json(text: str) -> Any:
    candidate = text.strip()
    match = _FENCE_RE.match(candidate)
    if match:
        candidate = match.group(1)
    try:
        return json.loads(candidate)
    except ValueError as exc:
        raise OllamaResponseError("The local AI model did not return valid JSON.") from exc


def get_ollama_client() -> OllamaClient:
    """Client built from the application settings (``OLLAMA_*`` environment variables)."""
    settings = get_settings()
    return OllamaClient(
        settings.ollama_base_url, settings.ollama_model, timeout=settings.ollama_timeout_seconds
    )


# ---------------------------------------------------------------------------
# Prompt-safety helpers shared by extractor, qa, explainer and drafter
# ---------------------------------------------------------------------------
_LABEL_RE = re.compile(r"[^A-Za-z0-9 _.:\-]")


def fence_untrusted(text: str, *, label: str = "DOCUMENT EXCERPT", nonce: Optional[str] = None) -> str:
    """Wrap untrusted text in a fence carrying a random nonce that does not occur in it, so the
    text cannot forge the closing marker.

    This is a mitigation, **not** a defence by itself: a model may still read instructions
    inside the fence. The real defences are structural (no tools, validated output, quotations
    checked against the source, human review before anything is trusted).
    """
    label = _LABEL_RE.sub("", label).strip().upper() or "DATA"
    if nonce is None:
        nonce = secrets.token_hex(8)
        while nonce in text or nonce in label:
            nonce = secrets.token_hex(8)
    elif nonce in text or nonce in label:
        raise ValueError("nonce occurs in the fenced content")
    return f"<<<BEGIN UNTRUSTED {label} {nonce}>>>\n{text}\n<<<END UNTRUSTED {label} {nonce}>>>"


def fence_untrusted_json(value: Any, *, label: str = "DATA") -> str:
    """Fence a JSON rendering of ``value``. ASCII-escaped JSON keeps every newline inside a
    string escaped, so embedded text cannot start a line that looks like an instruction."""
    return fence_untrusted(json.dumps(value, ensure_ascii=True, default=str, indent=1), label=label)


_PROMPT_NAME_RE = re.compile(r"^[a-z0-9_]+_v[0-9]+$")


def load_prompt(name: str) -> str:
    """Read a versioned prompt (``prompts/<name>.txt``). ``name`` must look like
    ``extract_requirements_v1``; no path separators are accepted."""
    if not _PROMPT_NAME_RE.match(name):
        raise PromptUnavailableError(name)
    try:
        text = (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PromptUnavailableError(name) from exc
    if not text:
        raise PromptUnavailableError(name)
    return text


def provenance(prompt_name: str, model: str) -> str:
    """Value for the ``extractor`` / ``generated_by`` columns (120 characters at most)."""
    return f"{prompt_name}@{model}"[:120]


_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _number_key(token: str) -> str:
    token = token.replace(",", "").rstrip(".")
    whole, _, frac = token.partition(".")
    whole = whole.lstrip("0") or "0"
    frac = frac.rstrip("0")
    return f"{whole}.{frac}" if frac else whole


def _is_figure(token: str) -> bool:
    # Single digits are list numbers and small counts ("2 gaps"); only figures are checked.
    return len(token.replace(",", "")) >= 2 or "." in token


def unsupported_numbers(generated: str, *sources: Any) -> list[str]:
    """Figures (two or more digits, or with decimals) that appear in ``generated`` but in none of
    ``sources``. Sources may be strings or JSON-serialisable values. Used to stop a model from
    introducing numbers that the deterministic modules did not supply."""
    allowed: set[str] = set()
    for source in sources:
        text = source if isinstance(source, str) else json.dumps(source, ensure_ascii=False, default=str)
        allowed.update(_number_key(t) for t in _NUMBER_RE.findall(text))
    bad = []
    for token in _NUMBER_RE.findall(generated):
        if _is_figure(token) and _number_key(token) not in allowed and token not in bad:
            bad.append(token)
    return bad
