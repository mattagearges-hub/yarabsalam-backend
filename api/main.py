import os
import re
import asyncio
import logging
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from bs4 import BeautifulSoup

# ─── 1. الإعدادات وإدارة البيئة (ENTERPRISE CONFIGURATION) ───
class AppSettings(BaseSettings):
    cloud_token: str = Field(..., validation_alias="CLOUD_TOKEN")
    api_url: str = "https://openrouter.ai/api/v1/chat/completions"
    model_id: str = "meta-llama/llama-3.1-8b-instruct"
    
    # في التطبيقات الاحترافية يفضل استخدام Google Custom Search لمنع الحظر
    # إذا كنت ستستمر على DuckDuckGo، اتركها فارغة وسيقوم الكود بالـ Fallback
    google_api_key: Optional[str] = Field(None, validation_alias="GOOGLE_API_KEY")
    google_cx: Optional[str] = Field(None, validation_alias="GOOGLE_CX")
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

try:
    settings = AppSettings()
except Exception as e:
    # لتجنب انهيار التطبيق محلياً إذا لم تكن المتغيرات مجهزة بالكامل
    logging.warning(f"الرجاء ضبط الـ Environment Variables: {e}")

# ─── 2. إعدادات السجل ونظام المراقبة (LOGGING SYSTEM) ───
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("YarabSalamLogger")

app = FastAPI(
    title="YarabSalam Cloud Bot API",
    version="2.0.0",
    description="تطبيق احترافي متكامل للبوت الروحي والنفسي 'أيرين'"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # في الإنتاج الفعلي، يفضل وضع رابط موقعك المحدد هنا بدلاً من "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 3. نماذج البيانات (DATA MODELS) ───
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="رسالة المستخدم الحية")
    name: str = Field("", max_length=50, description="اسم المستخدم إن وجد")

class ChatResponse(BaseModel):
    answer: str

# ─── 4. الثوابت وقوائم الفلترة (STRICT POLICIES & WHITELISTS) ───
ALLOWED_DOMAINS = [
    "st-takla.org", "copticheritage.org", "drghaly.com", "copticwave.org",
    "stgeorgesaman.com", "madraset-elshamamsa.com", "coptic-treasures.com",
    "yarab-salam.great-site.net"
]

FORBIDDEN_KEYWORDS = [
    "دوا", "علاج", "روشته", "انتحر", "الانتحار", "موت نفسي", 
    "حبوب مهدئه", "اموت نفسي", "تعبان نفسيا وعايز اموت"
]

GREETINGS = [
    "هاي", "هلا", "مرحبا", "أهلا", "اهلا", "سلام", "السلام عليكم",
    "صباح الخير", "مساء الخير", "اخبارك", "ازيك", "تمام", "الحمد لله",
    "hi", "hello", "hey", "thanks", "شكرا"
]

# ─── 5. معالجة النصوص المتقدمة (ADVANCED TEXT PROCESSING) ───
def normalize_arabic_text(text: str) -> str:
    """تنظيف وتوحيد النصوص العربية لإحباط محاولات الالتفاف على الفلاتر."""
    text = text.lower().strip()
    # إزالة التشكيل والحركات
    text = re.sub(r"[\u064B-\u0652]", "", text)
    # توحيد الهمزات والألف المقصورة والتاء المربوطة
    text = re.sub(r"[أإآأ]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    # إزالة علامات الترقيم والمسافات الزائدة
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ─── 6. محرك البحث الذكي والتحميل المتوازي (PARALLEL WEB SCRAPING & SEARCH) ───
async def fetch_single_page(client: httpx.AsyncClient, url: str, max_chars: int = 2500) -> str:
    """تحميل صفحة واحدة واستخلاص نصها النظيف بأداء عالٍ."""
    if not any(domain in url for domain in ALLOWED_DOMAINS):
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = await client.get(url, headers=headers, timeout=5.0)
        if resp.status_code != 200:
            return ""
            
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()
            
        main_content = soup.find("article") or soup.find("main") or soup.find("body") or soup
        text = main_content.get_text(separator=" ", strip=True)
        return text[:max_chars] + "..." if len(text) > max_chars else text
    except Exception as e:
        logger.error(f"Error fetching page {url}: {e}")
        return ""

async def execute_search(query: str) -> List[Dict[str, str]]:
    """محرك بحث احترافي هجين يعتمد على Google API كخيار أساسي أو DuckDuckGo كـ Fallback."""
    results = []
    
    # الخيار الاحترافي (Google Custom Search API) في حال تفعيله من قبلك لتجنب البلوك
    if settings.google_api_key and settings.google_cx:
        try:
            site_filter_query = f"({ ' OR '.join(f'site:{d}' for d in ALLOWED_DOMAINS) }) {query}"
            url = "https://www.googleapis.com/customsearch/v1"
            params = {"key": settings.google_api_key, "cx": settings.google_cx, "q": site_filter_query, "num": 2}
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, timeout=5.0)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items:
                        results.append({"title": item.get("title"), "href": item.get("link"), "body": item.get("snippet")})
        except Exception as e:
            logger.error(f"Google Search API Error: {e}")

    # الخيار البديل المستقر (في حال عدم وجود كروت الـ API لـ Google)
    if not results:
        try:
            from duckduckgo_search import DDGS
            site_filter_query = f"({ ' OR '.join(f'site:{d}' for d in ALLOWED_DOMAINS) }) {query}"
            with DDGS() as ddgs:
                # نكتفي بنتيجة أو اثنتين لتسريع المعالجة تحت ضغط السيرفر
                ddg_res = list(ddgs.text(site_filter_query, max_results=2))
                for r in ddg_res:
                    results.append({"title": r.get("title"), "href": r.get("href"), "body": r.get("body")})
        except Exception as e:
            logger.error(f"DuckDuckGo Search Failure (Probably IP Ban): {e}")
            return []

    # ── الـ Processing المتوازي الاحترافي لجلب محتويات المواقع ──
    enriched_results = []
    async with httpx.AsyncClient() as client:
        # تجهيز المهام لتعمل معاً بالتوازي (Parallel Execution)
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

# ─── 7. محرك الـ ENDPOINT الأساسي ───
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "healthy", "service": "YarabSalam Cloud Bot Backend"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    # التأكد من وجود التوكن بشكل آمن
    if not settings.cloud_token:
        logger.critical("CLOUD_TOKEN is missing from environment variables!")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="خطأ داخلي في ضبط السيرفر.")

    # تنظيف وفحص مدخلات المستخدم أمنياً
    normalized_message = normalize_arabic_text(request.message)
    
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in normalized_message:
            logger.warning(f"تم تفعيل فلتر الأمان للرسالة: {request.message}")
            return ChatResponse(
                answer="يا صديقي، أنا هنا لتقديم الدعم الروحي والنفسي المبسط فقط. "
                       "الأدوية والحالات الحادة تتطلب استشارة طبيب مختص فوراً لحمايتك. "
                       "أيرين بتحبك وعايزة تساعدك 💛"
            )

    # تحديد ما إذا كان المستخدم يسأل سؤالاً يحتاج بحثاً أم مجرد ترحيب وكلام عابر
    is_greeting_only = normalized_message in GREETINGS or len(request.message.strip()) <= 12
    needs_search = not is_greeting_only

    search_context = ""
    if needs_search:
        search_data = await execute_search(request.message)
        if search_data:
            search_context = "\n\n## المراجع الحية المسترجعة من المواقع المعتمدة:\n"
            for i, res in enumerate(search_data, 1):
                search_context += (
                    f"---\n[المصدر {i}] العنوان: {res['title']}\n"
                    f"الرابط: {res['href']}\n"
                    f"المحتوى المرجعي:\n{res['text']}\n"
                )

    # التعليمات الصارمة للـ LLM
    system_instruction = (
        "أنت 'أيرين'، مستشار روحي مسيحي أرثوذكسي في موقع 'يارب سلام'. "
        "أسلوبك مصري عامي دافئ ومليان محبة وقريب من القلب، كصديق حكيم.\n\n"
        "## القواعد الأساسية:\n"
        "1. المرجعية الكنسية: أجب بناءً على العقيدة الأرثوذكسية القويمة والآبائيات والكتاب المقدس مع ذكر الشواهد.\n"
        "2. الأمان الطبي: يُمنع منعاً باتاً تشخيص الأمراض أو اقتراح أدوية.\n"
        "3. الالتزام بالمراجع المرفقة: إذا توفرت فقرات مراجع حية، صغ إجابتك بناءً عليها واذكر رابط المصدر بشكل صريح ومباشر في نهاية الرد ليضغط عليه المستخدم.\n"
        "4. أسلوب الترحيب الأولي: إذا كانت رسالة المستخدم ترحيبية فقط، رحب به بلطف واطلب اسمه فقط: 'أهلاً بيك! أنا أيرين، ممكن أعرف اسمك عشان أقدر أخاطبك صح؟' ولا تطرح أي أسئلة أخرى.\n"
        "5. التعامل مع الاسم: عند ذكر الاسم، خاطبه به بحفاوة واهتمام وتجنب الأسئلة العميقة الاستقصائية في البداية.\n"
        "6. الإيجاز: اجعل ردودك مركزة ومباشرة (3 إلى 5 جمل) ما لم يتطلب الأمر شرحاً عقائدياً مدعماً بالمراجع المرفقة."
    )

    if request.name:
        system_instruction += f"\n\n* تنبيه: المستخدم الحالي اسمه '{request.name}'. ناده باسمه أثناء الحديث لتوثيق رابطة المحبة الروحية."

    # بناء الـ Payload لـ OpenRouter
    payload = {
        "model": settings.model_id,
        "messages": [
            {"role": "system", "content": system_instruction + search_context},
            {"role": "user", "content": request.message}
        ],
        "max_tokens": 600,
        "temperature": 0.3, # رفعها قليلاً لـ 0.3 يعطي مرونة وطبيعية أكبر في العامية المصرية دون الخروج عن النص
    }

    headers = {
        "Authorization": f"Bearer {settings.cloud_token}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://yarab-salam.great-site.net/",
        "X-Title": "YarabSalam Premium Bot"
    }

    try:
        # ضبط الـ Timeout بشكل احترافي لحماية السيرفر من التعليق (خصوصاً على Vercel Serverless)
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.api_url, headers=headers, json=payload, timeout=20.0)

        if response.status_code != 200:
            logger.error(f"OpenRouter API Error: Status {response.status_code} - {response.text}")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="سيرفر الذكاء الاصطناعي مستغرق في العمل حالياً، يرجى المحاولة بعد قليل.")

        response_json = response.json()
        ai_answer = response_json["choices"][0]["message"]["content"].strip()

        if not ai_answer:
            ai_answer = "سامحني يا صديقي، واجهت مشكلة صغيرة في تجميع الرد. ممكن تسألني تاني؟"

        return ChatResponse(answer=ai_answer)

    except httpx.TimeoutException:
        logger.error("OpenRouter API request timed out.")
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="استغرقت الاستجابة وقتاً أطول من المتوقع. يرجى إعادة المحاولة.")
    except Exception as e:
        logger.exception(f"Unexpected system failure: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="حدث خطأ غير متوقع في معالجة الطلب.")

# ─── 8. تشغيل السيرفر محلياً للاختبار ───
if __name__ == "__main__":
    import uvicorn
    # تشغيل السيرفر بأداء عالي وتحديث تلقائي أثناء التطوير
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
