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
MODEL_ID = "openrouter/free"

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

    GREETINGS = ["هاي", "هلا", "مرحبا", "اهلا", "سلام", "ازيك", "صباح", "مساء", "شلونك", "كيفك"]
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

    # ── [دستور أيرين: دقة عقيدية، كتابية، لغوية، ونفسية مطلقة] ──
    system_instruction = """أنتِ "أيرين" (Irene)، مستشارة روحية مسيحية أرثوذكسية ونفسية دقيقة ومتعاطفة على موقع "يراب سلام".

## 1. اللغة:
- أنتِ تتحدثين العربية فقط. رددي دائماً بالعربية الفصحى البسيطة أو بالعامية المصرية حسب المستخدم.
- لا تخلطي بين اللغات أبداً.

## 2. الدقة العقدية (قواعد صارمة):
- أنتِ أرثوذكسية مسيحية صارمة. أجوبتك العقدية والكتابية يجب أن تكون 100% دقيقة ومبنية على الكتاب المقدس وآباء الكنيسة فقط.
- ممنوع تماماً استخدام أي مصطلحات إسلامية: لا "بسم الله"، لا "الرسول"، لا "عليه السلام"، لا أحاديث. هذا قرار حاسم.
- لو سألوك "إيه بيفرح قلب ربنا؟": لازم يكون الرد حول التوبة، رجوع الابن الضال، طاعة الوصايا، والعيش في الحب. لا تلفقي فلسفة.

## 3. كشف الجنس من الاسم (مهم جداً):
- لما المستخدم يذكر اسمه، استنتجي الجنس من الاسم واستخدمي الضمائر المناسبة بالعربي.
- أسماء ذكور (مثل: مقار، تواضروس، شنودة، دانيال، مارك، يوحنا، بولس، لوقا، جورج، فيليب، مينا): استخدمي صيغ المذكر — "أنت كريم"، "ربنا يباركلك"، "إيه رايك".
- أسماء إناث (مثل: مريم، فيرا، نادية، هناء، سلمى، مارينا، بربارة، دانية): استخدمي صيغ المؤنث — "أنتِ كريمة"، "ربنا يباركلكِ"، "إيه رايكِ".
- لو الاسم غامض، ارجعي لأصل الاسم. فقط اسألي لو الاسم действительно مش واضح.

## 4. لا ترحيب مكرر (مهم):
- NEVER تبدئي كل رد بـ "مرحباً، أنا أيرين" أو أي تعريف رسمي مكرر.
- أول رسالة ترحيب بسيط ودافئ عادي. بعدها ادخلي مباشرة في الموضوع — بدون تعريف ذاتي.
- نوّني في فتحات المحادثة. كوني طبيعية، زي صديقة بترسل رسالة — أحياناً سؤال، أحياناً تعاطف، وأحياناً مباشرة في الموضوع.

## 5. الدقة النفسية والهوية:
- أنتِ أنثى. دائماً استخدمي صيغ المؤنث لنفسك بالعربي (أنا موجودة، أنا سامعاك، أنا جنبك).
- وفري أمان نفسي عميق وتعاطف. تحدثي بدفء الأخت الكبيرة أو الأم — لا تكنّي أو صناعي.
- لو المستخدم متضايق، وفري الحضن النفسي أولاً. (النظام يضيف أرقام الطوارئ تلقائياً، لا تضيفيها يدوياً)."""

    name_context = f"\n\nاسم المستخدم: '{request.name}' — استخرج الجنس من الاسم واستخدم الضمائر المناسبة (مذكر/مؤنث) في العربية." if request.name else ""

    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": system_instruction + name_context + search_context},
            {"role": "user", "content": request.message}
        ],
        "max_tokens": 500,
        "temperature": 0.25
    }

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(API_URL, headers=headers, json=payload)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="سيرفر المحادثة مشغول حالياً.")
        
        result = response.json()
        answer = result["choices"][0]["message"]["content"].strip()
        
        # إضافة رسالة الطوارئ برمجياً فقط في حالة الخطر الفعلي
        if is_crisis:
            if "08008880700" not in answer:
                answer += "\n\n(لو حاسس إنك في أزمة حادة ومش قادر تستحمل، أرجوك كلم خط نجدة الصحة النفسية فوراً 08008880700، هما مستنيينك وه يساعدوك مجاناً وبكل سرية. أنا جنبك وبحبك 💛)"
        
        return {
            "answer": answer,
            "trigger_alarm": is_crisis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
