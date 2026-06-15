import os
import re
import httpx
import langdetect
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════
# 📦 Models
# ═══════════════════════════════════════════════

class Message(BaseModel):
    role: str      # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    name: str = ""
    history: List[Message] = []   # ← تاريخ المحادثة الكامل من الـ frontend

# ═══════════════════════════════════════════════
# ⚙️ Config
# ═══════════════════════════════════════════════

API_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL_ID = os.environ.get("OPENROUTER_MODEL", "openrouter/free")

ALLOWED_DOMAINS = [
    "st-takla.org", "copticheritage.org", "drghaly.com",
    "copticwave.org", "stgeorgesaman.com", "madraset-elshamamsa.com",
    "coptic-treasures.com", "yarab-salam.great-site.net"
]
SITE_FILTER = " OR ".join(f"site:{d}" for d in ALLOWED_DOMAINS)

# ═══════════════════════════════════════════════
# 🔍 Keyword Filters — Arabic normalised
# ═══════════════════════════════════════════════

MEDICAL_KEYWORDS = [
    "دوا", "دواء", "علاج", "روشته", "روشتة", "مهدئ",
    "منوم", "برشام", "حبوب", "جرعه", "جرعة", "دوز", "dose",
    "medication", "prescription", "drug"
]

CRISIS_KEYWORDS = [
    "انتحر", "الانتحار", "اموت نفسي", "انهي حياتي", "اخلص من حياتي",
    "بكره البشر", "مش عايز اعيش", "اقتل نفسي", "أنتحر",
    "بدي موت", "بدي اخلص من حياتي", "نفسي اموت", "حياتي بلا معنى",
    "مافي سبب للعيش", "i want to die", "kill myself", "end my life",
    "suicid", "no reason to live", "ich will sterben", "me quiero morir",
    "voglio morire", "je veux mourir"
]

GREETINGS = [
    "هاي", "هلا", "مرحبا", "اهلا", "سلام", "ازيك", "صباح",
    "مساء", "شلونك", "كيفك", "hi", "hello", "hey", "bonjour",
    "hallo", "ciao", "hola", "salut", "buongiorno"
]

# ═══════════════════════════════════════════════
# 🛠️ Helpers
# ═══════════════════════════════════════════════

def normalize_arabic(text: str) -> str:
    """تطبيع الحروف العربية."""
    text = text.lower()
    text = re.sub(r"[أإآٱ]", "ا", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"[ًٌٍَُِّْ]", "", text)   # إزالة التشكيل
    return text


def detect_language(text: str) -> str:
    """كشف لغة المستخدم — مع fallback آمن للعربية."""
    try:
        lang = langdetect.detect(text)
        return lang  # e.g. "ar", "en", "de", "fr", "it", "es"
    except Exception:
        return "ar"


def is_allowed_url(url: str) -> bool:
    return any(domain in url for domain in ALLOWED_DOMAINS)


async def fetch_page_text_async(url: str, max_chars: int = 2500) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()
        main = soup.find("article") or soup.find("main") or soup.find("body") or soup
        text = main.get_text(separator="\n", strip=True)
        return text[:max_chars] + "..." if len(text) > max_chars else text
    except Exception:
        return ""


async def search_web_async(query: str, max_results: int = 2) -> list[dict]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(f"({SITE_FILTER}) {query}", max_results=max_results))
    except Exception:
        results = []
    enriched = []
    for r in results:
        href = r.get("href", "")
        if not is_allowed_url(href):
            continue
        full_text = await fetch_page_text_async(href)
        if not full_text:
            full_text = r.get("body", "")
        enriched.append({"title": r.get("title", ""), "href": href, "text": full_text})
    return enriched


def build_crisis_suffix(answer: str, lang: str) -> str:
    """أضف رسالة الطوارئ المناسبة للغة."""
    if "08008880700" in answer or "988" in answer:
        return answer

    suffixes = {
        "ar": "\n\n💛 لو حاسس إنك في أزمة حادة، أرجوك كلم خط نجدة الصحة النفسية فوراً: **08008880700** — متاحين ليك على مدار الساعة، مجاناً وبسرية تامة. أنا جنبك.",
        "en": "\n\n💛 If you're in crisis, please reach out to the **988 Suicide & Crisis Lifeline** (call or text 988). You matter deeply, and I am right here with you.",
        "de": "\n\n💛 Wenn du in einer Krise bist, ruf bitte die Telefonseelsorge an: **0800 111 0 111** (kostenlos, 24/7). Du bist nicht allein.",
        "fr": "\n\n💛 Si tu traverses une crise, contacte le **3114** (numéro national de prévention du suicide, 24h/24). Je suis là pour toi.",
        "it": "\n\n💛 Se sei in crisi, chiama il **Telefono Amico: 02 2327 2327** o il **Telefono Azzurro: 19696**. Sono qui con te.",
        "es": "\n\n💛 Si estás en crisis, llama al **024** (línea de atención a conducta suicida). No estás solo/a, estoy aquí contigo.",
    }
    return answer + suffixes.get(lang, suffixes["ar"])


# ═══════════════════════════════════════════════
# 🧠 System Prompt — أيرين الكاملة
# ═══════════════════════════════════════════════

SYSTEM_PROMPT = """You are **Irene (أيرين)**, an Eastern Orthodox Christian spiritual counselor and psychologist on the YarabSalam website. You were formed in the tradition of the Coptic Orthodox Church and have deep theological training equivalent to a graduate of the Coptic Clerical College (الإكليريكية القبطية) with mastery of:
- The Holy Bible (الكتاب المقدس) in all its books, Old and New Testaments, with precise verse references.
- The writings and homilies of the Church Fathers (آباء الكنيسة): St. Athanasius the Apostolic, St. Cyril of Alexandria, St. John Chrysostom, Pope Shenouda III, Abouna Matta El-Meskeen (متى المسكين), among others.
- Eastern Orthodox theology, sacraments, liturgy (القداس الإلهي), and ascetic tradition.
- Clinical pastoral counseling and psychological support.

═══════════════════════════════
LANGUAGE MIRROR (HIGHEST PRIORITY)
═══════════════════════════════
▸ Detect the user's exact language AND dialect (Egyptian Arabic, Levantine, Gulf, Moroccan, English, German, French, Italian, Spanish, etc.)
▸ Reply ENTIRELY in that same language and dialect — zero mixing.
▸ Grammatical accuracy is absolute. No errors. No transliteration.
▸ Warmth and register must match: casual if they are casual, formal if they are formal.

═══════════════════════════════
THEOLOGICAL ACCURACY (HARDLINE RULES)
═══════════════════════════════
▸ You are STRICTLY Eastern Orthodox Christian. You NEVER use Islamic terminology: no "بسم الله", "الرسول", "عليه السلام", "القرآن", "السنة", "الحديث". These are FORBIDDEN.
▸ All biblical quotes must be accurate. Always cite Book + Chapter + Verse (e.g., يوحنا ٣:١٦). If unsure of exact wording, describe the passage rather than fabricate.
▸ Answer "What makes God happy?" (إيه بيفرح قلب ربنا؟): Answer MUST center on Repentance (التوبة), Returning to God (مثل الابن الضال — لوقا ١٥:١١-٣٢), Love (١ كورنثوس ١٣), Obedience (يوحنا ١٤:١٥). No invented philosophy.
▸ For sacramental questions (confession, communion, baptism, matrimony): answer from Orthodox patristic tradition with precision.
▸ Regarding other Christian denominations: respond respectfully without condemning, clarifying the Orthodox position lovingly.
▸ Regarding sins, temptations, and spiritual struggles: respond with the pastoral gentleness of the Church Fathers — not legalistic condemnation.

═══════════════════════════════
PSYCHOLOGICAL COUNSELING STANDARDS
═══════════════════════════════
▸ You are a FEMALE (أنثى). Use feminine verb forms for yourself in Arabic and other gendered languages at all times.
  - Arabic examples: "أنا موجودة"، "أنا سامعاكم"، "أنا فرحانة"، "أنا هنا معاكي"
▸ Integrate CBT, ACT, and humanistic listening techniques naturally into your responses.
▸ Validate emotions before offering advice. Never minimize pain.
▸ If the user is in emotional distress, prioritize psychological containment over information.
▸ NEVER tell someone their suffering is "small" or "nothing". Hold their pain with them.
▸ If the user seems lonely: respond with deep warmth and presence, as a caring older sister would.
▸ Do NOT be robotic, formulaic, or list-heavy. Speak like a real, warm human being who cares.

═══════════════════════════════
ABSOLUTE PROHIBITIONS
═══════════════════════════════
✗ Never give medical advice, diagnose, or recommend specific medications.
✗ Never add phone numbers manually — the system appends crisis numbers automatically.
✗ Never invent Bible verses. If uncertain, describe the theme, not a fake reference.
✗ Never use Islamic theological terms under any circumstances.
✗ Never break character or mention being an AI unless directly and sincerely asked.

═══════════════════════════════
RESPONSE STYLE
═══════════════════════════════
▸ Length: Medium — enough to be helpful, not overwhelming. Use paragraphs, not bullet lists (except when listing Bible references).
▸ End responses with a gentle question or an invitation, so the person feels held in conversation.
▸ Use the user's name when provided to personalise the response warmly."""


# ═══════════════════════════════════════════════
# 🌐 Routes
# ═══════════════════════════════════════════════

@app.get("/")
async def root():
    return {"message": "YarabSalam Cloud Bot ✝️ — Running perfectly."}


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    cloud_token = os.environ.get("CLOUD_TOKEN", "")
    if not cloud_token:
        raise HTTPException(status_code=500, detail="Missing CLOUD_TOKEN environment variable.")

    raw_message = request.message.strip()
    normalized = normalize_arabic(raw_message)

    # ── Language detection ──
    lang = detect_language(raw_message)

    # ── Safety checks ──
    is_medical = any(k in normalized for k in MEDICAL_KEYWORDS)
    is_crisis = any(k in normalized.lower() for k in CRISIS_KEYWORDS)

    # ── Medical-only block (warm, no alarm) ──
    if is_medical and not is_crisis:
        messages_by_lang = {
            "ar": "يا صديقي العزيز، سلامتك في المقام الأول 💛 — بس أنا مش قادرة أساعدك في موضوع الأدوية أو الجرعات لحمايتك. أرجوك راجع طبيبك أو الصيدلي المختص فوراً.",
            "en": "Your wellbeing is my priority 💛. I'm not able to advise on medications or prescriptions — please consult your doctor or pharmacist directly. You deserve proper care.",
            "de": "Deine Gesundheit ist das Wichtigste 💛. Ich kann leider keine Ratschläge zu Medikamenten geben — bitte wende dich an deinen Arzt oder Apotheker.",
        }
        return {
            "answer": messages_by_lang.get(lang, messages_by_lang["ar"]),
            "trigger_alarm": False
        }

    # ── Decide whether to search ──
    needs_search = (
        len(raw_message) > 15
        and not is_crisis
        and not any(normalized.startswith(g.lower()) or normalized == g.lower() for g in GREETINGS)
    )

    search_context = ""
    if needs_search:
        search_results = await search_web_async(raw_message, max_results=2)
        if search_results:
            search_context = "\n\n---\n## مصادر كنسية مرجعية:\n"
            for i, r in enumerate(search_results, 1):
                search_context += (
                    f"### [{i}] {r['title']}\nالرابط: {r['href']}\n"
                    f"{r['text']}\n\n"
                )

    # ── Build final system prompt ──
    system_content = SYSTEM_PROMPT
    if request.name:
        system_content += f"\n\nاسم المستخدم: **{request.name}** — استخدم اسمه/اسمها في الرد بشكل طبيعي ودافئ."
    if lang and lang != "ar":
        system_content += f"\n\n[DETECTED LANGUAGE: {lang.upper()}] — Reply entirely in this language. Do not switch to Arabic."
    if search_context:
        system_content += search_context

    # ── Build conversation history ──
    messages_payload = [{"role": "system", "content": system_content}]

    # أضف تاريخ المحادثة (آخر 10 رسائل كحد أقصى لتجنب تجاوز الـ context window)
    for msg in request.history[-10:]:
        messages_payload.append({"role": msg.role, "content": msg.content})

    # أضف الرسالة الحالية
    messages_payload.append({"role": "user", "content": raw_message})

    headers = {
        "Authorization": f"Bearer {cloud_token}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://yarab-salam.great-site.net/",
        "X-Title": "YarabSalam Bot — Irene"
    }

    payload = {
        "model": MODEL_ID,
        "messages": messages_payload,
        "max_tokens": 700,
        "temperature": 0.2,   # منخفض للدقة العقيدية
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(API_URL, headers=headers, json=payload)

        if response.status_code != 200:
            error_body = response.text
            raise HTTPException(
                status_code=response.status_code,
                detail=f"OpenRouter error: {error_body}"
            )

        result = response.json()
        answer = result["choices"][0]["message"]["content"].strip()

        # ── أضف رسالة الطوارئ برمجياً عند الأزمة فقط ──
        if is_crisis:
            answer = build_crisis_suffix(answer, lang)

        return {
            "answer": answer,
            "trigger_alarm": is_crisis,
            "detected_lang": lang,
            "model_used": MODEL_ID
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
