"""Saathi voice agent server.
Browser mic -> Sarvam STT (saaras:v3) -> sarvam-105b -> Bulbul TTS -> browser speaker.
Run:  python app.py   then open http://127.0.0.1:8000"""
import asyncio
import json
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import persona
from sarvam import (HERE, TTS_LANGS, BudgetExceeded, Meter, Sarvam, SarvamError, sentence_chunks, speakable,
                    tts_language)

meter = Meter(HERE / "usage.json", float(os.getenv("BUDGET_INR", persona.BUDGET_INR)))
sarvam = Sarvam(meter)
app = FastAPI(title=persona.NAME)
app.mount("/samples", StaticFiles(directory=HERE / "samples"), name="samples")  # demo prescription photo

# Set ACCESS_CODE when deploying publicly so strangers can't spend your Sarvam credits
ACCESS_CODE = os.getenv("ACCESS_CODE", "").strip()


@app.middleware("http")
async def require_access_code(request: Request, call_next):
    path = request.url.path
    if ACCESS_CODE and path.startswith("/api/") and path != "/api/config" \
            and not secrets.compare_digest(request.headers.get("x-access-code", ""), ACCESS_CODE):
        return JSONResponse({"detail": "Wrong or missing access code."}, status_code=401)
    return await call_next(request)


class Profile(BaseModel):
    name: str
    call_them: str = ""
    age: str = ""
    language: str = "Hindi"
    medicines: str = ""
    notes: str = ""
    family: str = ""
    voice: str = "ritu"
    local_time: str = ""


@dataclass
class Call:
    profile: Profile
    lang_hint: str | None
    history: list[dict] = field(default_factory=list)  # starts with the hidden OPENER cue


calls: dict[str, Call] = {}


@app.exception_handler(SarvamError)
async def sarvam_error(_, e: SarvamError):
    return JSONResponse({"detail": str(e)}, status_code=402 if isinstance(e, BudgetExceeded) else 502)


def ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def get_call(session_id: str) -> Call:
    if session_id not in calls:
        raise HTTPException(404, "This call has ended or the server restarted. Start a new call.")
    return calls[session_id]


def system_prompt(p: Profile) -> str:
    fields = {k: (v or "not given") for k, v in p.model_dump().items()}
    fields["call_them"] = p.call_them or p.name
    fields["saathi_gender"] = persona.VOICES.get(p.voice, "female")
    return persona.CALL_PROMPT.format(**fields)


async def respond(call: Call, user_msg: dict, speak: bool) -> dict:
    """Get Saathi's next line and, optionally, voice it."""
    t = time.perf_counter()
    convo = (call.history + [user_msg])[-(persona.HISTORY_TURNS * 2 + 1):]
    reply = await sarvam.chat([{"role": "system", "content": system_prompt(call.profile)}, *convo],
                              persona.MAX_REPLY_TOKENS)
    call.history += [user_msg, {"role": "assistant", "content": reply}]
    timings = {"llm": ms(t)}

    out = {"reply": reply, "audio": [], "audio_mime": "audio/mpeg", "tts_lang": None, "tts_error": None}
    if speak and reply:
        t = time.perf_counter()
        spoken = speakable(reply, persona.MAX_SPOKEN_CHARS)
        lang = out["tts_lang"] = tts_language(spoken, call.lang_hint)
        # one clip per sentence group, synthesised in parallel and played back in order
        clips = await asyncio.gather(*(sarvam.speak(chunk, lang, call.profile.voice, persona.PACE)
                                       for chunk in sentence_chunks(spoken)), return_exceptions=True)
        out["audio"] = [c for c in clips if isinstance(c, str)]
        errors = [c for c in clips if isinstance(c, BaseException)]
        if errors:  # keep the text reply even if the voice fails
            out["tts_error"] = str(errors[0])
        timings["tts"] = ms(t)
    return {**out, "ms": timings, "spent": round(meter.spent, 4)}


@app.get("/")
async def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/api/config")
async def config():
    return {"name": persona.NAME, "tagline": persona.TAGLINE, "profile": persona.DEFAULT_PROFILE,
            "languages": list(persona.LANGUAGES),
            "voices": [{"id": v, "gender": g} for v, g in persona.VOICES.items()],
            "budget": meter.budget, "spent": round(meter.spent, 4), "locked": bool(ACCESS_CODE)}


@app.post("/api/call/start")
async def start_call(profile: Profile, speak: bool = True):
    session_id = uuid.uuid4().hex
    call = calls[session_id] = Call(profile, lang_hint=persona.LANGUAGES.get(profile.language))
    opener = {"role": "user", "content": persona.OPENER.format(call_them=profile.call_them or profile.name)}
    return {"session_id": session_id, **await respond(call, opener, speak)}


@app.post("/api/turn")
async def turn(session_id: str = Form(...), speak: bool = Form(True), text: str = Form(""),
               duration: float = Form(0), audio: UploadFile | None = File(None)):
    call = get_call(session_id)
    user_lang, stt_ms = None, None
    if audio is not None:
        t = time.perf_counter()
        blob = await audio.read()
        mime = (audio.content_type or "audio/webm").split(";")[0]
        # ~4 KB/s is a fair guess for browser Opus if the client didn't send a duration
        text, user_lang = await sarvam.transcribe(blob, mime, duration or len(blob) / 4000, persona.STT_MODE)
        if user_lang in TTS_LANGS:
            call.lang_hint = user_lang
        stt_ms = ms(t)
    text = text.strip()
    if not text:
        return {"user_text": "", "user_lang": user_lang, "reply": "", "spent": round(meter.spent, 4)}
    out = await respond(call, {"role": "user", "content": text}, speak)
    out["ms"]["stt"] = stt_ms
    return {"user_text": text, "user_lang": user_lang, **out}


def min_confidence(node) -> float:
    """Lowest confidence score anywhere in a Sarvam Vision annotation subtree."""
    if isinstance(node, dict):
        own = [node["confidence"]] if isinstance(node.get("confidence"), (int, float)) else []
        return min(own + [min_confidence(v) for v in node.values() if isinstance(v, (dict, list))], default=1.0)
    if isinstance(node, list):
        return min((min_confidence(v) for v in node), default=1.0)
    return 1.0


@app.post("/api/prescription")
async def prescription(file: UploadFile = File(...)):
    """Prescription photo -> Sarvam Vision extracts the medicines -> Sarvam-105B writes Saathi's medicine list."""
    blob = await file.read()
    if len(blob) > 10_000_000:
        raise HTTPException(413, "That file is too big. Please use a photo under 10 MB.")
    t = time.perf_counter()
    result, notes = await sarvam.extract(blob, file.filename or "prescription.jpg",
                                         (file.content_type or "image/jpeg").split(";")[0], persona.PRESCRIPTION_SCHEMA)
    vision_ms = ms(t)
    rows = result.get("medicines") or []
    row_notes = notes.get("medicines") or []
    meds, unsure = [], []
    for i, row in enumerate(rows):
        if isinstance(row, dict) and row.get("name"):
            meds.append(row)
            if i < len(row_notes) and min_confidence(row_notes[i]) < 0.75:
                unsure.append(row["name"])
    if not meds:
        raise HTTPException(422, "Couldn't find any medicines in that photo. Try a sharper, well-lit photo.")

    t = time.perf_counter()
    text = await sarvam.chat([{"role": "system", "content": persona.MEDS_PROMPT},
                              {"role": "user", "content": json.dumps(meds, ensure_ascii=False)}], 400, temperature=0)
    lines = [re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", line).strip() for line in text.splitlines()]
    return {"medicines": "\n".join(line for line in lines if line), "count": len(meds),
            "doctor": result.get("doctor") or "", "advice": result.get("advice") or "", "unsure": unsure,
            "ms": {"vision": vision_ms, "llm": ms(t)}, "spent": round(meter.spent, 4)}


class TranslateRequest(BaseModel):
    texts: list[str]
    target: str


@app.post("/api/translate")
async def translate(req: TranslateRequest):
    """Family report in the family's own language, via Sarvam Translate (Mayura)."""
    if req.target not in persona.LANGUAGES.values():
        raise HTTPException(400, "Unsupported language.")
    if req.target == "en-IN":
        return {"texts": req.texts, "spent": round(meter.spent, 4)}
    if len(req.texts) > 60 or sum(len(t) for t in req.texts) > 6000:
        raise HTTPException(413, "That report is too long to translate.")
    return {"texts": await sarvam.translate_many(req.texts, req.target), "spent": round(meter.spent, 4)}


@app.post("/api/insights")
async def insights(session_id: str = Form(...)):
    """Structured read of the call so far: powers the live checklist and the family report."""
    call = get_call(session_id)
    p = call.profile
    who = p.call_them or p.name
    transcript = "\n".join(f"{'Saathi' if m['role'] == 'assistant' else who}: {m['content']}" for m in call.history[1:])
    brief = (f"Elder: {p.name} (called {who}), age {p.age or 'not given'}\n"
             f"Medicine list:\n{p.medicines or 'none listed'}\n"
             f"Time of call: {p.local_time or 'not given'}\n\nTranscript:\n{transcript}")
    raw = await sarvam.chat([{"role": "system", "content": persona.INSIGHTS_PROMPT},
                             {"role": "user", "content": brief}], 900, temperature=0)
    match = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(match.group(0))
    except (AttributeError, ValueError):
        raise HTTPException(502, "Couldn't read the call insights this time. Try again.")
    return {"insights": data, "spent": round(meter.spent, 4)}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")  # hosting platforms set PORT
    print(f"\n  {persona.NAME} is live at http://127.0.0.1:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
