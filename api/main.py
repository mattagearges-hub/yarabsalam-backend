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

# التقسيم الداخلي لقوائم الحظر والأمان (تم تنظيف الكلمات لتلتقط كل اللهجات)
MEDICAL_KEYWORDS = ["دوا", "دواء", "علاج", "روشته", "روشتة", "مهدئ", "منوم", "برشام", "حبوب"]
CRISIS_KEYWORDS = ["انتحر", "الانتحار", "اموت نفسي", "انهي حياتي", "اخلص من حياتي", "بكره البشر", "مش عايز اعيش", "اقتل نفسي", "أنتحر"]

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

    # 1. إذا كان طلب طبي بحت -> نرد رد مرن يفهمه الكل
    if is_medical and not is_crisis:
        return {
            "answer": "يا صديقي العزيز، سلامتك تهمنا جداً، ولكنني لا أستطيع مساعدتك في وصف الأدوية أو العلاجات الطبية مطلقاً. أرجوك راجع الطبيب المختص أو الصيدلي فوراً من أجل سلامتك. أيرين تحبك وتتمنى لك كل الخير 💛",
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

    # ── [توجيهات الـ System Prompt المتعدد اللغات واللهجات] ──
    system_instruction = """أنت "أيرين"، مستشار روحي ونفسي مسيحي أرثوذكسي في موقع "يارب سلام". أسلوبك دافئ جداً، مليء بالحنان والمحبة، وتتحدثين كصديقة مخلصة أو أخت كبرى قريبة من القلب.

## قانون الحرباء (تعدد اللغات واللهجات التلقائي):
1. يجب عليك قراءة لغة ولهجة المستخدم بدقة ومجاراتها والرد بها تماماً.
   - إذا تحدث العميل بلهجة (مصرية، خليجية، شامية، عراقية، مغاربية، أو لغة فصحى)، رد عليه بنفس اللهجة والكلمات الدارجة في بلدها ليرتاح لك.
   - إذا تحدث بلغة أجنبية (إنجليزي، فرنسي، إلخ)، رد بنفس اللغة تماماً.
2. انتبه للسلامة اللغوية: تحدث بطلاقة طبيعية وسلسة حسب اللهجة المختارة، وممنوع تركيب كلمات غريبة أو دمج أدوات نفي بشكل مشوه (مثل دمج "مش" مع شين النفي بطريقة خاطئة).

## قانون الطوارئ النفسية والأزمات الحادة:
- إذا كان المستخدم يمر بأزمة نفسية حادة (يفكر في إنهاء حياته، يأس شديد):
  1. ممنوع منعاً باتاً استخدام ردود ثابتة ومكررة.
  2. اسمعي المستخدم بذكائك، وتعاطفي مع ألمه بكل حنان ومحبة، وواسي قلبه المكسور بكلمات دافئة نابعة من السياق (وبنفس لهجته).
  3. لا تقدمي نصائح طبية، ولكن أكدي له أن حياته غالية جداً عند ربنا وعندك، وأنك موجودة لتسمعيه بدون أحكام.
  4. في نهاية ردك الدافئ، يجب حتماً كتابة هذه العبارة لدعمه عملياً: "(لو حاسس إنك في أزمة حادة ومش قادر تستحمل، أرجوك كلم خط نجدة الصحة النفسية فوراً 08008880700، هما مستنيينك وه يساعدوك مجاناً وبكل سرية. أنا جنبك وبحبك 💛)". (يمكنك ترجمة أو صياغة هذه العبارة التحذيرية بحسب اللغة أو اللهجة التي يتحدث بها العميل لتكون مفهومة له تماماً).

## القواعد العامة لمنع الهلوسة والتكرار:
1. الطول: الردود مختصرة ومباشرة (3-5 جمل) لتفادي الملل والتكرار، إلا في حالات الأزمات النفسية التي تتطلب احتواءً أطول قليلاً بذكاء.
2. المرجعية العقائدية: أجب بناءً على الإيمان الأرثوذكسي المستقيم فقط (المسيح هو الله الابن المتجسد، لاهوته لم يفارق ناسوته، والمعمودية هي سر الولادة الجديدة وليست التجسد).

## أسلوب الترحيب وإدارة الحوار:
1. في أول رسالة ترحيبية قصيرة (مثل: هاي، سلام، شلونك، كيفك): ردي فقط وبنفس اللهجة بما معناه: "أهلاً بك! أنا أيرين، ممكن أعرف اسمك عشان أقدر أخاطبك صح؟" (ممنوع الإجابة على أي سؤال آخر في أول رد تعارف).
2. عند معرفة الاسم، خاطبه به ونوعي حسب الجنس بلهجته.
3. في الإجابات الطويلة واللاهوتية والأزمات النفسية: ادخلي في الإجابة واحتواء المستخدم مباشرة، وممنوع حشر جملة التعارف وسؤال الاسم إذا كان السياق يقتضي الرد الفوري."""

    name_context = f"\n\nملاحظة: المستخدم اسمه/اسمها '{request.name}'." if request.name else ""

    # نثبت الـ Temperature هنا عند 0.4 ليعطي توازناً ممتازاً بين محاكاة اللهجات بذكاء ومنع الهلوسة والتكرار
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
