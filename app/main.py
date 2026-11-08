"""Nutq Studio backend. Bepul Edge neyron ovozlari (kalit shart emas) + ixtiyoriy Neuron/ElevenLabs."""
import asyncio
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path

import edge_tts
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

NEURON_KEY = os.getenv("NEURONAI_API_KEY", "").strip()
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
AISHA_KEY = os.getenv("AISHA_API_KEY", "").strip()
AISHA_BASE = "https://back.aisha.group"
AISHA_MOODS = ("Neutral", "Cheerful", "Happy", "Sad")
PAID_RATE = int(os.getenv("PAID_RATE_PER_MIN", "10"))
ELEVEN_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
MAX_CHARS = int(os.getenv("MAX_CHARS", "600"))
RATE = int(os.getenv("RATE_PER_MIN", "40"))
EDGE_LOCALES = ("uz-UZ", "ru-RU", "en-US", "en-GB")
# Oʻzbekcha uchun 2 ta asl ovoz bor (Madina, Sardor). Ulardan ohang/tezlikni oʻzgartirib qoʻshimcha ovoz uslublari yasaymiz.
# nom: (pitch Hz, tezlik %)
UZ_VARIANTS = {
    "yumshoq": (-6, -8),
    "yosh": (10, 6),
    "chuqur": (-14, -4),
    "tezkor": (0, 14),
    "hikoyachi": (-4, -14),
}

neuron = None
if NEURON_KEY:
    from naiuz import NeuronAI

    neuron = NeuronAI(api_key=NEURON_KEY, timeout=120)

app = FastAPI(title="Nutq Studio")
hits: dict = defaultdict(deque)
_cache: dict = {"t": 0, "data": None}


def rate_limit(req: Request, bucket: str = "free", limit: int = RATE) -> None:
    ip = (req.headers.get("x-forwarded-for") or req.client.host or "?").split(",")[0].strip()
    now, q = time.time(), hits[(bucket, ip)]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Juda koʻp soʻrov. Bir daqiqadan soʻng urinib koʻring.")
    q.append(now)


class TTSReq(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)
    voice_id: str = Field(max_length=80)
    provider: str = "edge"
    language: str = "uz"
    stability: float = Field(0.5, ge=0, le=1)
    speed: float = Field(1.0, ge=0.5, le=2.0)


def _paid_voices():
    out, errors = [], {}
    if neuron:
        try:
            for v in neuron.voices.list(limit=100):
                out.append({"id": v.id, "name": getattr(v, "name", None) or v.id,
                            "language": getattr(v, "language", None) or "uz",
                            "provider": "neuron", "tags": list(getattr(v, "tags", None) or [])})
        except Exception as e:  # noqa: BLE001
            errors["neuron"] = str(e)[:200]
    if AISHA_KEY:
        for mood in AISHA_MOODS:
            out.append({"id": f"Gulnoza~{mood}", "name": f"Gulnoza · {mood.lower()}", "language": "uz",
                        "provider": "aisha", "tags": ["Ayol", "Aisha AI"]})
    if ELEVEN_KEY:
        try:
            r = httpx.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": ELEVEN_KEY}, timeout=20)
            r.raise_for_status()
            for v in r.json().get("voices", []):
                out.append({"id": v["voice_id"], "name": v["name"], "language": "multi", "provider": "elevenlabs",
                            "tags": [str(x) for x in (v.get("labels") or {}).values()][:3]})
        except Exception as e:  # noqa: BLE001
            errors["elevenlabs"] = str(e)[:200]
    return out, errors


@app.get("/api/voices")
async def voices():
    if _cache["data"] and time.time() - _cache["t"] < 300:
        return _cache["data"]
    out, errors = [], {}
    try:
        for v in await edge_tts.list_voices():
            if v["Locale"] in EDGE_LOCALES:
                short = v["ShortName"]
                name = short.split("-", 2)[2].replace("Neural", "")
                tags = [v.get("Gender", ""), v["Locale"]]
                out.append({"id": short, "name": name, "language": v["Locale"][:2], "provider": "edge",
                            "tags": [t for t in tags if t]})
                if v["Locale"] == "uz-UZ":
                    for var in UZ_VARIANTS:
                        out.append({"id": f"{short}~{var}", "name": f"{name} · {var}", "language": "uz",
                                    "provider": "edge", "tags": [v.get("Gender", ""), "uslub"]})
    except Exception as e:  # noqa: BLE001
        errors["edge"] = str(e)[:200]
    paid, perr = await asyncio.to_thread(_paid_voices)
    out += paid
    errors.update(perr)
    order = {"uz": 0, "ru": 1, "en": 2, "multi": 3}
    out.sort(key=lambda v: (order.get(v["language"], 9), v["provider"] != "edge", v["name"]))
    data = {"voices": out, "providers": {"edge": True, "neuron": bool(neuron), "elevenlabs": bool(ELEVEN_KEY), "aisha": bool(AISHA_KEY)},
            "errors": errors}
    if out:
        _cache.update(t=time.time(), data=data)
    return data


async def edge_audio(text: str, voice: str, speed: float) -> bytes:
    voice, _, var = voice.partition("~")
    if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}-\w+", voice) or (var and var not in UZ_VARIANTS):
        raise HTTPException(400, "Notoʻgʻri ovoz")
    pitch, rate_adj = UZ_VARIANTS.get(var, (0, 0))
    rate = f"{max(-50, min(100, round((speed - 1) * 100) + rate_adj)):+d}%"
    buf = bytearray()
    try:
        async for ch in edge_tts.Communicate(text, voice, rate=rate, pitch=f"{pitch:+d}Hz").stream():
            if ch["type"] == "audio":
                buf += ch["data"]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Edge TTS xatosi: {str(e)[:150]}")
    if not buf:
        raise HTTPException(502, "Ovoz yaratilmadi")
    return bytes(buf)


def neuron_audio(b: TTSReq) -> bytes:
    if not neuron:
        raise HTTPException(400, "NEURONAI_API_KEY sozlanmagan")
    try:
        return neuron.tts.synthesize(text=b.text, voice_id=b.voice_id, language=b.language, quality="high").audio
    except Exception as e:  # noqa: BLE001
        raise HTTPException(int(getattr(e, "status", 502) or 502), str(getattr(e, "message", e))[:200])


def aisha_audio(b: TTSReq) -> bytes:
    if not AISHA_KEY:
        raise HTTPException(400, "AISHA_API_KEY sozlanmagan")
    mood = b.voice_id.partition("~")[2]
    if mood not in AISHA_MOODS:
        raise HTTPException(400, "Notoʻgʻri ovoz")
    speed = 0 if abs(b.speed - 1) < 0.01 else min(2.0, max(0.5, b.speed))
    h = {"X-Api-Key": AISHA_KEY}
    try:
        r = httpx.post(f"{AISHA_BASE}/api/v1/tts/post/", headers=h, timeout=120,
                       data={"transcript": b.text, "language": "uz", "model": "Gulnoza", "mood": mood,
                             "speed": str(speed)})
        if r.status_code == 402:
            raise HTTPException(402, "Aisha balansi tugagan")
        if r.status_code != 201:
            raise HTTPException(502, f"Aisha xatosi ({r.status_code})")
        path = r.json()["audio_path"]
        a = httpx.get(AISHA_BASE + (path if path.startswith("/") else "/" + path), headers=h, timeout=60)
        a.raise_for_status()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Aisha ulanish xatosi: {str(e)[:120]}")
    return a.content


def eleven_audio(b: TTSReq) -> bytes:
    if not ELEVEN_KEY:
        raise HTTPException(400, "ELEVENLABS_API_KEY sozlanmagan")
    r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{b.voice_id}",
                   params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": ELEVEN_KEY},
                   json={"text": b.text, "model_id": ELEVEN_MODEL,
                         "voice_settings": {"stability": b.stability, "similarity_boost": 0.8}}, timeout=120)
    if r.status_code != 200:
        raise HTTPException(502, f"ElevenLabs xatosi ({r.status_code})")
    return r.content


@app.post("/api/tts")
async def tts(body: TTSReq, request: Request):
    rate_limit(request)
    if body.provider != "edge":
        rate_limit(request, "paid", PAID_RATE)  # pullik provayderlar uchun qattiqroq limit
    if body.provider == "edge":
        return Response(await edge_audio(body.text, body.voice_id, body.speed), media_type="audio/mpeg")
    if body.provider == "aisha":
        return Response(await asyncio.to_thread(aisha_audio, body), media_type="audio/wav")
    if body.provider == "neuron":
        return Response(await asyncio.to_thread(neuron_audio, body), media_type="audio/wav")
    if body.provider == "elevenlabs":
        return Response(await asyncio.to_thread(eleven_audio, body), media_type="audio/mpeg")
    raise HTTPException(400, "Nomaʼlum provayder")


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
