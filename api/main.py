import os
import re
import asyncio
import logging
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from bs4 import BeautifulSoup

# ─── 1. إدارة الإعدادات الآمنة ───
class AppSettings(BaseSettings):
    cloud_token: str = Field(..., validation_alias="CLOUD_TOKEN")
    api_url: str = "https://openrouter.ai/api/v1/chat/completions"
    model_id: str = "meta-llama/llama-3.1-8b-instruct"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# محاولة تحميل الإعدادات لتجنب كراش السيرفر إذا لم ترفع الـ Token بعد
try:
    settings = AppSettings()
except Exception:
    settings = None

# ─── 2. نظام تسجيل التقارير (Logging) ───
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("YarabSalamVercelLogger")

app = FastAPI(title="YarabSalam Premium Vercel API", version="2.5.0")

# تفعيل الـ CORS بشكل كامل وصحيح للمتصفحات
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 3. نماذج البيانات (Pydantic Models) ───
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1500)
    name: str = Field("", max_length=50)

class ChatResponse(BaseModel):
    answer: str

# ─── 4. السياسات النطاقية وقوائم الفلترة ───
ALLOWED_DOMAINS = [
    "st-takla.org", "copticheritage.org", "drghaly.com", "copticwave.org",
    "stgeorgesaman.com", "madraset-elshamamsa.com", "coptic-treasures.com",
    "yarab-salam.great-site.net"
]

FORBIDDEN_KEYWORDS = [
    "دوا", "علاج", "روشته", "انتحر", "الانتحار", "موت نفسي", 
    "حبوب مهدئه", "اموت نفسي", "انتحار"
]

GREETINGS = [
    "هاي", "هلا", "مرحبا", "أهلا", "اهلا", "سلام", "السلام عليكم",
    "صباح الخير", "مساء الخير", "اخبارك", "ازيك", "تمام", "الحمد لله",
    "hi", "hello", "hey", "thanks", "شكرا"
]

# ─── 5. معالجة النصوص العربية المتقدمة ───
def normalize_arabic_text(text: str) -> str:
    """تنظيف وتوحيد الحروف العربية لمنع ثغرات الالتفاف والـ Bypass."""
    text = text.lower().strip()
    text = re.sub(r"[\u064B-\u0652]", "", text)  # إزالة التشكيل
    text = re.sub(r"[أإآأ]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"[^\w\s]", " ", text)  # إزالة علامات الترقيم
    text = re.sub(r"\s+", " ", text).strip()  # إزالة المسافات الزائدة
    return text

# ─── 6. كاشط الروابط والبحث السريع والموفر للوقت ───
async def fetch_single_page(client: httpx.AsyncClient, url: str, max_chars: int = 2000) -> str:
    """تحميل وقراءة محتوى الرابط بسرعة خارقة تناسب قيود Vercel."""
    if not any(domain in url for domain in ALLOWED_DOMAINS):
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        # مهلة قصيرة جداً (2.5 ثانية) لضمان عدم تعليق الدالة
        resp = await client.get(url, headers=headers, timeout=2.5)
        if resp.status_code != 200:
            return ""
            
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()
            
        main_content = soup.find("article") or soup.find("main") or soup.find("body") or soup
        text = main_content.get_text(separator=" ", strip=True)
        return text[:max_chars] + "..." if len(text) > max_chars else text
    except Exception:
        return ""

async def execute_search_fast(query: str) -> List[Dict[str, str]]:
    """البحث عبر الويب وجلب مراجع حية بنتيجة واحدة فقط لتفادي الـ Timeout."""
    results = []
    try:
        from duckduckgo_search import DDGS
        site_filter_query = f"({ ' OR '.join(f'site:{d}' for d in ALLOWED_DOMAINS) }) {query}"
        
        with DDGS() as ddgs:
            # نطلب نتيجة واحدة فقط لضمان السرعة القصوى على الخطة المجانية
            ddg_res = list(ddgs.text(site_filter_query, max_results=1))
            for r in ddg_res:
                results.append({"title": r.get("title"), "href": r.get("href"), "body": r.get("body")})
    except Exception as e:
        logger.error(f"DuckDuckGo Search Bypass/Error: {e}")
        return []

    if not results:
        return []

    # جلب المحتوى بالتوازي الفوري
    enriched_results = []
    async with httpx.AsyncClient() as client:
        tasks = [fetch_single_page(client, r["href"]) for r in results]
        fetched_texts = await asyncio.gather(*tasks)
        
        for r, full_text in zip(results, fetched_texts):
            final_text = full_text if full_text else r.get("body", "")
            if final_text:
                enriched_results.append({
                    "title": r["title"],
                    "href": r["href"],
                    "text": final_text
                })
                
    return enriched_results

# ─── 7. الـ Endpoint الرئيسي ───
@app.get("/")
async def root():
    return {"message": "YarabSalam Cloud Bot is running blazing fast on Vercel!"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    # التأكد من تهيئة التوكن
    if not settings or not settings.cloud_token:
        raise HTTPException(status_code=500, detail="Missing CLOUD_TOKEN environment variable.")

    # 1. فحص الفلتر الأمني لحماية الحالات الحادة فوراً
    normalized_message = normalize_arabic_text(request.message)
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in normalized_message:
            return ChatResponse(
                answer="يا صديقي، أنا هنا لتقديم الدعم الروحي والنفسي المبسط فقط. "
                       "الأدوية والحالات الحادة تتطلب استشارة طبيب مختص فوراً لحمايتك وصحتك. "
                       "أيرين بتحبك وعايزة تساعدك 💛"
            )

    # 2. تحديد نوع الرسالة (ترحيب أم سؤال حقيقي يحتاج بحث)
    is_greeting = normalized_message in GREETINGS or len(request.message.strip()) <= 12
    needs_search = not is_greeting

    search_context = ""
    if needs_search:
        # البحث السريع
        search_data = await execute_search_fast(request.message)
        if search_data:
            search_context = "\n\n## المراجع الحية المسترجعة من المواقع المعتمدة:\n"
            for i, res in enumerate(search_data, 1):
                search_context += (
                    f"---\n[المصدر {i}] العنوان: {res['title']}\n"
                    f"الرابط: {res['href']}\n"
                    f"المحتوى المرجعي:\n{res['text']}\n"
                )

    # 3. صياغة التعليمات الروحية لـ "أيرين"
    system_instruction = (
        "أنت 'أيرين'، مستشار روحي مسيحي أرثوذكسي في موقع 'يارب سلام'. "
        "أسلوبك مصري عامي دافئ ومليان محبة وقريب من القلب، كصديق حكيم يفهمك.\n\n"
        "## القواعد الصارمة والنهائية:\n"
        "1. المرجعية: أجب بناءً على العقيدة الأرثوذكسية القويمة والتعليم الآبائي والكتاب المقدس مع ذكر شواهد الآيات.\n"
        "2. الأمان الطبي: يُمنع تماماً تشخيص أمراض أو اقتراح أدوية.\n"
        "3. الالتزام بالمراجع: إذا توفرت فقرات مراجع حية، صغ إجابتك بناءً عليها واذكر رابط المصدر الحقيقي في نهاية ردك ليضغط عليه المستخدم.\n"
        "4. أسلوب الترحيب: إذا كانت الرسالة ترحيبية أو قصيرة، رد فقط وبصيغة قاطعة بـ: 'أهلاً بيك! أنا أيرين، ممكن أعرف اسمك عشان أقدر أخاطبك صح؟' ولا تطرح أي أسئلة أخرى.\n"
        "5. مناداة المستخدم: إذا تم تزويدك باسم المستخدم، ناده به لتوثيق المحبة الروحية.\n"
        "6. الإيجاز الذكي: الردود تكون مختصرة ومباشرة جداً (3-5 جمل) لتفادي انقطاع الاتصال."
    )

    if request.name:
        system_instruction += f"\n\n* ملحوظة: المستخدم الحالي اسمه هو '{request.name}'. استخدم هذا الاسم في خطابك معه."

    # 4. تجهيز الـ Payload لـ OpenRouter
    payload = {
        "model": settings.model_id,
        "messages": [
            {"role": "system", "content": system_instruction + search_context},
            {"role": "user", "content": request.message}
        ],
        "max_tokens": 400, # تقليله لـ 400 يجعل الرد أسرع بكثير على Vercel
        "temperature": 0.25
    }

    headers = {
        "Authorization": f"Bearer {settings.cloud_token}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://yarab-salam.great-site.net/",
        "X-Title": "YarabSalam Premium Bot"
    }

    try:
        # مهلة استدعاء OpenRouter مضبوطة بدقة على 6 ثوانٍ لحماية دالة Vercel من الانهيار (Timeout)
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.api_url, headers=headers, json=payload, timeout=6.0)

        if response.status_code != 200:
            raise HTTPException(status_code=503, detail="سيرفر المحادثة مشغول حالياً.")

        response_json = response.json()
        ai_answer = response_json["choices"][0]["message"]["content"].strip()

        if not ai_answer:
            ai_answer = "سامحني يا صديقي، واجهت مشكلة صغيرة في تجميع الرد. ممكن تسألني تاني؟"

        return ChatResponse(answer=ai_answer)

    except (httpx.TimeoutException, asyncio.TimeoutError):
        logger.warning("تم تفعيل درع الحماية ضد الـ Vercel Timeout (الرد البديل السريع)")
        # رد بديل روحي سريع جداً يتم إرجاعه فوراً بدلاً من سقوط الاتصال بـ Failed to fetch
        return ChatResponse(
            answer="أهلاً بيك يا صديقي الغالي. أنا هنا وبسمعك وبفكر في كلامك بعمق.. "
                   "ساعات شبكة السيرفر عندي بتتقل شوية من كتر المحبة، بس أنا معاك. "
                   "ممكن تقولي إيه أكتر حاجة شاغلة بالك دلوقتي عشان نتكلم فيها بوضوح؟"
        )
    except Exception as e:
        logger.error(f"System Error: {e}")
        return ChatResponse(answer="سامحني يا صديقي، حصلت حاجة مش مظبوطة في السيرفر. جرب تبعتلي رسالتك تاني كده؟")
