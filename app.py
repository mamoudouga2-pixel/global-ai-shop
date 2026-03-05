import streamlit as st
from supabase import create_client, Client
import hashlib
import pandas as pd
import datetime
import plotly.express as px
import plotly.graph_objects as go
import os
import time
from PIL import Image

# ══════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="GLOBAL AI | PRO",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ══════════════════════════════════════════════════════════
# API KEYS
# ══════════════════════════════════════════════════════════
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY        = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_API_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
LIVEKIT_URL         = os.environ.get("LIVEKIT_URL", "")
LIVEKIT_API_KEY     = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_SECRET      = os.environ.get("LIVEKIT_API_SECRET", "")

# ══════════════════════════════════════════════════════════
# SUPABASE
# ══════════════════════════════════════════════════════════
supabase = None
try:
    _url = os.environ.get("SUPABASE_URL","").strip()
    _key = os.environ.get("SUPABASE_KEY","").strip()
    if not _url:
        try:
            _url = st.secrets.get("SUPABASE_URL","").strip()
            _key = st.secrets.get("SUPABASE_KEY","").strip()
        except: pass
    if _url.startswith("https://") and _key:
        supabase: Client = create_client(_url, _key)
except Exception as e:
    print("[Supabase]", e)

DATA_DIR = "user_memory"
os.makedirs(DATA_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════
# MODULE IMPORTS
# ══════════════════════════════════════════════════════════
try:
    from database import get_or_create_user, extend_subscription, save_order, get_all_orders
    from logic import VOUCHERS, get_ai_response, analyze_fake_order, extract_customer_info
    files_missing = False
except ImportError:
    files_missing = True
    def get_or_create_user(phone): return (phone, "My Business", "", "2030-12-31", "TRIAL")
    def extend_subscription(phone, days): pass
    def get_all_orders(phone): return pd.DataFrame()
    VOUCHERS = {"FUTURE2040": 30, "BANGLADESH_AI": 365, "TRIAL_BOSS": 7}
    def get_ai_response(msg, tone, key, ctx): return f"[DATA: Demo] {msg}"
    def analyze_fake_order(u, a): return "POTENTIAL_ORDER (50%)", "🟨"
    def extract_customer_info(t): return {}

import requests as _req, base64 as _b64, io as _io

_SALES_PROMPT = (
    "তুমি একজন বাংলাদেশী দোকানের অভিজ্ঞ কাস্টমার কেয়ার প্রতিনিধি।\n"
    "১. তুমি কখনো বলবে না যে তুমি AI বা রোবট।\n"
    "২. কেউ সালাম দিলে আগে উত্তর দাও: ওয়ালাইকুম আসসালাম।\n"
    "৩. জ্বি ভাই, জ্বি আপু, জ্বি স্যার — বিনয়ের সাথে কথা বলো।\n"
    "৪. সর্বোচ্চ ৩ বাক্যে উত্তর দাও। সবসময় বাংলায় কথা বলো।\n"
    "৫. কাস্টমার একটা পণ্য চাইলে আরেকটা suggest করো।\n"
    "৬. অর্ডার নিতে নাম ও ঠিকানা চাও।"
)

def get_ai_sales_response(user_message, shop_context=""):
    import re
    gkey = os.environ.get("GEMINI_API_KEY","")
    grkey = os.environ.get("GROQ_API_KEY","")
    prompt = _SALES_PROMPT + "\n\n[দোকান]: " + shop_context[:300] + "\n\nকাস্টমার: " + user_message + "\n\nউত্তর:"
    if gkey:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key=" + gkey
            r = _req.post(url, json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.9,"maxOutputTokens":120}}, timeout=15)
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return re.sub(r"\[EXTRACTED_DATA:.*?\]","",txt,flags=re.DOTALL).strip()
        except: pass
    if grkey:
        try:
            r = _req.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":"Bearer "+grkey,"Content-Type":"application/json"},
                json={"model":"llama3-8b-8192","messages":[{"role":"system","content":_SALES_PROMPT},{"role":"user","content":shop_context[:200]+"\nকাস্টমার: "+user_message}],"max_tokens":120},
                timeout=15)
            if r.status_code == 200: return r.json()["choices"][0]["message"]["content"].strip()
        except: pass
    return "জ্বি বলুন, কীভাবে সাহায্য করতে পারি?"

def text_to_audio_b64(text):
    if not text: return ""
    try:
        from gtts import gTTS
        tts = gTTS(text=text[:400], lang="bn", slow=False)
        buf = _io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return _b64.b64encode(buf.read()).decode("utf-8")
    except: return ""

def whatsapp_call_ui(shop_phone="", shop_context=""):
    import streamlit.components.v1 as _cv1

    for k,v in [("call_active",False),("call_greeted",False),("audio_b64",""),("audio_id",0)]:
        if k not in st.session_state: st.session_state[k]=v

    # voice query param
    qp = st.query_params
    vr = qp.get("vr","").strip()
    if vr:
        try: del st.query_params["vr"]
        except: pass
        reply = get_ai_sales_response(vr, shop_context)
        st.session_state.audio_b64 = text_to_audio_b64(reply)
        st.session_state.audio_id += 1
        st.rerun()

    # greeting
    if st.session_state.call_active and not st.session_state.call_greeted:
        with st.spinner("সংযুক্ত হচ্ছে..."):
            greet = get_ai_sales_response("আসসালামু আলাইকুম বলো তারপর কাস্টমার কেয়ার হিসেবে পরিচয় দাও এবং সাহায্যের কথা জিজ্ঞেস করো।", shop_context)
            st.session_state.audio_b64 = text_to_audio_b64(greet)
            st.session_state.audio_id += 1
            st.session_state.call_greeted = True

    is_active = st.session_state.call_active
    audio_b64 = st.session_state.audio_b64
    audio_id  = str(st.session_state.audio_id)
    gkey      = os.environ.get("GEMINI_API_KEY","")

    CALL_SVG = '<svg viewBox="0 0 24 24" width="28" height="28" fill="white"><path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1-9.4 0-17-7.6-17-17 0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1L6.6 10.8z"/></svg>'
    END_SVG  = '<svg viewBox="0 0 24 24" width="28" height="28" fill="white"><path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.12-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z"/></svg>'

    audio_play = ""
    if is_active and audio_b64:
        audio_play = f"""<script>
(function(){{var k="a{audio_id}";if(sessionStorage.getItem(k))return;sessionStorage.setItem(k,"1");
try{{var b=atob("{audio_b64}"),buf=new ArrayBuffer(b.length),v=new Uint8Array(buf);
for(var i=0;i<b.length;i++)v[i]=b.charCodeAt(i);
var ctx=new(window.AudioContext||window.webkitAudioContext)();
ctx.decodeAudioData(buf,function(d){{var s=ctx.createBufferSource();s.buffer=d;s.connect(ctx.destination);s.onended=startListen;s.start(0);}},startListen);
}}catch(e){{startListen();}}}})();
</script>"""

    status_html = "<div class=\'st\'>কল করতে নিচের বাটন চাপুন</div>" if not is_active else "<div class=\'st\'><span class=\'dot\'></span> সংযুক্ত</div><div class=\'tmr\' id=\'tmr\'>00:00</div><div class=\'pls\'><span></span><span></span><span></span></div>"
    btn_html = f'<button class="bcall" id="bc" onclick="doCall()">{CALL_SVG}</button>' if not is_active else f'<button class="bend" onclick="doEnd()">{END_SVG}</button>'
    av_cls = "av ring" if not is_active else "av live"

    sys_ctx = (_SALES_PROMPT + "\n[দোকান]: " + shop_context[:300]).replace("`","'").replace("\\","\\\\")

    html = f"""<!DOCTYPE html><html lang="bn"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;700&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Noto Sans Bengali",sans-serif;background:transparent;display:flex;justify-content:center;padding:10px 0;}}
.wrap{{display:flex;flex-direction:column;align-items:center;background:linear-gradient(180deg,#0d1117,#161b22);border-radius:26px;padding:30px 22px 24px;width:100%;max-width:330px;box-shadow:0 8px 40px rgba(0,0,0,.7);border:1px solid rgba(255,255,255,.07);}}
.av{{width:88px;height:88px;border-radius:50%;background:linear-gradient(135deg,#25d366,#075e35);display:flex;align-items:center;justify-content:center;font-size:2.7rem;margin-bottom:12px;}}
.av.ring{{animation:rp 1.2s ease infinite;}}
.av.live{{box-shadow:0 0 0 4px rgba(37,211,102,.35);}}
@keyframes rp{{0%,100%{{box-shadow:0 0 0 0 rgba(37,211,102,.8);}}70%{{box-shadow:0 0 0 22px rgba(37,211,102,0);}}}}
.nm{{color:#fff;font-size:1.25rem;font-weight:700;margin-bottom:4px;}}
.st{{color:rgba(255,255,255,.4);font-size:.78rem;margin-bottom:16px;display:flex;align-items:center;gap:5px;}}
.dot{{width:7px;height:7px;border-radius:50%;background:#25d366;animation:bk .9s infinite alternate;}}
@keyframes bk{{from{{opacity:.2;}}to{{opacity:1;}}}}
.tmr{{color:rgba(255,255,255,.3);font-size:.78rem;margin-bottom:12px;font-variant-numeric:tabular-nums;}}
.pls{{display:flex;gap:5px;margin-bottom:14px;}}.pls span{{width:6px;height:6px;border-radius:50%;background:#25d366;animation:pl .7s ease infinite alternate;}}
.pls span:nth-child(2){{animation-delay:.2s;}}.pls span:nth-child(3){{animation-delay:.4s;}}
@keyframes pl{{from{{opacity:.15;transform:scale(.5);}}to{{opacity:1;transform:scale(1.5);}}}}
.bcall{{width:68px;height:68px;border-radius:50%;background:#25d366;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 20px rgba(37,211,102,.6);animation:pg 1.7s ease infinite;}}
@keyframes pg{{0%,100%{{box-shadow:0 0 0 0 rgba(37,211,102,.6);}}70%{{box-shadow:0 0 0 16px rgba(37,211,102,0);}}}}
.bend{{width:68px;height:68px;border-radius:50%;background:#ff3b30;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 18px rgba(255,59,48,.5);}}
</style></head><body>
<div class="wrap">
  <div class="{av_cls}">🏪</div>
  <div class="nm">কাস্টমার কেয়ার</div>
  {status_html}
  {btn_html}
</div>
<script>
var IS={str(is_active).lower()};
var GKEY="{gkey}";
var SYS=`{sys_ctx}`;
var rec=null,sec=0,tid=null,spk=false,hist=[];
function nav(u){{try{{window.top.location.href=u;}}catch(e){{window.location.href=u;}}}}
function base(){{try{{return window.top.location.href.split("?")[0];}}catch(e){{return window.location.href.split("?")[0];}}}}
function doCall(){{
  var b=document.getElementById("bc");if(b){{b.disabled=true;b.style.opacity=".5";}}
  try{{
    var ctx=new(window.AudioContext||window.webkitAudioContext)();
    function t(f,s,d){{var o=ctx.createOscillator(),g=ctx.createGain();o.connect(g);g.connect(ctx.destination);o.type="sine";o.frequency.value=f;var c=ctx.currentTime+s;g.gain.setValueAtTime(0,c);g.gain.linearRampToValueAtTime(.12,c+.05);g.gain.setValueAtTime(.12,c+d-.05);g.gain.linearRampToValueAtTime(0,c+d);o.start(c);o.stop(c+d+.1);}}
    function rng(){{t(440,0,.4);t(480,.05,.4);t(440,.65,.4);t(480,.7,.4);}}
    rng();window._rt=setInterval(function(){{var c2=new(window.AudioContext||window.webkitAudioContext)();function t2(f,s,d){{var o=c2.createOscillator(),g=c2.createGain();o.connect(g);g.connect(c2.destination);o.type="sine";o.frequency.value=f;var c=c2.currentTime+s;g.gain.setValueAtTime(0,c);g.gain.linearRampToValueAtTime(.12,c+.05);g.gain.setValueAtTime(.12,c+d-.05);g.gain.linearRampToValueAtTime(0,c+d);o.start(c);o.stop(c+d+.1);}}t2(440,0,.4);t2(480,.05,.4);t2(440,.65,.4);t2(480,.7,.4);}},2800);
  }}catch(e){{}}
  setTimeout(function(){{
    if(window._rt){{clearInterval(window._rt);window._rt=null;}}
    nav(base()+"?call=1");
  }},15000+Math.random()*7000);
}}
function doEnd(){{
  if(rec){{try{{rec.abort();}}catch(e){{}}}}
  if(tid){{clearInterval(tid);}}
  nav(base()+"?call=0");
}}
function sendV(t){{if(rec){{try{{rec.abort();}}catch(e){{}}}}nav(base()+"?vr="+encodeURIComponent(t));}}
function startListen(){{
  if(!IS||spk)return;
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR)return;
  try{{
    rec=new SR();rec.lang="bn-BD";rec.interimResults=false;rec.continuous=false;
    rec.onresult=function(e){{var t="";for(var i=e.resultIndex;i<e.results.length;i++)if(e.results[i].isFinal)t+=e.results[i][0].transcript;if(t.trim())sendV(t.trim());}};
    rec.onend=function(){{if(IS&&!spk)setTimeout(startListen,1000);}};
    rec.onerror=function(ev){{if(ev.error!=="aborted"&&ev.error!=="no-speech")setTimeout(startListen,1500);}};
    rec.start();
  }}catch(e){{setTimeout(startListen,1500);}}
}}
if(IS){{tid=setInterval(function(){{sec++;var m=String(Math.floor(sec/60)).padStart(2,"0"),s=String(sec%60).padStart(2,"0");var e=document.getElementById("tmr");if(e)e.textContent=m+":"+s;}},1000);}}
</script>
{audio_play}
</body></html>"""

    _cv1.html(html, height=340, scrolling=False)

    qp2 = st.query_params
    cp = qp2.get("call","")
    if cp=="1" and not st.session_state.call_active:
        try: del st.query_params["call"]
        except: pass
        st.session_state.call_active=True; st.session_state.call_greeted=False; st.session_state.audio_b64=""; st.rerun()
    elif cp=="0":
        try: del st.query_params["call"]
        except: pass
        st.session_state.call_active=False; st.session_state.call_greeted=False; st.session_state.audio_b64=""; st.rerun()

# ══════════════════════════════════════════════════════════
# AUTH HELPERS
# ══════════════════════════════════════════════════════════
def hash_pass(p): return hashlib.sha256(str(p).encode()).hexdigest()

def register_user_db(phone, email, password):
    if supabase is None: return "ERROR: ডাটাবেস নেই"
    try:
        c = supabase.table("merchants").select("phone").eq("phone", phone).execute()
        if c.data: return "EXISTS"
        expiry = (datetime.date.today() + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        supabase.table("merchants").insert({
            "phone": phone, "email": email, "pin": hash_pass(password), "expiry_date": expiry, "status": "TRIAL"
        }).execute()
        supabase.table("merchant_data").insert({
            "merchant_phone": phone, "rules": "দোকানের নিয়ম এখানে লিখুন...", "inventory": []
        }).execute()
        return "SUCCESS"
    except Exception as e:
        return f"ERROR: {e}"

def verify_login_db(identifier, password):
    """phone বা email দিয়ে লগইন"""
    if supabase is None: return False
    try:
        res = supabase.table("merchants").select("pin").eq("phone", identifier).execute()
        if not res.data:
            res = supabase.table("merchants").select("pin").eq("email", identifier).execute()
        if res.data and res.data[0]['pin'] == hash_pass(password): return True
    except Exception as e:
        print(f"Login Error: {e}")
    return False

def get_phone_from_identifier(identifier):
    if supabase is None: return identifier
    try:
        res = supabase.table("merchants").select("phone").eq("phone", identifier).execute()
        if res.data: return res.data[0]['phone']
        res = supabase.table("merchants").select("phone").eq("email", identifier).execute()
        if res.data: return res.data[0]['phone']
    except: pass
    return identifier

# ══════════════════════════════════════════════════════════
# MEMORY & INVENTORY
# ══════════════════════════════════════════════════════════
def save_user_memory(phone, text):
    if supabase:
        try: supabase.table("merchant_data").update({"rules": text}).eq("merchant_phone", phone).execute()
        except Exception as e: st.error(f"সেভ এরর: {e}")

def load_user_memory(phone):
    if supabase:
        try:
            res = supabase.table("merchant_data").select("rules").eq("merchant_phone", phone).execute()
            if res.data: return res.data[0].get("rules", "")
        except: pass
    return ""

def save_inventory(phone, products):
    if supabase:
        try: supabase.table("merchant_data").update({"inventory": products}).eq("merchant_phone", phone).execute()
        except Exception as e: st.error(f"ইনভেন্টরি সেভ এরর: {e}")

def load_inventory(phone):
    if supabase:
        try:
            res = supabase.table("merchant_data").select("inventory").eq("merchant_phone", phone).execute()
            if res.data: return res.data[0].get("inventory", [])
        except: pass
    return []

def get_full_ai_context(phone):
    info = load_user_memory(phone)
    products = load_inventory(phone)
    ctx = f"[দোকানের নিয়ম]: {info}\n\n[পণ্যসমূহ]:\n"
    for p in products:
        ctx += f"- {p.get('name','')}: {p.get('desc','')}\n"
    return ctx

# ══════════════════════════════════════════════════════════
# SHORT LINK HELPER
# ══════════════════════════════════════════════════════════
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://global-ai-shop.onrender.com")

def get_short_link(phone):
    return f"{BASE_URL}?shop={phone}"

# ══════════════════════════════════════════════════════════
# PREMIUM CSS — Apple × Microsoft Fluent × Obsidian
# ══════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');

/* ── BASE ── */
#MainMenu,footer,header{visibility:hidden}
.block-container{padding-top:0 !important;padding-bottom:2rem !important;max-width:1400px}

/* ── BACKGROUND ── */
.stApp{
  background:#020710;
  background-image:
    radial-gradient(ellipse 70% 50% at 5% 0%,   rgba(0,160,255,0.12) 0%,transparent 55%),
    radial-gradient(ellipse 50% 40% at 95% 100%, rgba(120,0,255,0.10) 0%,transparent 55%),
    radial-gradient(ellipse 35% 25% at 50% 50%,  rgba(0,255,150,0.04) 0%,transparent 65%);
  color:#dde6f5;
  font-family:'Plus Jakarta Sans',sans-serif;
}
.stApp::after{
  content:'';position:fixed;inset:0;
  background:url("data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='g'%3E%3CfeTurbulence baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23g)' opacity='0.03'/%3E%3C/svg%3E");
  pointer-events:none;z-index:0;
}

/* ── TYPOGRAPHY ── */
h1,h2,h3,h4{font-family:'Syne',sans-serif !important}

/* ── GLOBAL HEADER ── */
.page-header{
  padding:2.5rem 0 0.5rem;
  text-align:center;
}
.page-header h1{
  font-family:'Syne',sans-serif;
  font-size:clamp(2.2rem,5vw,4rem);
  font-weight:800;
  background:linear-gradient(135deg,#38d9ff 0%,#2563ff 45%,#a855f7 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  letter-spacing:-2px;line-height:1.05;margin:0;
}
.page-header p{
  font-size:0.78rem;color:rgba(160,200,255,0.45);
  letter-spacing:5px;text-transform:uppercase;margin-top:0.5rem;font-weight:500;
}

/* ── GLASS CARD ── */
.g-card{
  background:rgba(10,18,36,0.6);
  backdrop-filter:blur(32px) saturate(200%);
  -webkit-backdrop-filter:blur(32px) saturate(200%);
  border-radius:22px;
  border:1px solid rgba(255,255,255,0.065);
  box-shadow:0 24px 64px rgba(0,0,0,0.55),inset 0 1px 0 rgba(255,255,255,0.08);
  padding:28px 30px;
  margin-bottom:18px;
  transition:border-color .4s,box-shadow .4s;
}
.g-card:hover{
  border-color:rgba(56,217,255,0.16);
  box-shadow:0 28px 72px rgba(0,0,0,0.6),0 0 48px rgba(0,160,255,0.06),inset 0 1px 0 rgba(255,255,255,0.1);
}

/* ── KPI CARD ── */
.kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:4px}
.kpi{
  background:rgba(0,160,255,0.06);
  border:1px solid rgba(0,160,255,0.14);
  border-radius:16px;padding:18px 20px;text-align:center;
}
.kpi-val{
  font-family:'Syne',sans-serif;font-size:1.9rem;font-weight:800;
  background:linear-gradient(135deg,#38d9ff,#2563ff);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.kpi-lbl{font-size:0.72rem;color:rgba(140,190,255,0.55);text-transform:uppercase;letter-spacing:1.8px;margin-top:3px;}

/* ── SECTION HEADING ── */
.sec-head{
  font-family:'Syne',sans-serif;font-size:1.05rem;font-weight:700;
  display:flex;align-items:center;gap:8px;margin-bottom:1rem;
}

/* ── TABS ── */
.stTabs [data-baseweb="tab-list"]{
  background:rgba(6,12,26,0.7);border-radius:16px;padding:5px;gap:3px;
  border:1px solid rgba(255,255,255,0.055);margin-bottom:0;
}
.stTabs [data-baseweb="tab"]{
  background:transparent !important;border-radius:12px;
  color:rgba(140,180,255,0.5) !important;
  font-family:'Plus Jakarta Sans',sans-serif !important;
  font-weight:600 !important;font-size:0.82rem !important;
  padding:10px 18px !important;transition:all .25s;
  border:1px solid transparent !important;
}
.stTabs [aria-selected="true"]{
  background:rgba(56,217,255,0.1) !important;
  color:#38d9ff !important;
  border:1px solid rgba(56,217,255,0.22) !important;
  box-shadow:0 4px 18px rgba(56,217,255,0.1);
}
.stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]){
  background:rgba(255,255,255,0.04) !important;
  color:rgba(200,225,255,0.75) !important;
}
[data-baseweb="tab-panel"]{padding-top:1.2rem !important}

/* ── BUTTONS ── */
.stButton>button{
  background:rgba(255,255,255,0.04) !important;
  color:rgba(210,230,255,0.88) !important;
  border:1px solid rgba(255,255,255,0.08) !important;
  border-radius:12px !important;padding:10px 20px !important;
  font-family:'Plus Jakarta Sans',sans-serif !important;
  font-weight:600 !important;font-size:0.87rem !important;
  width:100%;transition:all .22s cubic-bezier(.16,1,.3,1) !important;
  backdrop-filter:blur(8px);
}
.stButton>button:hover{
  background:rgba(56,217,255,0.1) !important;
  border-color:rgba(56,217,255,0.38) !important;
  color:#38d9ff !important;
  box-shadow:0 0 22px rgba(56,217,255,0.22),0 4px 10px rgba(0,0,0,0.25) !important;
  transform:translateY(-1px) !important;
}
.stButton>button:active{transform:translateY(1px) !important}

/* ── PRIMARY BTN ── */
.btn-primary>button{
  background:linear-gradient(135deg,#38d9ff 0%,#2563ff 100%) !important;
  color:#fff !important;border:none !important;border-radius:50px !important;
  font-size:0.95rem !important;font-weight:700 !important;padding:13px 26px !important;
  box-shadow:0 4px 22px rgba(37,99,255,0.42) !important;
}
.btn-primary>button:hover{
  transform:translateY(-2px) scale(1.02) !important;
  box-shadow:0 8px 30px rgba(56,217,255,0.5) !important;
}

/* ── DANGER BTN ── */
.btn-danger>button{
  background:rgba(255,50,80,0.07) !important;color:#ff5c6e !important;
  border:1px solid rgba(255,50,80,0.22) !important;
}
.btn-danger>button:hover{
  background:linear-gradient(135deg,#ff416c,#ff2b4a) !important;
  color:#fff !important;border-color:transparent !important;
  box-shadow:0 0 22px rgba(255,65,108,0.4) !important;
}

/* ── INPUTS ── */
.stTextInput input,.stTextArea textarea{
  background:rgba(4,10,24,0.75) !important;
  border:1px solid rgba(255,255,255,0.08) !important;
  color:#e2eeff !important;border-radius:12px !important;
  padding:12px 15px !important;
  font-family:'Plus Jakarta Sans',sans-serif !important;
  font-size:0.92rem !important;transition:all .25s !important;
  box-shadow:inset 0 2px 6px rgba(0,0,0,0.3) !important;
}
.stTextInput input:focus,.stTextArea textarea:focus{
  border-color:rgba(56,217,255,0.45) !important;
  box-shadow:0 0 0 3px rgba(56,217,255,0.1),inset 0 2px 6px rgba(0,0,0,0.3) !important;
}
.stTextInput label,.stTextArea label,.stFileUploader label{
  color:rgba(140,190,255,0.65) !important;font-size:0.75rem !important;
  font-weight:700 !important;letter-spacing:1.2px !important;text-transform:uppercase !important;
}

/* ── METRICS ── */
[data-testid="metric-container"]{
  background:rgba(0,160,255,0.05);
  border:1px solid rgba(0,160,255,0.11);
  border-radius:14px;padding:14px 18px !important;
}
[data-testid="metric-container"] label{
  color:rgba(140,190,255,0.55) !important;font-size:0.7rem !important;
  text-transform:uppercase;letter-spacing:1.8px;
}
[data-testid="stMetricValue"]{
  font-family:'Syne',sans-serif !important;font-size:1.7rem !important;
  font-weight:800 !important;color:#38d9ff !important;
}

/* ── SIDEBAR ── */
[data-testid="stSidebar"]{
  background:rgba(3,8,20,0.95) !important;
  border-right:1px solid rgba(255,255,255,0.055) !important;
  backdrop-filter:blur(20px);
}

/* ── PRODUCT CARD ── */
.prod-card{
  background:rgba(255,255,255,0.028);
  border:1px solid rgba(255,255,255,0.055);
  border-radius:14px;padding:13px;margin-bottom:9px;
  transition:all .28s;
}
.prod-card:hover{
  background:rgba(56,217,255,0.05);
  border-color:rgba(56,217,255,0.18);
  transform:translateY(-2px);
  box-shadow:0 8px 24px rgba(0,0,0,0.28);
}

/* ── TRIAL BADGE ── */
.trial-badge{
  display:inline-block;
  background:linear-gradient(135deg,rgba(251,191,36,0.15),rgba(245,158,11,0.08));
  border:1px solid rgba(251,191,36,0.3);
  color:#fbbf24;border-radius:8px;
  padding:3px 10px;font-size:0.72rem;font-weight:700;letter-spacing:1px;
}
.premium-badge{
  display:inline-block;
  background:linear-gradient(135deg,rgba(56,217,255,0.15),rgba(37,99,255,0.08));
  border:1px solid rgba(56,217,255,0.3);
  color:#38d9ff;border-radius:8px;
  padding:3px 10px;font-size:0.72rem;font-weight:700;letter-spacing:1px;
}

/* ── EXPIRY METER ── */
.expiry-box{
  background:rgba(0,230,118,0.07);
  border:1px solid rgba(0,230,118,0.18);
  border-radius:14px;padding:14px 16px;text-align:center;
}
.expiry-num{
  font-family:'Syne',sans-serif;font-size:2rem;font-weight:800;color:#00e676;
}
.expiry-lbl{font-size:0.7rem;color:rgba(100,200,130,0.55);text-transform:uppercase;letter-spacing:2px;margin-top:2px;}
.expiry-bar-bg{background:rgba(255,255,255,0.07);border-radius:99px;height:5px;margin-top:10px;overflow:hidden;}
.expiry-bar{background:linear-gradient(90deg,#00e676,#00b4d8);height:5px;border-radius:99px;transition:width .8s ease;}

/* ── LINK BOX ── */
.link-box{
  background:rgba(56,217,255,0.05);
  border:1px solid rgba(56,217,255,0.14);
  border-radius:12px;padding:12px 14px;
  font-family:monospace;font-size:0.78rem;
  color:#38d9ff;word-break:break-all;
  cursor:pointer;
}

/* ── DIVIDER ── */
hr{border:none !important;border-top:1px solid rgba(255,255,255,0.055) !important;margin:1.2rem 0 !important;}

/* ── ALERTS ── */
.stSuccess,.stInfo,.stWarning,.stError{border-radius:12px !important;border:none !important;}

/* ── SPINNER ── */
.stSpinner>div{border-top-color:#38d9ff !important;}

/* ── CODE ── */
code{
  background:rgba(56,217,255,0.08) !important;color:#38d9ff !important;
  border-radius:6px !important;padding:2px 7px !important;font-size:0.82rem !important;
  border:1px solid rgba(56,217,255,0.14) !important;
}

/* ── DATAFRAME ── */
[data-testid="stDataFrame"]{border-radius:14px;overflow:hidden;border:1px solid rgba(255,255,255,0.065);}

/* ── FADE IN ── */
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
.g-card,.page-header{animation:fadeUp .55s ease both;}

/* ── CUSTOMER PAGE ── */
.cust-hero{
  min-height:100vh;background:#010409;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:2rem 1.5rem;text-align:center;
  background-image:radial-gradient(ellipse 60% 40% at 50% 0%, rgba(37,211,102,0.1) 0%,transparent 60%);
}
.cust-store-name{
  font-family:'Syne',sans-serif;font-size:clamp(1.6rem,5vw,2.8rem);font-weight:800;
  color:#fff;margin-bottom:.4rem;
}
.cust-tagline{color:rgba(180,230,200,0.55);font-size:.9rem;max-width:380px;line-height:1.6;margin-bottom:2.5rem;}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════
if 'phone'      not in st.session_state: st.session_state.phone      = None
if 'logged_in'  not in st.session_state: st.session_state.logged_in  = False
if 'shop_rules' not in st.session_state: st.session_state.shop_rules = ""

# ══════════════════════════════════════════════════════════
# 📞 CUSTOMER PAGE — WhatsApp Call UI
# ══════════════════════════════════════════════════════════
def customer_page(shop_phone):
    products  = load_inventory(shop_phone)
    shop_ctx  = get_full_ai_context(shop_phone)

    # Hero
    st.markdown(f"""
    <div class="cust-hero">
      <div style="font-size:3.5rem;margin-bottom:.6rem;">🏪</div>
      <h1 class="cust-store-name">কাস্টমার কেয়ার</h1>
      <p class="cust-tagline">যেকোনো প্রশ্ন বা অর্ডারের জন্য সরাসরি কল করুন।<br>২৪/৭ সক্রিয় • বাংলায় কথা বলুন</p>
    </div>
    """, unsafe_allow_html=True)

    # Products
    if products:
        st.markdown("<div class='g-card'>", unsafe_allow_html=True)
        st.markdown("<p class='sec-head' style='color:#38d9ff;'>🛒 আমাদের পণ্যসমূহ</p>", unsafe_allow_html=True)
        cols = st.columns(min(len(products), 3))
        for i, p in enumerate(products):
            with cols[i % len(cols)]:
                st.markdown("<div class='prod-card'>", unsafe_allow_html=True)
                if p.get("image") and os.path.exists(p["image"]):
                    st.image(p["image"], use_column_width=True)
                st.markdown(f"<p style='text-align:center;font-weight:700;font-size:.95rem;color:#e2eeff;margin:4px 0 2px;'>{p.get('name','')}</p>", unsafe_allow_html=True)
                d = p.get('desc','')
                st.markdown(f"<p style='text-align:center;font-size:.78rem;color:rgba(160,200,255,0.55);'>{d[:55]}{'...' if len(d)>55 else ''}</p>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # WhatsApp Call UI
    st.markdown("<div style='max-width:400px;margin:0 auto;'>", unsafe_allow_html=True)
    whatsapp_call_ui(shop_phone, shop_ctx)
    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# 🔐 AUTH PAGE
# ══════════════════════════════════════════════════════════
def auth_page():
    st.markdown("""
    <div class="page-header">
      <h1>GLOBAL AI</h1>
      <p>Bangladesh's #1 AI Sales Platform • বাংলাদেশের ব্যবসায়ীদের জন্য</p>
    </div>
    """, unsafe_allow_html=True)

    _, c, _ = st.columns([1, 1.5, 1])
    with c:
        st.markdown("<div class='g-card'>", unsafe_allow_html=True)
        t1, t2 = st.tabs(["🔐  লগইন", "✨  নতুন অ্যাকাউন্ট"])

        with t1:
            st.markdown("<br>", unsafe_allow_html=True)
            ident = st.text_input("মোবাইল নম্বর বা ইমেইল", placeholder="০১XXXXXXXXX বা email@...", key="li")
            pw    = st.text_input("পাসওয়ার্ড", type="password", placeholder="••••••", key="lp")
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("<div class='btn-primary'>", unsafe_allow_html=True)
            if st.button("লগইন করুন →", key="login_btn"):
                if verify_login_db(ident, pw):
                    phone = get_phone_from_identifier(ident)
                    st.session_state.phone     = phone
                    st.session_state.logged_in = True
                    st.session_state.shop_rules = load_user_memory(phone)
                    st.success("✅ লগইন সফল!")
                    time.sleep(0.6); st.rerun()
                else:
                    st.error("❌ নম্বর/ইমেইল বা পাসওয়ার্ড ভুল!")
            st.markdown("</div>", unsafe_allow_html=True)

        with t2:
            st.markdown("<br>", unsafe_allow_html=True)
            r_phone = st.text_input("মোবাইল নম্বর (১১ ডিজিট)", placeholder="০১XXXXXXXXX", key="rp")
            r_email = st.text_input("ইমেইল অ্যাড্রেস", placeholder="yourname@gmail.com", key="re")
            r_pass  = st.text_input("পাসওয়ার্ড (কমপক্ষে ৪ অক্ষর)", type="password", placeholder="••••••", key="rpw")

            st.markdown("""
            <div style='background:rgba(251,191,36,0.07);border:1px solid rgba(251,191,36,0.2);
                 border-radius:10px;padding:10px 14px;margin:10px 0;'>
              <p style='color:#fbbf24;font-size:0.8rem;font-weight:700;margin:0;'>🎁 ৩ দিন বিনামূল্যে ব্যবহার করুন!</p>
              <p style='color:rgba(251,191,36,0.6);font-size:0.75rem;margin:2px 0 0;'>রেজিস্ট্রেশন করলেই অটো ফ্রি ট্রায়াল শুরু।</p>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("<div class='btn-primary'>", unsafe_allow_html=True)
            if st.button("অ্যাকাউন্ট খুলুন ✨", key="reg_btn"):
                if len(r_phone) != 11 or not r_phone.isdigit():
                    st.warning("⚠️ সঠিক ১১ ডিজিটের মোবাইল নম্বর দিন।")
                elif "@" not in r_email:
                    st.warning("⚠️ সঠিক ইমেইল অ্যাড্রেস দিন।")
                elif len(r_pass) < 4:
                    st.warning("⚠️ পাসওয়ার্ড কমপক্ষে ৪ অক্ষর হতে হবে।")
                else:
                    with st.spinner("অ্যাকাউন্ট তৈরি হচ্ছে..."):
                        status = register_user_db(r_phone, r_email, r_pass)
                    if status == "SUCCESS":
                        st.success("🎉 অ্যাকাউন্ট তৈরি হয়েছে! ৩ দিন ফ্রি ট্রায়াল শুরু।")
                        st.balloons()
                    elif status == "EXISTS":
                        st.warning("⚠️ এই নম্বরে আগে থেকে অ্যাকাউন্ট আছে।")
                    else:
                        st.error(f"🚨 {status.replace('ERROR:','').strip()}")
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# 🛰️ DASHBOARD
# ══════════════════════════════════════════════════════════
def dashboard():
    phone     = st.session_state.phone
    user_data = get_or_create_user(phone)
    owner_phone, biz_name, email, expiry, status = user_data

    try:
        exp_date  = datetime.datetime.strptime(expiry, "%Y-%m-%d").date()
        days_left = (exp_date - datetime.date.today()).days
        trial_days = 3
        pct = max(0, min(100, int(days_left / trial_days * 100))) if status == "TRIAL" else min(100, int(days_left / 30 * 100))
    except:
        days_left = 0; pct = 0

    # ── SIDEBAR ─────────────────────────────
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<h3 style='font-family:Syne;color:#38d9ff;text-align:center;font-size:1rem;letter-spacing:2px;text-transform:uppercase;'>⚡ কন্ট্রোল প্যানেল</h3>", unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)

        # Profile
        st.markdown(f"""
        <div style='background:rgba(56,217,255,0.05);border:1px solid rgba(56,217,255,0.1);border-radius:14px;padding:14px 16px;margin-bottom:14px;'>
          <div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;'>
            <div style='width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,#38d9ff,#2563ff);display:flex;align-items:center;justify-content:center;font-size:1.1rem;'>🏪</div>
            <div>
              <p style='color:#e2eeff;font-weight:700;font-size:0.88rem;margin:0;'>{biz_name}</p>
              <p style='color:rgba(140,180,255,0.5);font-size:0.72rem;margin:0;'>{owner_phone}</p>
            </div>
          </div>
          <span class='{"trial-badge" if status=="TRIAL" else "premium-badge"}'>{"⏳ TRIAL" if status=="TRIAL" else "⭐ PREMIUM"}</span>
        </div>
        """, unsafe_allow_html=True)

        # Expiry
        if days_left >= 0:
            st.markdown(f"""
            <div class='expiry-box' style='margin-bottom:14px;'>
              <div class='expiry-num'>{days_left}</div>
              <div class='expiry-lbl'>দিন বাকি আছে</div>
              <div class='expiry-bar-bg'><div class='expiry-bar' style='width:{pct}%'></div></div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error("❌ মেয়াদ শেষ! রিচার্জ করুন।")

        # Recharge
        st.markdown("<div style='background:rgba(0,160,255,0.06);border:1px solid rgba(0,160,255,0.13);border-radius:13px;padding:14px;margin-bottom:14px;'>", unsafe_allow_html=True)
        st.markdown("<p style='font-size:0.75rem;font-weight:700;color:#38d9ff;margin-bottom:6px;letter-spacing:1px;'>💳 মেয়াদ বাড়ান</p>", unsafe_allow_html=True)
        sec_key = st.text_input("Secret Key", type="password", placeholder="XXXXXXXX", key="skey")
        if st.button("রিচার্জ করুন →", key="recharge"):
            if sec_key in VOUCHERS:
                extend_subscription(owner_phone, VOUCHERS[sec_key])
                st.success("🎉 মেয়াদ বাড়ানো হয়েছে!")
                time.sleep(0.6); st.rerun()
            else:
                st.error("❌ ভুল Secret Key!")
        st.markdown("</div>", unsafe_allow_html=True)

        # Customer Link
        short_link = get_short_link(owner_phone)
        st.markdown("<p style='font-size:0.7rem;color:rgba(140,180,255,0.45);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:5px;'>🔗 আপনার কাস্টমার লিংক</p>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class='link-box' onclick="navigator.clipboard.writeText('{short_link}');this.textContent='✅ কপি হয়েছে!';" title="ক্লিক করলে কপি হবে">
          {short_link}
        </div>
        <p style='font-size:0.7rem;color:rgba(140,180,255,0.35);margin-top:4px;'>👆 ক্লিক করলে কপি হবে • Facebook পেজে শেয়ার করুন</p>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div class='btn-danger'>", unsafe_allow_html=True)
        if st.button("🔴 লগআউট"):
            st.session_state.logged_in = False
            st.session_state.phone     = None
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # ── MAIN AREA ────────────────────────────
    st.markdown("""
    <div class="page-header" style="padding-top:1rem;">
      <h1>GLOBAL AI WORKSPACE</h1>
      <p>আপনার ব্যবসার সম্পূর্ণ AI কন্ট্রোল প্যানেল</p>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊  ড্যাশবোর্ড",
        "📞  কল সেন্টার",
        "🧠  AI ট্রেনিং",
        "🛍️  ইনভেন্টরি",
        "📦  অর্ডার ভল্ট"
    ])

    # ── TAB 1: DASHBOARD ─────────────────────
    with tab1:
        df = get_all_orders(owner_phone)
        total_sales  = int(df['total_amount'].sum()) if df is not None and not df.empty and 'total_amount' in df.columns else 0
        total_calls  = len(df) if df is not None and not df.empty else 0
        real_orders  = len(df[df['status'].str.contains('REAL', na=False)]) if df is not None and not df.empty and 'status' in df.columns else 0

        st.markdown(f"""
        <div class='kpi-grid'>
          <div class='kpi'><div class='kpi-val'>৳{total_sales:,}</div><div class='kpi-lbl'>মোট সেলস</div></div>
          <div class='kpi'><div class='kpi-val'>{total_calls}</div><div class='kpi-lbl'>মোট কল</div></div>
          <div class='kpi'><div class='kpi-val'>{real_orders}</div><div class='kpi-lbl'>রিয়েল অর্ডার</div></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div class='g-card' style='margin-top:14px;'>", unsafe_allow_html=True)
        st.markdown("<p class='sec-head' style='color:#38d9ff;'>📈 সেলস চার্ট</p>", unsafe_allow_html=True)
        if df is not None and not df.empty and 'order_date' in df.columns and 'total_amount' in df.columns:
            fig = px.area(df, x='order_date', y='total_amount', color_discrete_sequence=["#38d9ff"], template="plotly_dark")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0,r=0,t=8,b=0),
                xaxis=dict(gridcolor="rgba(255,255,255,0.04)",showgrid=True),
                yaxis=dict(gridcolor="rgba(255,255,255,0.04)",showgrid=True))
            fig.update_traces(fillcolor="rgba(56,217,255,0.07)", line=dict(color="#38d9ff",width=2))
            st.plotly_chart(fig, use_container_width=True)

            # Status pie
            if 'status' in df.columns and not df.empty:
                s_counts = df['status'].value_counts().reset_index()
                s_counts.columns = ['status','count']
                pie = px.pie(s_counts, names='status', values='count', hole=0.55,
                    color_discrete_sequence=['#38d9ff','#f59e0b','#ff5c6e'], template="plotly_dark")
                pie.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0,r=0,t=8,b=0),legend=dict(font=dict(color="#9db4d8")))
                st.plotly_chart(pie, use_container_width=True)
        else:
            st.markdown("""
            <div style='text-align:center;padding:3rem 0;'>
              <p style='font-size:2.5rem;'>📡</p>
              <p style='color:rgba(140,180,255,0.4);font-size:.88rem;'>এখনো কোনো ডাটা নেই।<br>কাস্টমার লিংক শেয়ার করুন।</p>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # Recent orders table
        if df is not None and not df.empty:
            st.markdown("<div class='g-card'>", unsafe_allow_html=True)
            st.markdown("<p class='sec-head' style='color:#f59e0b;'>⚡ সাম্প্রতিক অর্ডার</p>", unsafe_allow_html=True)
            show_cols = [c for c in ['customer_name','customer_phone','district','total_amount','trust_score','status','order_date'] if c in df.columns]
            st.dataframe(df[show_cols].head(10), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

    # ── TAB 2: CALL CENTER ───────────────────
    with tab2:
        st.markdown("<div class='g-card'>", unsafe_allow_html=True)
        st.markdown("<p class='sec-head' style='color:#00e676;'>📞 AI কল টেস্ট প্যানেল</p>", unsafe_allow_html=True)
        st.markdown("<p style='color:rgba(140,190,255,0.45);font-size:.82rem;'>এখানে আপনি AI-কে নিজে টেস্ট করতে পারবেন — কাস্টমার যা অনুভব করবে।</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        _, cc, _ = st.columns([1, 2, 1])
        with cc:
            shop_ctx = get_full_ai_context(owner_phone)
            whatsapp_call_ui(owner_phone, shop_ctx)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── TAB 3: AI TRAINING ───────────────────
    with tab3:
        st.markdown("<div class='g-card'>", unsafe_allow_html=True)
        st.markdown("<p class='sec-head' style='color:#fbbf24;'>🧠 দোকানের তথ্য ও নিয়মকানুন</p>", unsafe_allow_html=True)
        st.markdown("<p style='color:rgba(140,190,255,0.45);font-size:.82rem;margin-bottom:12px;'>এই তথ্য AI পড়বে এবং কাস্টমারকে সঠিক উত্তর দেবে।</p>", unsafe_allow_html=True)
        rules = st.text_area("ডেলিভারি চার্জ, রিটার্ন পলিসি, বিশেষ অফার লিখুন:",
            value=st.session_state.shop_rules, height=120,
            placeholder="যেমন: ঢাকার ভেতরে ডেলিভারি ৬০ টাকা, বাইরে ১২০ টাকা। ক্যাশ অন ডেলিভারি সুবিধা আছে...")
        st.markdown("<div class='btn-primary'>", unsafe_allow_html=True)
        if st.button("💾 সেভ করুন", key="save_rules"):
            save_user_memory(phone, rules)
            st.session_state.shop_rules = rules
            st.success("✅ AI-এর মেমোরি আপডেট হয়েছে!")
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── TAB 4: INVENTORY ─────────────────────
    with tab4:
        # Add product
        st.markdown("<div class='g-card'>", unsafe_allow_html=True)
        st.markdown("<p class='sec-head' style='color:#38d9ff;'>➕ নতুন পণ্য যুক্ত করুন</p>", unsafe_allow_html=True)
        with st.form("add_prod", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1: p_name = st.text_input("পণ্যের নাম", placeholder="যেমন: লাল শাড়ি")
            with c2: p_img  = st.file_uploader("ছবি (ঐচ্ছিক)", type=['jpg','png','jpeg'])
            p_desc = st.text_area("বিবরণ ও দাম", placeholder="যেমন: সিল্কের শাড়ি, সাইজ ফ্রি, দাম ১২০০ টাকা", height=65)
            st.markdown("<div class='btn-primary'>", unsafe_allow_html=True)
            added = st.form_submit_button("➕ পণ্য যুক্ত করুন")
            st.markdown("</div>", unsafe_allow_html=True)
            if added:
                if p_name and p_desc:
                    prods = load_inventory(owner_phone)
                    img_path = ""
                    if p_img:
                        img_path = f"{DATA_DIR}/{owner_phone}_{int(time.time())}.png"
                        Image.open(p_img).save(img_path)
                    prods.append({"name": p_name, "desc": p_desc, "image": img_path})
                    save_inventory(owner_phone, prods)
                    st.success(f"✅ '{p_name}' যুক্ত হয়েছে!")
                    time.sleep(0.6); st.rerun()
                else:
                    st.warning("⚠️ নাম এবং বিবরণ দিতে হবে।")
        st.markdown("</div>", unsafe_allow_html=True)

        # Product list
        saved = load_inventory(owner_phone)
        if saved:
            st.markdown("<div class='g-card'>", unsafe_allow_html=True)
            st.markdown(f"<p class='sec-head' style='color:#a855f7;'>📦 পণ্য তালিকা ({len(saved)} টি)</p>", unsafe_allow_html=True)
            for i, p in enumerate(saved):
                st.markdown("<div class='prod-card'>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns([1, 5, 1])
                with c1:
                    if p.get("image") and os.path.exists(p["image"]):
                        st.image(p["image"], width=52)
                    else:
                        st.markdown("<div style='width:52px;height:52px;background:rgba(255,255,255,0.05);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.4rem;'>🛍️</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"<p style='font-weight:700;font-size:.9rem;color:#e2eeff;margin:0 0 2px;'>{p.get('name','')}</p>", unsafe_allow_html=True)
                    d = p.get('desc','')
                    st.markdown(f"<p style='font-size:.76rem;color:rgba(140,190,255,0.5);margin:0;'>{d[:85]}{'...' if len(d)>85 else ''}</p>", unsafe_allow_html=True)
                with c3:
                    st.markdown("<div class='btn-danger'>", unsafe_allow_html=True)
                    if st.button("✕", key=f"del_{i}"):
                        saved.pop(i); save_inventory(owner_phone, saved); st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    # ── TAB 5: VAULT ─────────────────────────
    with tab5:
        st.markdown("<div class='g-card'>", unsafe_allow_html=True)
        st.markdown("<p class='sec-head' style='color:#a855f7;'>📦 কাস্টমার অর্ডার ভল্ট</p>", unsafe_allow_html=True)
        df_v = get_all_orders(owner_phone)
        if df_v is not None and not df_v.empty:
            show = [c for c in ['customer_name','customer_phone','village','district','quantity','total_amount','trust_score','status','order_date'] if c in df_v.columns]
            st.dataframe(df_v[show] if show else df_v, use_container_width=True)

            # Export
            csv = df_v.to_csv(index=False).encode('utf-8')
            st.download_button("📥 CSV ডাউনলোড করুন", csv, "orders.csv", "text/csv", key="dl_csv")
        else:
            st.markdown("""
            <div style='text-align:center;padding:3rem 0;'>
              <p style='font-size:3rem;'>📭</p>
              <p style='color:rgba(140,180,255,0.35);font-size:.85rem;'>কোনো অর্ডার নেই।<br>কাস্টমার লিংক শেয়ার করুন।</p>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# 🚀 MAIN
# ══════════════════════════════════════════════════════════
def main():
    qp = st.query_params
    if "shop" in qp:
        customer_page(qp["shop"])
        return

    if not st.session_state.logged_in:
        auth_page()
        return

    dashboard()


if __name__ == "__main__":
    main()
