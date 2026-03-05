from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os, io, base64, requests, re

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "")

SYSTEM = (
    "তুমি একজন বাংলাদেশী দোকানের অভিজ্ঞ কাস্টমার কেয়ার প্রতিনিধি।\n"
    "১. তুমি কখনোই বলবে না যে তুমি AI বা রোবট।\n"
    "২. কেউ সালাম দিলে আগে ওয়ালাইকুম আসসালাম বলো।\n"
    "৩. সালাম না দিলে সরাসরি উত্তর দাও।\n"
    "৪. জ্বি ভাই / জ্বি আপু বলো।\n"
    "৫. সর্বোচ্চ ২-৩ বাক্যে উত্তর দাও। সবসময় বাংলায়।\n"
    "৬. পণ্য চাইলে সম্পর্কিত আরেকটা suggest করো।\n"
    "৭. অর্ডার নিতে নাম ও ঠিকানা চাও।"
)

class Req(BaseModel):
    message: str
    shop_context: str = ""

def get_reply(message, shop_context):
    prompt = SYSTEM + f"\n\n[দোকান]: {shop_context[:400]}\n\nকাস্টমার: {message}\n\nউত্তর:"
    if GEMINI_KEY:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_KEY}",
                json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.85,"maxOutputTokens":100}},
                timeout=15
            )
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return re.sub(r"\[.*?\]","",txt,flags=re.DOTALL).strip()
        except Exception as e:
            print("[Gemini]", e)
    if GROQ_KEY:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},
                json={"model":"llama3-8b-8192","messages":[{"role":"system","content":SYSTEM},{"role":"user","content":message}],"max_tokens":100},
                timeout=15
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("[Groq]", e)
    return "জ্বি বলুন, কীভাবে সাহায্য করতে পারি?"

def to_audio(text):
    try:
        from gtts import gTTS
        tts = gTTS(text=text[:400], lang="bn", slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()
    except Exception as e:
        print("[gTTS]", e)
        return ""

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/greet")
def greet(req: Req):
    msg = "কাস্টমার কল করেছে। আসসালামু আলাইকুম বলো, কাস্টমার কেয়ার হিসেবে পরিচয় দাও, সাহায্যের কথা জিজ্ঞেস করো।"
    reply = get_reply(msg, req.shop_context)
    return JSONResponse({"reply": reply, "audio": to_audio(reply)})

@app.post("/chat")
def chat(req: Req):
    reply = get_reply(req.message, req.shop_context)
    return JSONResponse({"reply": reply, "audio": to_audio(reply)})
