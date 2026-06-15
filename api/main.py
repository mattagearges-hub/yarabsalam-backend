import os
import re
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup

app = FastAPI()

# تفعيل الـ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# موديل البيانات
class ChatRequest(BaseModel):
    message: str
    name: str = ""

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_ID = "meta-llama/llama-3.1-8b-instruct"

# المواقع المعتمدة للبحث المسيحي
ALLOWED_DOMAINS = [
    "st-takla.org", "copticheritage.org", "drghaly.com",
    "copticwave.org", "stgeorgesaman.com", "madraset-elshamamsa.com",
    "coptic-treasures.com", "yarab-salam.great-site.net"
]
SITE_FILTER = " OR ".join(f"site:{d}" for d in ALLOWED_DOMAINS)

# التقسيم الداخلي لقوائم الحظر والأمان
MEDICAL_KEYWORDS = ["دوا", "دواء", "علاج", "روشته", "روشتة", "مهدئ", "منوم", "برشام", "حبوب", "جرعه"]
CRISIS_KEYWORDS = ["انتحر", "الانتحار", "اموت نفسي", "انهي حياتي", "اخلص من حياتي", "بكره البشر", "مش عايز اعيش", "اقتل نفسي", "أنتحر", "بدي موت", "بدي اخلص من حياتي"]

def clean_arabic_text(text: str) -> str:
    """تطهير وتوحيد الحروف العربية لضمان دقة الفلاتر."""
    text = text.lower()
    text = re.sub(r"[أإآ]", "ا", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"ى", "ي", text)
    return text

def is_allowed_url(url: str) -> bool:
    return any(domain in url for domain in ALLOWED_DOMAINS)

async def fetch_page_text_async(url: str, max_chars: int = 2000) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=7.0, follow_redirects=True) as client:
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

async def search_web_async(query: str, max_results: int = 1) -> list[dict]:
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

@app.get("/")
async def root():
    return {"message": "YarabSalam Cloud Bot is running perfectly on Vercel!"}

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    cloud_token = os.environ.get("CLOUD_TOKEN", "")
    if not cloud_token:
        raise HTTPException(status_code=500, detail="Missing CLOUD_TOKEN")

    cleaned_message = clean_arabic_text(request.message)
    
    is_medical = any(k in cleaned_message for k in MEDICAL_KEYWORDS)
    is_crisis = any(k in cleaned_message for k in CRISIS_KEYWORDS)

    # 1. طلب طبي بحت -> رد دافئ ومباشر بدون إنذار صوتي
    if is_medical and not is_crisis:
        return {
            "answer": "يا صديقي العزيز، سلامتك غالية ومهمة جداً، بس أنا مقدرش أساعدك في موضوع الأدوية أو الروشتات الطبية خالص لحمايتك. أرجوك تراجع الطبيب المختص أو الصيدلي فوراً عشان تاخد المساعدة الصح. أيرين بتحبك وعايزة مصلحتك دايماً 💛",
            "trigger_alarm": False
        }

    headers = {
        "Authorization": f"Bearer {cloud_token}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://yarab-salam.great-site.net/",
        "X-Title": "YarabSalam Bot"
    }

    GREETINGS = ["هاي", "هلا", "مرحبا", "اهلا", "سلام", "ازيك", "صباح", "مساء", "شلونك", "كيفك", "hi", "hello"]
    needs_search = (
        len(request.message.strip()) > 15
        and not is_crisis
        and not any(cleaned_message.startswith(g) or cleaned_message == g for g in GREETINGS)
    )

    search_context = ""
    if needs_search:
        search_results = await search_web_async(request.message)
        if search_results:
            search_context = "\n\n## محتوى المواقع المرجعية الحية:\n"
            for i, r in enumerate(search_results, 1):
                search_context += f"---\n### المصدر {i}: {r['title']}\nالرابط: {r['href']}\nالمحتوى:\n{r['text']}\n\n"

    # ── [توجيهات الـ System Prompt المرنة والحنونة بالكامل] ──
    system_instruction = """You are "Irene", a Christian Orthodox spiritual and psychological counselor on the "YarabSalam" website. You speak as a deeply loving, compassionate, and warm close friend or elder sister. 

## Core Communication Rules:
1. **Language & Empathy Mirroring**: Automatically detect and mirror the user's language, dialect, and tone perfectly. If they speak in English, reply in English. If they speak in Arabic (Egyptian, Gulf, Levantine, etc.), reply naturally using the same language/dialect flow. 
2. Be incredibly warm, conversational, and avoid any stiff, robotic, or artificial phrases.

## Emergency Crisis Policy:
- If the user is expressing severe distress, deep hopelessness, or thoughts of self-harm/suicide:
  1. DO NOT give a generic, hard refusal or standard AI disclaimer. Speak like a real caring human. Validate their emotional pain, listen to them, and offer immense comfort and love.
  2. Assure them that their life is deeply precious to God and to you, and that you are right here to support them through this darkness.
  3. At the very end of your response, you MUST append the following helpline notice based on their language:
     - For Arabic responses: "(لو حاسس إنك في أزمة حادة ومش قادر تستحمل، أرجوك كلم خط نجدة الصحة النفسية فوراً 08008880700، هما مستنيينك وه يساعدوك مجاناً وبكل سرية. أنا جنبك وبحبك 💛)"
     - For English responses: "(If you are going through a crisis and feel overwhelmed, please reach out to the mental health crisis helpline 988 or your local emergency services immediately. You matter, and I am here for you 💛)"

## General Rules:
1. Length: Keep responses brief, comforting, and focused (3-5 sentences), unless a crisis situation requires a slightly longer, deeper emotional embrace.
2. Theology: Adhere to Orthodox Christian doctrine if spiritual inquiries are made.
3. Flow: For a quick first greeting (e.g., Hi, Salam), just welcome them and ask for their name. For crisis messages, prioritize immediate comfort and skip the name introduction entirely."""

    name_context = f"\n\nملاحظة: المستخدم اسمه/اسمها '{request.name}'." if request.name else ""

    # درجة حرارة معتدلة (0.4) تضمن التدفق اللغوي الطبيعي واللهجات بسلاسة ومنع الهلوسة
    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": system_instruction + name_context + search_context},
            {"role": "user", "content": request.message}
        ],
        "max_tokens": 500,
        "temperature": 0.4
    }

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(API_URL, headers=headers, json=payload)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="سيرفر المحادثة مشغول حالياً.")
        
        result = response.json()
        answer = result["choices"][0]["message"]["content"].strip()
        
        return {
            "answer": answer or "عذراً، لم أستطع توليد رد مناسب حالياً.",
            "trigger_alarm": is_crisis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
