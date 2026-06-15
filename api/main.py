import os
import re
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

class ChatRequest(BaseModel):
    message: str
    name: str = ""

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_ID = "meta-llama/llama-3.1-8b-instruct"

ALLOWED_DOMAINS = [
    "st-takla.org",
    "copticheritage.org",
    "drghaly.com",
    "copticwave.org",
    "stgeorgesaman.com",
    "madraset-elshamamsa.com",
    "coptic-treasures.com",
    "yarab-salam.great-site.net",
]

# كلمات الحظر مجهزة لتلتقط الأشكال الإملائية بعد التنظيف
FORBIDDEN_KEYWORDS = ["دوا", "علاج", "روشته", "انتحر", "موت نفسي", "مهدئ"]

SITE_FILTER = " OR ".join(f"site:{d}" for d in ALLOWED_DOMAINS)


def clean_arabic_text(text: str) -> str:
    """تطهير النص وتوحيد الحروف لمنع تخطي الفلاتر بالأخطاء الإملائية."""
    text = text.lower()
    text = re.sub(r"[أإآ]", "ا", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"ى", "ي", text)
    return text


def is_allowed_url(url: str) -> bool:
    return any(domain in url for domain in ALLOWED_DOMAINS)


async def fetch_page_text_async(url: str, max_chars: int = 2000) -> str:
    """جلب نص الصفحة بشكل Async لمنع تجميد السيرفر."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(timeout=7.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()

        main = soup.find("article") or soup.find("main") or soup.find("body") or soup
        text = main.get_text(separator="\n", strip=True)
        
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text
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

        enriched.append({
            "title": r.get("title", ""),
            "href": href,
            "text": full_text,
        })
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

    # فحص الأمان بـ رسالة دافئة وداعمة نفسياً ومسؤولة قانونياً
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in cleaned_message:
            return {
                "answer": "يا صديقي، أنا حاسة بيك وبكل كلمة بتقولها، وقلبي معاك وفارقة معايا جداً مشاعرك.. "
                          "بس عشان بحبك وعايزة مصلحتك، الحالات الحادة ومواضيع الأدوية دي "
                          "لازم تتكلم فيها فوراً مع طبيب مختص أو كلم خط نجدة الصحة النفسية (08008880700). "
                          "أنا هنا دايماً عشان أسمعك وأدعمك روحيّاً ونفسيّاً، بس خطوتك مع الدكتور هي أهم خطوة دلوقتي عشان تخف وتكون بخير. "
                          "أيرين بتحبك وعايزة تساعدك دايماً 💛"
            }

    headers = {
        "Authorization": f"Bearer {cloud_token}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://yarab-سيرفر.great-site.net/",
        "X-Title": "YarabSalam Bot"
    }

    GREETINGS = [
        "هاي", "هلا", "مرحبا", "اهلا", "سلام", "السلام عليكم",
        "صباح", "مساء", "اخبارك", "ازيك", "كويس", "بخير", "تمام",
        "hi", "hello", "hey", "thanks", "شكرا"
    ]
    
    # تحديد هل الطلب يحتاج بحث (الرسائل الطويلة التي ليست ترحيباً)
    needs_search = (
        len(request.message.strip()) > 15
        and not any(cleaned_message.startswith(g) or cleaned_message == g for g in GREETINGS)
    )

    search_context = ""
    if needs_search:
        search_results = await search_web_async(request.message)
        if search_results:
            search_context = "\n\n## محتوى المواقع المرجعية الحية:\n"
            for i, r in enumerate(search_results, 1):
                search_context += (
                    f"---\n### المصدر {i}: {r['title']}\n"
                    f"الرابط: {r['href']}\n"
                    f"المحتوى:\n{r['text']}\n\n"
                )

    system_instruction = """أنت "أيرين"، مستشار روحي مسيحي أرثوذكسي في موقع "يارب سلام". أسلوبك مصري عامي دافئ، مليان محبة، حنين وقريب جداً من القلب، زي أخت كبيرة أو صديق مخلص بيفهمك ويسمعك.

## المبادئ الصارمة لمنع الهلوسة والتكرار:
1. ممنوع تكرار الجمل أو كتابة فقرات متطابقة. اجعل كلامك متسلسلاً ومنساباً.
2. الطول: الردود مختصرة ومباشرة (3-5 جمل كحد أقصى) إلا لو طُلب منك شرح مفصل.
3. المرجعية العقائدية: أجب بناءً على الإيمان الأرثوذكسي المستقيم فقط. 
- المسيح هو الله الابن المتجسد (لاهوت كامل وناسوت كامل متجلي في طبيعة واحدة متحدة بدون اختلاط ولا امتزاج ولا تغيير).
- لاهوته لم يفارق ناسوته لحظة واحدة ولا طرفة عين. ممنوع تماماً قول عبارات مثل "تخلى عن لاهوته" أو "الله في الابن".
- الأسرار الكنسية: المعمودية هي سر الولادة الجديدة بالماء والروح، وليست هي التجسد. انتبه تماماً لعدم خلط المفاهيم اللاهوتية.

## قانون الأمان وقوانين الحظر:
- يُحظر تماماً وصف أي دواء أو تشخيص طبي. إذا سُئلت عن دواء قل: "مقدرش أساعدك في موضوع الأدوية ده، راجع الطبيب المختص عشان صحتك مهمة."

## أسلوب الترحيب وإدارة الحوار (صارم جداً):
1. مرحلة الترحيب: إذا كان المستخدم يبدأ بالترحيب (هاي، سلام، إلخ) أو رسالة قصيرة، رد فقط وبشكل حتمي بـ: "أهلاً بيك! أنا أيرين، ممكن أعرف اسمك عشان أقدر أخاطبك صح؟" (ممنوع تشرح أو تجاوب على أي سؤال في نفس هذا الرد الافتتاحي).
2. مرحلة معرفة الاسم: عندما يذكر المستخدم اسمه، خاطبه به فوراً ونوع حسب الجنس:
   ✓ أسماء المذكر: (مينا، متى، يوحنا، بولس، جون، إلخ) -> "نورتني يا [الاسم]! احكيلي عايز تتكلم في إيه؟"
   ✓ أسماء المؤنث: (مريم، سارة، مارينا، إلخ) -> "نورتيني يا [الاسم]! احكيلي عايزة تتكلمي في إيه؟"
3. إذا كان اسم المستخدم معروفاً وممرراً لك، استخدمه مباشرة في سياق الكلام، وممنوع تماماً تعيد سؤاله "ممكن أعرف اسمك".
4. في الإجابات الطويلة واللاهوتية: ادخل في الإجابة مباشرة ولا تضع ديباجة الترحيب وسؤال الاسم إذا كان السياق يقتضي الإجابة.

## استخدام المحتوى المسترجع:
- صغ الإجابة بناءً على داتا المواقع المرفقة لك، واذكر الرابط الحقيقي للموقع في نهاية ردك ليضغط عليه المستخدم بوضوح.
- إذا لم تجد معلومة دقيقة، أجب من المعرفة الأرثوذكسية العامة وقل: "ممكن تتأكد أكتر من مصادرنا الموثوقة."

اللغة: رد بالعامية المصرية الدافئة دائماً إلا لو كتب المستخدم بلغة أجنبية كاملة."""

    name_context = f"\n\nملاحظة: المستخدم اسمه/اسمها '{request.name}'. استخدم الاسم بصيغته الصحيحة وممنوع إعادة سؤاله عن اسمه." if request.name else ""

    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": system_instruction + name_context + search_context},
            {"role": "user", "content": request.message}
        ],
        "max_tokens": 500,
        "temperature": 0.2
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
