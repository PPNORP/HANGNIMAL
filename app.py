import os
import json
import random
import urllib.parse
import urllib.request
from pathlib import Path
from flask import Flask, jsonify, render_template, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

START_LIFE = 8
HINT_LETTER_MAX = 2
HINT_LETTER_COST = 2

# ----------------- load words -----------------
WORDS_FILE = Path("animals.txt")
if not WORDS_FILE.exists():
    raise FileNotFoundError("animals.txt not found next to app.py")

ANIMALS = []
for line in WORDS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
    w = line.strip().lower()
    if w and w.isalpha():
        ANIMALS.append(w)

if not ANIMALS:
    raise ValueError("animals.txt is empty or has no valid a-z words.")

# ----------------- translate (prefer `translate` lib, else fallback) -----------------
TRANSLATE_CACHE: dict[str, str] = {}

try:
    from translate import Translator  # type: ignore
    HAS_TRANSLATE_LIB = True
except Exception:
    HAS_TRANSLATE_LIB = False

def translate_to_th(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    key = text.lower()
    if key in TRANSLATE_CACHE:
        return TRANSLATE_CACHE[key]

    # A) translate lib
    if HAS_TRANSLATE_LIB:
        try:
            tr = Translator(from_lang="en", to_lang="th")
            th = (tr.translate(text) or "").strip()
            if th:
                TRANSLATE_CACHE[key] = th
            return th
        except Exception:
            pass

    # B) fallback: MyMemory (no pip)
    try:
        q = urllib.parse.quote(text)
        url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en|th"
        req = urllib.request.Request(url, headers={"User-Agent": "AnimalHangman/1.0"})
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        th = ((data.get("responseData") or {}).get("translatedText") or "").strip()
        if th:
            TRANSLATE_CACHE[key] = th
        return th
    except Exception:
        return ""

# ----------------- wikipedia summary (image + short explanation) -----------------
WIKI_CACHE: dict[str, dict] = {}

def wikipedia_summary(word: str) -> dict:
    """
    Returns: { img, desc_en, extract_en }
    desc_en = short description line
    extract_en = short paragraph
    """
    word = (word or "").strip()
    if not word:
        return {"img": "", "desc_en": "", "extract_en": ""}

    key = word.lower()
    if key in WIKI_CACHE:
        return WIKI_CACHE[key]

    title = urllib.parse.quote(word)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    req = urllib.request.Request(url, headers={"User-Agent": "AnimalHangman/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))

        img = ((data.get("thumbnail") or {}).get("source") or "").strip()
        desc_en = (data.get("description") or "").strip()
        extract_en = (data.get("extract") or "").strip()

        out = {"img": img, "desc_en": desc_en, "extract_en": extract_en}
        WIKI_CACHE[key] = out
        return out
    except Exception:
        out = {"img": "", "desc_en": "", "extract_en": ""}
        WIKI_CACHE[key] = out
        return out

# ----------------- game state helpers -----------------
def mask_word(word: str, guessed: set[str]) -> str:
    return " ".join(c if c in guessed else "_" for c in word)

def pick_word() -> str:
    return random.choice(ANIMALS)

def start_round(stage: int, life: int) -> dict:
    word = pick_word()
    info = wikipedia_summary(word)

    return {
        "stage": stage,
        "life": life,
        "word": word,                 # backend only
        "img": info["img"],
        "desc_en": info["desc_en"],
        "extract_en": info["extract_en"],

        "guessed": [],
        "wrong": [],
        "hint_letters_used": 0,

        "status": "playing",          # playing | failed
        "message": f"🧩 STAGE {stage} started",

        # last revealed (after clear/fail)
        "last_en": "",
        "last_th": "",
        "last_about_en": "",
        "last_about_th": "",
    }

def public_state(st: dict) -> dict:
    guessed = set(st.get("guessed", []))
    word = st.get("word", "")
    masked = mask_word(word, guessed) if word else ""
    return {
        "stage": st.get("stage", 1),
        "life": st.get("life", START_LIFE),
        "length": len(word),
        "masked": masked,
        "wrong": st.get("wrong", []),
        "status": st.get("status", "playing"),
        "message": st.get("message", ""),

        # show immediately
        "img": st.get("img", ""),
        "hint_letters_used": st.get("hint_letters_used", 0),
        "hint_letters_max": HINT_LETTER_MAX,

        # last revealed (only changes after clear/fail)
        "last_en": st.get("last_en", ""),
        "last_th": st.get("last_th", ""),
        "last_about_en": st.get("last_about_en", ""),
        "last_about_th": st.get("last_about_th", ""),
    }

def get_state():
    return session.get("game")

def save_state(st):
    session["game"] = st

# ----------------- routes -----------------
@app.get("/")
def index():
    return render_template("index.html")

@app.get("/api/state")
def api_state():
    st = get_state()
    if not st:
        return jsonify({"status": "no_game"})
    return jsonify(public_state(st))

@app.post("/api/reset")
def api_reset():
    session.pop("game", None)
    return jsonify({"ok": True})

@app.post("/api/start")
def api_start():
    st = start_round(stage=1, life=START_LIFE)
    save_state(st)
    return jsonify(public_state(st))

@app.post("/api/guess")
def api_guess():
    st = get_state()
    if not st:
        return jsonify({"error": "no_game"}), 400
    if st["status"] != "playing":
        return jsonify(public_state(st))

    data = request.get_json(silent=True) or {}
    g = (data.get("guess") or "").lower().strip()

    if len(g) != 1 or not g.isalpha():
        st["message"] = "Enter ONE letter only (a-z)"
        save_state(st)
        return jsonify(public_state(st))

    guessed = set(st["guessed"])
    wrong = set(st["wrong"])
    word = st["word"]
    life = int(st["life"])

    if g in guessed or g in wrong:
        st["message"] = f"Already guessed: {g}"
        save_state(st)
        return jsonify(public_state(st))

    if g in word:
        guessed.add(g)
        life += 2
        st["message"] = f"✅ Correct! +2 life -> {life}"
    else:
        wrong.add(g)
        life -= 1
        st["message"] = f"❌ Wrong! -1 life -> {life}"

    st["guessed"] = sorted(list(guessed))
    st["wrong"] = sorted(list(wrong))
    st["life"] = life

    # fail
    if life <= 0:
        about_en = (st.get("desc_en") or st.get("extract_en") or "").strip()
        st["status"] = "failed"
        st["last_en"] = word
        st["last_th"] = translate_to_th(word) or "-"
        st["last_about_en"] = about_en or "-"
        st["last_about_th"] = translate_to_th(about_en) if about_en else "-"
        st["message"] = f"💀 GAME OVER! Word: {st['last_en']} | ไทย: {st['last_th']}"
        save_state(st)
        return jsonify(public_state(st))

    # clear -> next round immediately
    if all(c in guessed for c in word):
        about_en = (st.get("desc_en") or st.get("extract_en") or "").strip()

        st["last_en"] = word
        st["last_th"] = translate_to_th(word) or "-"
        st["last_about_en"] = about_en or "-"
        st["last_about_th"] = translate_to_th(about_en) if about_en else "-"

        next_stage = int(st["stage"]) + 1
        next_life = life  # carry life
        nxt = start_round(stage=next_stage, life=next_life)

        # carry last reveal info into new round
        nxt["last_en"] = st["last_en"]
        nxt["last_th"] = st["last_th"]
        nxt["last_about_en"] = st["last_about_en"]
        nxt["last_about_th"] = st["last_about_th"]
        nxt["message"] = f"🎉 CLEAR! {nxt['last_en']} | ไทย: {nxt['last_th']} → Next word!"

        st = nxt

    save_state(st)
    return jsonify(public_state(st))

@app.post("/api/hint_letter")
def api_hint_letter():
    st = get_state()
    if not st:
        return jsonify({"error": "no_game"}), 400
    if st["status"] != "playing":
        return jsonify(public_state(st))

    used = int(st.get("hint_letters_used", 0))
    if used >= HINT_LETTER_MAX:
        st["message"] = "Hint letter limit reached (2 per word)."
        save_state(st)
        return jsonify(public_state(st))

    word = st["word"]
    guessed = set(st["guessed"])
    remaining = sorted({c for c in word if c.isalpha() and c not in guessed})

    if not remaining:
        st["message"] = "No letters left to reveal."
        save_state(st)
        return jsonify(public_state(st))

    reveal = random.choice(remaining)
    guessed.add(reveal)
    st["guessed"] = sorted(list(guessed))

    st["hint_letters_used"] = used + 1
    st["life"] = int(st["life"]) - HINT_LETTER_COST
    st["message"] = f"💡 Hint: '{reveal}' (-{HINT_LETTER_COST} life) | {st['hint_letters_used']}/{HINT_LETTER_MAX}"

    # fail after hint
    if st["life"] <= 0:
        about_en = (st.get("desc_en") or st.get("extract_en") or "").strip()
        st["status"] = "failed"
        st["last_en"] = word
        st["last_th"] = translate_to_th(word) or "-"
        st["last_about_en"] = about_en or "-"
        st["last_about_th"] = translate_to_th(about_en) if about_en else "-"
        st["message"] = f"💀 GAME OVER! Word: {st['last_en']} | ไทย: {st['last_th']}"
        save_state(st)
        return jsonify(public_state(st))

    # clear after hint -> next round
    if all(c in guessed for c in word):
        about_en = (st.get("desc_en") or st.get("extract_en") or "").strip()
        st["last_en"] = word
        st["last_th"] = translate_to_th(word) or "-"
        st["last_about_en"] = about_en or "-"
        st["last_about_th"] = translate_to_th(about_en) if about_en else "-"

        next_stage = int(st["stage"]) + 1
        nxt = start_round(stage=next_stage, life=int(st["life"]))

        nxt["last_en"] = st["last_en"]
        nxt["last_th"] = st["last_th"]
        nxt["last_about_en"] = st["last_about_en"]
        nxt["last_about_th"] = st["last_about_th"]
        nxt["message"] = f"🎉 CLEAR! {nxt['last_en']} | ไทย: {nxt['last_th']} → Next word!"

        st = nxt

    save_state(st)
    return jsonify(public_state(st))

if __name__ == "__main__":
    app.run(debug=True)
