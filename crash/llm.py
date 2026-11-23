"""LLM backends. Both conditions of the evaluation use the SAME backend, model and settings.

openai    : any OpenAI-compatible chat endpoint (default: Groq free tier). Env: LLM_API_KEY (or GROQ_API_KEY),
            LLM_BASE_URL (default https://api.groq.com/openai/v1), CRASH_MODEL (default openai/gpt-oss-120b).
            Also works for Google Gemini, xAI Grok, OpenRouter, Ollama etc. by changing the three variables.
manual    : legacy offline replay (no network): a prompt is looked up in eval/manual/responses/<sha>.txt; if missing it is written to
            pending/<sha>.json and PendingResponse is raised. Kept only for the historical Claude-session answers; not the documented path.
"""
import hashlib, json, os, time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PendingResponse(Exception):
    pass


def key(system, user, tag):
    return hashlib.sha1(json.dumps([tag, system, user]).encode()).hexdigest()[:16]


DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class _TokenThrottle:
    """Keeps the request inside a tokens-per-minute budget (Groq free tier: 8000 TPM for gpt-oss-120b).
    Reserves prompt-estimate + max_tokens per request, as the provider does, and sleeps until the 60 s window has room."""

    def __init__(self, tpm):
        self.tpm, self.log = tpm, deque()

    def wait(self, need):
        need = min(need, self.tpm)
        while True:
            now = time.time()
            while self.log and now - self.log[0][0] > 61:
                self.log.popleft()
            used = sum(n for _, n in self.log)
            if used + need <= self.tpm or not self.log:
                self.log.append((now, need)); return
            time.sleep(max(1.0, 61 - (now - self.log[0][0])))


def _api_key():
    return os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY")


class OpenAICompatBackend:
    name = "openai"

    def __init__(self):
        from openai import OpenAI
        k = _api_key()
        if not k:
            raise RuntimeError("Set LLM_API_KEY (free Groq key: https://console.groq.com/keys) or use --backend manual")
        self.client = OpenAI(api_key=k, base_url=os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL), max_retries=5)
        self.model = os.environ.get("CRASH_MODEL", DEFAULT_MODEL)
        self.temperature = float(os.environ.get("CRASH_TEMPERATURE", "0"))
        self.max_tokens = int(os.environ.get("CRASH_MAX_TOKENS", "1200"))
        self.effort = os.environ.get("CRASH_REASONING_EFFORT", "low")      # only sent for gpt-oss models
        self.throttle = _TokenThrottle(int(os.environ.get("CRASH_TPM", "7000")))
        self.fallback = os.environ.get("CRASH_FALLBACK_MODEL", "")   # optional, e.g. openai/gpt-oss-20b, used only when the daily quota is gone
        self.used_fallback = False

    def complete(self, system, user, tag="x"):
        self.throttle.wait((len(system) + len(user)) // 3 + self.max_tokens)
        try:
            return self._call(self.model, system, user)
        except Exception as e:
            from openai import RateLimitError
            if self.fallback and isinstance(e, RateLimitError) and "per day" in str(e):
                if not self.used_fallback:
                    print(f"[llm] daily token quota of {self.model} used up, switching to {self.fallback}", flush=True)
                self.used_fallback = True
                return self._call(self.fallback, system, user)
            raise

    def _call(self, model, system, user):
        extra = {"reasoning_effort": self.effort} if "gpt-oss" in model else {}
        r = self.client.chat.completions.create(
            model=model, max_tokens=self.max_tokens, temperature=self.temperature, extra_body=extra,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content or ""


class ManualBackend:
    name = "manual"

    def __init__(self, workdir=None):
        self.dir = Path(workdir or ROOT / "eval" / "manual")
        (self.dir / "pending").mkdir(parents=True, exist_ok=True)
        (self.dir / "responses").mkdir(parents=True, exist_ok=True)

    def complete(self, system, user, tag="x"):
        k = key(system, user, tag)
        resp = self.dir / "responses" / f"{k}.txt"
        if resp.exists():
            return resp.read_text()
        (self.dir / "pending" / f"{k}.json").write_text(json.dumps(
            {"id": k, "tag": tag, "system": system, "user": user}, indent=1))
        raise PendingResponse(k)


def get_backend(name=None):
    """Default: the OpenAI-compatible (Groq) API when LLM_API_KEY / GROQ_API_KEY is set, else the legacy offline replay."""
    if name is None:
        name = "openai" if _api_key() else "manual"
    return {"openai": OpenAICompatBackend, "manual": ManualBackend}[name]()
