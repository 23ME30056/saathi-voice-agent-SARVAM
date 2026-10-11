"""Thin async wrapper around Sarvam's speech-to-text, chat and text-to-speech APIs,
plus a local credit meter so the ₹100 budget doesn't vanish by accident."""
import json
import os
import re
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
API_KEY = (os.getenv("SARVAM") or os.getenv("SARVAM_API_KEY") or "").strip()
BASE_URL = "https://api.sarvam.ai"

STT_MODEL = "saaras:v3"
LLM_MODEL = "sarvam-105b"
TTS_MODEL = "bulbul:v3"

# ₹ prices from docs.sarvam.ai/api/getting-started/pricing (Oct 2026)
PRICE_STT_PER_SEC = 30 / 3600
PRICE_TTS_PER_CHAR = 30 / 10_000
PRICE_LLM_IN = 15 / 1_000_000
PRICE_LLM_OUT = 60 / 1_000_000

TTS_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}

# Unicode block -> TTS language, so a reply is voiced in whatever script the LLM wrote it in
SCRIPT_LANGS = [
    (0x0900, 0x097F, "hi-IN"),  # Devanagari (Marathi too, resolved via the STT hint)
    (0x0980, 0x09FF, "bn-IN"),
    (0x0A00, 0x0A7F, "pa-IN"),
    (0x0A80, 0x0AFF, "gu-IN"),
    (0x0B00, 0x0B7F, "od-IN"),
    (0x0B80, 0x0BFF, "ta-IN"),
    (0x0C00, 0x0C7F, "te-IN"),
    (0x0C80, 0x0CFF, "kn-IN"),
    (0x0D00, 0x0D7F, "ml-IN"),
]

AUDIO_EXT = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav"}


class SarvamError(Exception):
    pass


class BudgetExceeded(SarvamError):
    pass


class Meter:
    """Estimated spend, persisted to usage.json. The real balance lives on dashboard.sarvam.ai."""

    def __init__(self, path: Path, budget: float):
        self.path, self.budget = path, budget
        self.data = {"spent_inr": 0.0, "stt_seconds": 0.0, "tts_chars": 0, "llm_in_tokens": 0, "llm_out_tokens": 0}
        if path.exists():
            self.data.update(json.loads(path.read_text()))

    @property
    def spent(self) -> float:
        return self.data["spent_inr"]

    def guard(self):
        if self.spent >= self.budget:
            raise BudgetExceeded(
                f"Local budget of ₹{self.budget:g} reached (est. ₹{self.spent:.2f} spent). "
                "Raise BUDGET_INR in persona.py to keep going."
            )

    def add(self, cost: float, **counts):
        self.data["spent_inr"] += cost
        for k, v in counts.items():
            self.data[k] += v
        self.path.write_text(json.dumps(self.data, indent=2))


class Sarvam:
    def __init__(self, meter: Meter):
        if not API_KEY:
            raise SystemExit("No Sarvam key found: put SARVAM=<your key> in .env")
        self.meter = meter
        self.http = httpx.AsyncClient(base_url=BASE_URL, timeout=60, headers={"api-subscription-key": API_KEY})

    async def _post(self, path: str, **kwargs) -> dict:
        self.meter.guard()
        r = await self.http.post(path, **kwargs)
        if r.status_code >= 400:
            try:
                body = r.json()
                err = body.get("error")
                msg = err.get("message") if isinstance(err, dict) else (err or body.get("detail") or r.text)
            except ValueError:
                msg = r.text
            raise SarvamError(f"Sarvam {path} failed ({r.status_code}): {msg}")
        return r.json()

    async def transcribe(self, audio: bytes, mime: str, seconds: float, mode: str) -> tuple[str, str | None]:
        """Speech -> (transcript, detected language code). Language is auto-detected."""
        data = await self._post(
            "/speech-to-text",
            files={"file": ("speech" + AUDIO_EXT.get(mime, ".webm"), audio, mime)},
            data={"model": STT_MODEL, "mode": mode, "language_code": "unknown"},
        )
        self.meter.add(seconds * PRICE_STT_PER_SEC, stt_seconds=seconds)
        return (data.get("transcript") or "").strip(), data.get("language_code")

    async def chat(self, messages: list[dict], max_tokens: int, temperature: float = 0.7) -> str:
        data = await self._post(
            "/v1/chat/completions",
            # reasoning_effort=None turns thinking off: much lower latency, which a voice call needs
            json={"model": LLM_MODEL, "messages": messages, "max_tokens": max_tokens,
                  "temperature": temperature, "reasoning_effort": None},
        )
        usage = data.get("usage") or {}
        tin, tout = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        self.meter.add(tin * PRICE_LLM_IN + tout * PRICE_LLM_OUT, llm_in_tokens=tin, llm_out_tokens=tout)
        text = data["choices"][0]["message"].get("content") or ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()

    async def speak(self, text: str, lang: str, speaker: str, pace: float) -> str:
        """Text -> base64 MP3."""
        data = await self._post(
            "/text-to-speech",
            json={"text": text, "language_code": lang, "model": TTS_MODEL, "speaker": speaker,
                  "pace": pace, "output_audio_codec": "mp3", "speech_sample_rate": 22050},
        )
        self.meter.add(len(text) * PRICE_TTS_PER_CHAR, tts_chars=len(text))
        return data["audios"][0]


def tts_language(text: str, hint: str | None) -> str:
    """Pick the TTS language from the reply's script, using the STT-detected language as a tiebreaker."""
    counts = Counter()
    for ch in text:
        o = ord(ch)
        for lo, hi, lang in SCRIPT_LANGS:
            if lo <= o <= hi:
                counts[lang] += 1
                break
    if not counts:  # Latin script: English, or romanised Hinglish
        return hint if hint in ("hi-IN", "en-IN") else "en-IN"
    lang = counts.most_common(1)[0][0]
    if lang == "hi-IN" and hint == "mr-IN":
        return "mr-IN"
    return lang


def sentence_chunks(text: str, max_chars: int = 100) -> list[str]:
    """Split into sentence groups so TTS can run in parallel (Bulbul latency grows with length)."""
    chunks, cur = [], ""
    for part in re.split(r"(?<=[.!?।])\s+", text):
        if cur and len(cur) + 1 + len(part) > max_chars:
            chunks.append(cur)
            cur = part
        else:
            cur = f"{cur} {part}".strip()
    return chunks + [cur] if cur else chunks


def speakable(text: str, limit: int) -> str:
    """Strip markdown leftovers and cap length (TTS is billed per character)."""
    t = re.sub(r"[*_`#>\[\]]", "", text)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    end = max(cut.rfind(p) for p in ".!?।")
    return cut[: end + 1] if end > limit // 2 else cut
