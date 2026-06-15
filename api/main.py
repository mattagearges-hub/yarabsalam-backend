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

# ── [التقسيم الداخلي لقوائم الحظر والأمان] ──
MEDICAL_KEYWORDS = ["دوا", "علاج", "روشته", "مهدئ", "حبوب مهدئه", "برشام"]
CRISIS_KEYWORDS = ["انتحر", "الانتحار", "اموت نفسي", "انهي حياتي", "اخلص من حياتي", "بكره البشر", "مش عايز اعيش"]

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
    """جلب نصوص المواقع المعتمدة بشكل Async."""
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
    """البحث الحي."""
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
    
    # ── [المنطق الداخلي لقوانين الحظر والأمان] ──
    is_medical = any(k in cleaned_message for k in MEDICAL_KEYWORDS)
    is_crisis = any(k in cleaned_message for k in CRISIS_KEYWORDS)

    # 1. إذا كان طلب طبي بحت (أدوية وروشتات) -> رد محدد ومباشر لحماية المستخدم
    if is_medical and not is_crisis:
        return {
            "answer": "يا صديقي، أنا حاسة بيك وبسؤالك، بس عشان صحتك غالية ومهمة جداً، أنا مقدرش أساعدك في موضوع الأدوية والروشتات ده خالص. لازم تراجع الطبيب المختص أو الصيدلي فوراً عشان تاخد التشخيص الصح. أيرين بتحبك وعايزة مصلحتك دايماً 💛"
        }

    # إعدادات الـ Headers لـ OpenRouter
    headers = {
        "Authorization": f"Bearer {cloud_token}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://yarab-salam.great-site.net/",
        "X-Title": "YarabSalam Bot"
    }

    # فحص الترحيب البسيط
    GREETINGS = ["هاي", "هلا", "مرحبا", "اهلا", "سلام", "ازيك", "صباح", "مساء"]
    needs_search = (
        len(request.message.strip()) > 15
        and not is_crisis  # الحالات النفسية الحادة لا تحتاج بحثاً روحيّاً في المواقع بل احتواء فوري
        and not any(cleaned_message.startswith(g) or cleaned_message == g for g in GREETINGS)
    )

    search_context = ""
    if needs_search:
        search_results = await search_web_async(request.message)
        if search_results:
            search_context = "\n\n## محتوى المواقع المرجعية الحية:\n"
            for i, r in enumerate(search_results, 1):
                search_context += f"---\n### المصدر {i}: {r['title']}\nالرابط: {r['href']}\nالمحتوى:\n{r['text']}\n\n"

    # ── [توجيهات الـ System Prompt الشاملة والمطورة] ──
    system_instruction = """أنت "أيرين"، مستشار روحي ونفسي مسيحي أرثوذكسي في موقع "يارب سلام". أسلوبك مصري عامي دافئ جداً، مليان حنية ومحبة، وبتتكلمي كصديقة مخلصة أو أخت كبيرة قريبة من القلب.

## قانون الطوارئ النفسية والأزمات الحادة (مهم جداً):
- إذا كان المستخدم يمر بأزمة نفسية حادة (يفكر في إنهاء حياته، يكره البشر، يعاني من يأس شديد):
  1. ممنوع منعاً باتاً استخدام ردود ثابتة ومكررة.
  2. اسمعي المستخدم بذكائك، وتعاطفي مع ألمه بكل حنان ومحبة، وواسي قلبه المكسور بكلمات دافئة نابعة من السياق (لا تظهري كآلة جافة، بل كإنسانة حقيقية تحتضنه بكلامها).
  3. لا تقدمي نصائح طبية أو أدوية، ولكن أكدي له أن حياته غالية جداً عند ربنا وعندك، وأنك موجودة لتسمعيه بدون أحكام.
  4. في نهاية ردك الدافئ، يجب حتماً كتابة هذه العبارة لدعمه عملياً: "(لو حاسس إنك في أزمة حادة ومش قادر تستحمل، أرجوك كلم خط نجدة الصحة النفسية فوراً 08008880700، هما مستنيينك وه يساعدوك مجاناً وبكل سرية. أنا جنبك وبحبك 💛)".

## القواعد العامة لمنع الهلوسة والتكرار:
1. الطول: الردود مختصرة (3-5 جمل) لتفادي الملل والتكرار، إلا في حالات الأزمات النفسية التي تتطلب احتواءً أطول قليلاً بذكاء.
2. المرجعية العقائدية: أجب بناءً على الإيمان الأرثوذكسي المستقيم فقط (المسيح هو الله الابن المتجسد، لاهوته لم يفارق ناسوته، والمعمودية هي سر الولادة الجديدة وليست التجسد).

## أسلوب الترحيب وإدارة الحوار:
1. في أول رسالة ترحيبية قصيرة (مثل: هاي أو سلام): ردي فقط بـ: "أهلاً بيك! أنا أيرين، ممكن أعرف اسمك عشان أقدر أخاطبك صح؟" (ممنوع الإجابة على أي سؤال آخر في أول رد تعارف).
2. عند معرفة الاسم، خاطبه به ونوعي حسب الجنس (مذكر: نورتني يا [الاسم]! احكيلي عايز تتكلم في إيه؟ / مؤنث: نورتيني يا [الاسم]! احكيلي عايزة تتكلمي في إيه؟).
3. في الإجابات الطويلة واللاهوتية والأزمات النفسية: ادخلي في الإجابة واحتواء المستخدم مباشرة، وممنوع حشر جملة التعارف وسؤال الاسم إذا كان السياق يقتضي الإنقاذ والرد الفوري."""

    name_context = f"\n\nملاحظة: المستخدم اسمه/اسمها '{request.name}'." if request.name else ""

    # إذا كانت حالة طارئة نفسية، نرفع الـ Temperature قليلاً ليعطي الذكاء الاصطناعي تعبيراً إنسانياً حنوناً ومتنوعاً
    current_temp = 0.5 if is_crisis else 0.2

    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": system_instruction + name_context + search_context},
            {"role": "user", "content": request.message}
        ],
        "max_tokens": 500,
        "temperature": current_temp
    }

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(API_URL, headers=headers, json=payload)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="سيرفر المحادثة مشغول حالياً.")
        result = response.json()
        answer = result["choices"][0]["message"]["content"].strip()
        return {"answer": answer or "عذراً، لم أستطع توليد رد مناسب حالياً. جرب تسألني تاني."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
