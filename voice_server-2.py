from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
import os, io, base64, requests, re

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "")
SUPA_URL   = os.environ.get("SUPABASE_URL", "")
SUPA_KEY   = os.environ.get("SUPABASE_KEY", "")

SYSTEM = (
    "তুমি একজন বাংলাদেশী দোকানের অভিজ্ঞ কাস্টমার কেয়ার প্রতিনিধি।\n"
    "১. তুমি কখনো বলবে না যে তুমি AI বা রোবট।\n"
    "২. কেউ সালাম দিলে আগে ওয়ালাইকুম আসসালাম বলো।\n"
    "৩. সালাম না দিলে সরাসরি উত্তর দাও।\n"
    "৪. জ্বি ভাই / জ্বি আপু বলো।\n"
    "৫. সর্বোচ্চ ২-৩ বাক্যে উত্তর দাও। সবসময় বাংলায়।\n"
    "৬. পণ্য চাইলে সম্পর্কিত আরেকটা suggest করো।\n"
    "৭. অর্ডার নিতে নাম ও ঠিকানা চাও।"
)

def get_shop_info(shop_phone):
    biz_name = "কাস্টমার কেয়ার"
    shop_ctx = ""
    if SUPA_URL and SUPA_KEY and shop_phone:
        try:
            h = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"}
            r = requests.get(
                f"{SUPA_URL}/rest/v1/merchant_data?merchant_phone=eq.{shop_phone}&select=rules,inventory,profile",
                headers=h, timeout=8)
            if r.status_code == 200 and r.json():
                d = r.json()[0]
                profile = d.get("profile") or {}
                biz_name = profile.get("company_name", "") or biz_name
                rules = d.get("rules", "") or ""
                inv = d.get("inventory", []) or []
                prods = " | ".join([
                    p.get("name", "") + ": " + p.get("desc", "")
                    for p in inv[:10]
                ])
                shop_ctx = f"দোকান: {biz_name}. নিয়ম: {rules[:150]}. পণ্য: {prods}"
        except Exception as e:
            print("[Supabase]", e)
    return biz_name, shop_ctx

def get_reply(message, shop_context):
    prompt = SYSTEM + f"\n\n[দোকান]: {shop_context[:400]}\n\nকাস্টমার: {message}\n\nউত্তর:"
    if GEMINI_KEY:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.85, "maxOutputTokens": 100}},
                timeout=15)
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return re.sub(r"\[.*?\]", "", txt, flags=re.DOTALL).strip()
        except Exception as e:
            print("[Gemini]", e)
    if GROQ_KEY:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={"model": "llama3-8b-8192",
                      "messages": [{"role": "system", "content": SYSTEM},
                                   {"role": "user", "content": message}],
                      "max_tokens": 100},
                timeout=15)
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

class Req(BaseModel):
    message: str
    shop_context: str = ""

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/chat")
def chat(req: Req):
    reply = get_reply(req.message, req.shop_context)
    return JSONResponse({"reply": reply, "audio": to_audio(reply)})

@app.post("/greet")
def greet(req: Req):
    msg = "কাস্টমার কল করেছে। আসসালামু আলাইকুম বলো, কাস্টমার কেয়ার হিসেবে পরিচয় দাও, কীভাবে সাহায্য করতে পারো জিজ্ঞেস করো।"
    reply = get_reply(msg, req.shop_context)
    return JSONResponse({"reply": reply, "audio": to_audio(reply)})

@app.get("/call")
def call_page(shop: str = ""):
    biz_name, shop_ctx = get_shop_info(shop)
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://global-ai-shop.onrender.com")
    vapi = base_url.rstrip("/") + ":8000"

    biz_js = biz_name.replace("`", "'").replace("$", "").replace("\n", " ")
    ctx_js = shop_ctx.replace("`", "'").replace("$", "").replace("\n", " ").replace('"', "'")

    biz_js  = biz_name.replace("`","'").replace("$","").replace("\n"," ").replace('"',"'")
    ctx_js  = shop_ctx.replace("`","'").replace("$","").replace("\n"," ").replace('"',"'")

    html = (
        "<!DOCTYPE html>"
        "<html lang='bn'>"
        "<head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no'>"
        f"<title>{biz_js}</title>"
        "<link href='https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;700&display=swap' rel='stylesheet'>"
        "<style>"
        "*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent;}"
        "html,body{min-height:100vh;background:#010409;font-family:'Noto Sans Bengali',sans-serif;}"
        "body{display:flex;align-items:center;justify-content:center;padding:20px;"
        "background-image:radial-gradient(ellipse 70% 50% at 50% 0%,rgba(37,211,102,.09) 0%,transparent 60%);}"
        ".card{background:linear-gradient(180deg,#0d1117,#161b22);border-radius:24px;"
        "padding:32px 22px 28px;width:100%;max-width:340px;"
        "box-shadow:0 8px 40px rgba(0,0,0,.85);border:1px solid rgba(255,255,255,.07);"
        "display:flex;flex-direction:column;align-items:center;}"
        ".shop{color:rgba(255,255,255,.25);font-size:.65rem;letter-spacing:3px;"
        "text-transform:uppercase;margin-bottom:20px;text-align:center;}"
        ".av{width:90px;height:90px;border-radius:50%;"
        "background:linear-gradient(135deg,#25d366,#075e35);"
        "display:flex;align-items:center;justify-content:center;font-size:2.8rem;margin-bottom:14px;}"
        ".av.ring{animation:rp 1.1s ease infinite;}"
        ".av.live{box-shadow:0 0 0 6px rgba(37,211,102,.3);animation:none;}"
        "@keyframes rp{0%,100%{box-shadow:0 0 0 0 rgba(37,211,102,.8);}70%{box-shadow:0 0 0 28px rgba(37,211,102,0);}}"
        ".nm{color:#fff;font-size:1.2rem;font-weight:700;margin-bottom:6px;}"
        ".live-badge{display:none;background:rgba(37,211,102,.15);border:1px solid rgba(37,211,102,.4);"
        "color:#25d366;font-size:.7rem;font-weight:700;letter-spacing:2px;"
        "padding:4px 14px;border-radius:20px;margin-bottom:10px;}"
        ".st{font-size:.76rem;color:rgba(255,255,255,.4);margin-bottom:16px;"
        "text-align:center;min-height:20px;line-height:1.5;transition:color .3s;}"
        ".st.g{color:#25d366;}"
        ".tmr{color:rgba(255,255,255,.25);font-size:.74rem;margin-bottom:12px;"
        "font-variant-numeric:tabular-nums;display:none;letter-spacing:2px;}"
        ".pulse{display:none;gap:5px;margin-bottom:14px;align-items:center;}"
        ".pulse span{width:6px;height:6px;border-radius:50%;background:#25d366;"
        "animation:pl .65s ease infinite alternate;}"
        ".pulse span:nth-child(2){animation-delay:.2s;}.pulse span:nth-child(3){animation-delay:.4s;}"
        "@keyframes pl{from{opacity:.15;transform:scale(.5);}to{opacity:1;transform:scale(1.5);}}"
        ".ltxt{color:#25d366;font-size:.72rem;display:none;margin-bottom:10px;"
        "animation:bk .9s infinite alternate;text-align:center;}"
        "@keyframes bk{from{opacity:.3;}to{opacity:1;}}"
        ".bcall{width:72px;height:72px;border-radius:50%;background:#25d366;border:none;"
        "cursor:pointer;display:flex;align-items:center;justify-content:center;"
        "box-shadow:0 6px 24px rgba(37,211,102,.55);animation:pg 1.8s ease infinite;}"
        "@keyframes pg{0%,100%{box-shadow:0 0 0 0 rgba(37,211,102,.6);}70%{box-shadow:0 0 0 22px rgba(37,211,102,0);}}"
        ".bcall:active{transform:scale(.93);}"
        ".bend{width:72px;height:72px;border-radius:50%;background:#ff3b30;border:none;"
        "cursor:pointer;display:none;align-items:center;justify-content:center;"
        "box-shadow:0 6px 22px rgba(255,59,48,.5);}"
        ".bend:active{transform:scale(.93);}"
        "svg{width:28px;height:28px;fill:white;pointer-events:none;}"
        ".lbl{color:rgba(255,255,255,.2);font-size:.66rem;margin-top:8px;}"
        ".err{color:#ff8080;font-size:.72rem;margin-top:10px;text-align:center;"
        "display:none;padding:8px 12px;background:rgba(255,59,48,.1);"
        "border-radius:8px;width:100%;line-height:1.5;}"
        "</style>"
        "</head>"
        "<body>"
        "<div class='card'>"
        f"<div class='shop'>{biz_js}</div>"
        "<div class='av' id='av'>🏪</div>"
        "<div class='nm'>কাস্টমার কেয়ার</div>"
        "<div class='live-badge' id='livebadge'>● লাইভ সংযুক্ত</div>"
        "<div class='st' id='st'>কল করতে নিচের সবুজ বাটন চাপুন</div>"
        "<div class='tmr' id='tmr'>00:00</div>"
        "<div class='pulse' id='pulse'><span></span><span></span><span></span></div>"
        "<div class='ltxt' id='ltxt'>🎤 বলুন...</div>"
        "<button class='bcall' id='bcall' onclick='startCall()'>"
        "<svg viewBox='0 0 24 24'><path d='M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1-9.4 0-17-7.6-17-17 0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1L6.6 10.8z'/></svg>"
        "</button>"
        "<button class='bend' id='bend' onclick='endCall()'>"
        "<svg viewBox='0 0 24 24'><path d='M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.12-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z'/></svg>"
        "</button>"
        "<div class='lbl' id='lbl'>📞 কল করুন</div>"
        "<div class='err' id='err'></div>"
        "</div>"
        "<script>"
        f"var VAPI='{vapi}';"
        f"var CTX='{ctx_js}';"
        "var active=false,rec=null,sec=0,tid=null,busy=false,audioCtx=null,ringTmr=null;"
        "function $(i){return document.getElementById(i);}"
        "function setSt(t,g){$('st').textContent=t;$('st').className='st'+(g?' g':'');}"
        "function showP(v){$('pulse').style.display=v?'flex':'none';}"
        "function showL(v){$('ltxt').style.display=v?'block':'none';}"
        "function showErr(t){var e=$('err');if(t){e.textContent=t;e.style.display='block';}else e.style.display='none';}"
        "function getAC(){if(!audioCtx)audioCtx=new(window.AudioContext||window.webkitAudioContext)();if(audioCtx.state==='suspended')audioCtx.resume();return audioCtx;}"
        "function playRing(){var c=getAC();"
        "function tone(f,s,d){var o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);o.type='sine';o.frequency.value=f;var t=c.currentTime+s;g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.12,t+.06);g.gain.setValueAtTime(.12,t+d-.06);g.gain.linearRampToValueAtTime(0,t+d);o.start(t);o.stop(t+d+.1);}"
        "function ring(){tone(440,0,.45);tone(480,.05,.45);tone(440,.72,.45);tone(480,.77,.45);}ring();ringTmr=setInterval(ring,2800);}"
        "function stopRing(){if(ringTmr){clearInterval(ringTmr);ringTmr=null;}}"
        "function playB64(b64){try{var c=getAC(),bin=atob(b64),buf=new ArrayBuffer(bin.length),v=new Uint8Array(buf);for(var i=0;i<bin.length;i++)v[i]=bin.charCodeAt(i);c.decodeAudioData(buf,function(dec){var s=c.createBufferSource();s.buffer=dec;s.connect(c.destination);s.onended=function(){busy=false;showP(false);if(active){setSt('বলুন...',true);showL(true);startListen();}};s.start(0);},function(){busy=false;if(active)startListen();});}catch(e){busy=false;if(active)startListen();}}"
        "function speakFallback(text){if(!window.speechSynthesis){busy=false;if(active)startListen();return;}window.speechSynthesis.cancel();var u=new SpeechSynthesisUtterance(text||'জ্বি বলুন।');u.lang='bn-IN';u.rate=0.9;u.volume=1;var vs=window.speechSynthesis.getVoices();var bn=vs.find(function(v){return v.lang&&(v.lang.startsWith('bn')||v.lang.startsWith('hi'));});if(bn)u.voice=bn;u.onend=function(){busy=false;showP(false);if(active){setSt('বলুন...',true);showL(true);startListen();}};u.onerror=function(){busy=false;if(active)startListen();};window.speechSynthesis.speak(u);}"
        "function speak(data){busy=true;showP(true);showL(false);setSt('বলছে...',true);if(data.audio&&data.audio.length>100){playB64(data.audio);}else{speakFallback(data.reply||'জ্বি বলুন।');}}"
        "async function apiCall(ep,msg){try{var r=await fetch(VAPI+'/'+ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,shop_context:CTX})});return await r.json();}catch(e){return{reply:'জ্বি বলুন।',audio:'';};}}"
        "function startListen(){if(!active||busy)return;var SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){setSt('Chrome এ খুলুন',false);showErr('Chrome browser ব্যবহার করুন');return;}try{if(rec){try{rec.abort();}catch(e){}}rec=new SR();rec.lang='bn-IN';rec.continuous=false;rec.interimResults=true;rec.maxAlternatives=1;rec.onstart=function(){setSt('বলুন...',true);showL(true);showErr('');};rec.onresult=function(e){var txt='',fin=false;for(var i=e.resultIndex;i<e.results.length;i++){if(e.results[i].isFinal){txt+=e.results[i][0].transcript;fin=true;}else setSt('শুনছি: '+e.results[i][0].transcript,true);}if(fin&&txt.trim()){showL(false);setSt('বুঝছি...',false);if(rec){try{rec.abort();}catch(ex){}}apiCall('chat',txt.trim()).then(speak);}};rec.onend=function(){showL(false);if(active&&!busy)setTimeout(startListen,500);};rec.onerror=function(ev){showL(false);if(ev.error==='not-allowed'){showErr('মাইক Allow করুন → address bar এ 🔒 ক্লিক করুন');active=false;endCall();return;}if(active&&!busy)setTimeout(startListen,1000);};rec.start();}catch(e){if(active&&!busy)setTimeout(startListen,1500);}}"
        "function startCall(){getAC();showErr('');$('bcall').style.display='none';$('av').className='av ring';setSt('রিং হচ্ছে...',false);$('lbl').textContent='সংযুক্ত হচ্ছে...';playRing();"
        "setTimeout(function(){stopRing();active=true;$('av').className='av live';$('livebadge').style.display='block';$('bend').style.display='flex';$('tmr').style.display='block';$('lbl').textContent='📵 কাটুন';setSt('সংযুক্ত',true);"
        "tid=setInterval(function(){sec++;var m=String(Math.floor(sec/60)).padStart(2,'0'),s=String(sec%60).padStart(2,'0');$('tmr').textContent=m+':'+s;},1000);"
        "apiCall('greet','').then(speak);},2000);}"
        "function endCall(){active=false;busy=false;stopRing();if(tid){clearInterval(tid);tid=null;}if(rec){try{rec.abort();}catch(e){}}if(window.speechSynthesis)window.speechSynthesis.cancel();$('av').className='av';$('livebadge').style.display='none';$('bend').style.display='none';$('bcall').style.display='flex';$('tmr').style.display='none';showP(false);showL(false);setSt('কল শেষ। আবার করতে পারেন।',false);$('lbl').textContent='📞 আবার কল করুন';sec=0;}"
        "if(window.speechSynthesis){window.speechSynthesis.getVoices();window.speechSynthesis.onvoiceschanged=function(){};}"
        "</script>"
        "</body></html>"
    )

    return HTMLResponse(content=html)
