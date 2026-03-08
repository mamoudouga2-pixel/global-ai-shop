import streamlit as st
from supabase import create_client, Client
import hashlib
try:
    import pandas as pd
except ImportError:
    pd = None
import datetime
import plotly.express as px
import plotly.graph_objects as go
import os
import time
from PIL import Image

st.set_page_config(
    page_title="GLOBAL AI | PRO",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def _get_secret(key, default=""):
    try:
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)

GEMINI_API_KEY     = _get_secret("GEMINI_API_KEY")
GROQ_API_KEY       = _get_secret("GROQ_API_KEY")
OPENROUTER_API_KEY = _get_secret("OPENROUTER_API_KEY")

supabase = None
try:
    _url = _get_secret("SUPABASE_URL","").strip()
    _key = _get_secret("SUPABASE_KEY","").strip()
    if _url.startswith("https://") and _key:
        supabase: Client = create_client(_url, _key)
except Exception as e:
    print("[Supabase]", e)

DATA_DIR = "user_memory"
os.makedirs(DATA_DIR, exist_ok=True)

try:
    from database import get_or_create_user, extend_subscription, save_order, get_all_orders
    from logic import VOUCHERS, get_ai_response, analyze_fake_order, extract_customer_info
    files_missing = False
except ImportError:
    files_missing = True
    def get_or_create_user(phone): return (phone, "My Business", "", "2030-12-31", "TRIAL")
    def extend_subscription(phone, days): pass
    def get_all_orders(phone): return None
    VOUCHERS = {"FUTURE2040": 30, "BANGLADESH_AI": 365, "TRIAL_BOSS": 7}
    def get_ai_response(msg, tone, key, ctx): return f"[DATA: Demo] {msg}"
    def analyze_fake_order(u, a): return "POTENTIAL_ORDER (50%)", "🟨"
    def extract_customer_info(t): return {}

import requests as _req, io as _io, base64 as _b64

_SALES_PROMPT = (
    "তুমি একজন বাংলাদেশী দোকানের অভিজ্ঞ কাস্টমার কেয়ার প্রতিনিধি।\n"
    "কঠোর নিয়ম:\n"
    "১. তুমি কখনোই বলবে না যে তুমি AI, রোবট বা chatbot — তুমি একজন মানুষ কর্মী।\n"
    "২. কেউ 'আসসালামু আলাইকুম' বা 'সালাম' দিলে আগে 'ওয়ালাইকুম আসসালাম' বলো।\n"
    "৩. কেউ সালাম না দিয়ে সরাসরি প্রশ্ন করলে সরাসরি উত্তর দাও — আগে সালাম দেওয়ার দরকার নেই।\n"
    "৪. সম্বোধন: জ্বি ভাই / জ্বি আপু / জ্বি স্যার — পরিস্থিতি বুঝে ব্যবহার করো।\n"
    "৫. উত্তর সর্বোচ্চ ২-৩ বাক্যে দাও। সবসময় বাংলায়।\n"
    "৬. কাস্টমার একটা পণ্য চাইলে সম্পর্কিত আরেকটা suggest করো।\n"
    "৭. অর্ডার নিশ্চিত করতে নাম ও ঠিকানা চাও।\n"
    "৮. উষ্ণ ও আন্তরিক কথা বলো — যেন পরিচিত দোকানদার।"
)

def get_ai_sales_response(user_message, shop_context=""):
    import re
    gkey  = _get_secret("GEMINI_API_KEY") or GEMINI_API_KEY
    grkey = _get_secret("GROQ_API_KEY")   or GROQ_API_KEY
    prompt = (
        _SALES_PROMPT
        + "\n\n[দোকানের তথ্য]: " + shop_context[:300]
        + "\n\nকাস্টমার বলেছে: " + user_message
        + "\n\nতোমার উত্তর:"
    )
    if gkey:
        try:
            url = ("https://generativelanguage.googleapis.com/v1beta"
                   "/models/gemini-2.0-flash-lite:generateContent?key=" + gkey)
            r = _req.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.85, "maxOutputTokens": 120}
            }, timeout=15)
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                txt = re.sub(r"\[EXTRACTED_DATA:.*?\]", "", txt, flags=re.DOTALL).strip()
                return txt
        except Exception as ex:
            print("[Gemini]", ex)
    if grkey:
        try:
            r = _req.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": "Bearer " + grkey, "Content-Type": "application/json"},
                json={"model": "llama3-8b-8192",
                      "messages": [{"role": "system", "content": _SALES_PROMPT},
                                   {"role": "user", "content": "দোকান: " + shop_context[:200] + "\nকাস্টমার: " + user_message}],
                      "max_tokens": 120},
                timeout=15
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as ex:
            print("[Groq]", ex)
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
    except Exception as e:
        print("[gTTS]", e)
        return ""

def whatsapp_call_ui(shop_phone="", shop_context="", check_sub=False, expiry_date="2099-01-01"):
    import streamlit.components.v1 as _c
    # সম্পূর্ণ বিনামূল্যে — subscription check নেই

    for k,v in [("call_active",False),("call_greeted",False),("audio_b64",""),("audio_id",0)]:
        if k not in st.session_state: st.session_state[k]=v

    # greeting
    if st.session_state.call_active and not st.session_state.call_greeted:
        with st.spinner("AI সংযুক্ত হচ্ছে..."):
            greet = get_ai_sales_response(
                "কাস্টমার কল করেছে। আসসালামু আলাইকুম বলো, কাস্টমার কেয়ার হিসেবে পরিচয় দাও, সাহায্যের কথা জিজ্ঞেস করো।",
                shop_context)
            st.session_state.audio_b64 = text_to_audio_b64(greet)
            st.session_state.audio_id += 1
            st.session_state.call_greeted = True

    is_active = st.session_state.call_active
    audio_b64 = st.session_state.audio_b64
    audio_id  = str(st.session_state.audio_id)

    # audio autoplay
    if is_active and audio_b64:
        _c.html(f"""<script>
(function(){{
  var k="a{audio_id}";
  if(sessionStorage.getItem(k))return;
  sessionStorage.setItem(k,"1");
  try{{
    var b=atob("{audio_b64}"),buf=new ArrayBuffer(b.length),u=new Uint8Array(buf);
    for(var i=0;i<b.length;i++)u[i]=b.charCodeAt(i);
    var ctx=new(window.AudioContext||window.webkitAudioContext)();
    ctx.decodeAudioData(buf,function(d){{
      var s=ctx.createBufferSource();s.buffer=d;s.connect(ctx.destination);s.start(0);
    }});
  }}catch(e){{}}
}})();
</script>""", height=0)

    # call UI
    av_cls = "av ring" if not is_active else "av live"
    st_txt  = "কল করতে নিচের বাটন চাপুন" if not is_active else "🟢 সংযুক্ত — কথা বলুন"

    _c.html(f"""<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:"Noto Sans Bengali",sans-serif;background:transparent;display:flex;justify-content:center;padding:10px 0;}}
.wrap{{display:flex;flex-direction:column;align-items:center;background:linear-gradient(180deg,#0d1117,#161b22);
border-radius:24px;padding:26px 20px 20px;width:100%;max-width:300px;
box-shadow:0 8px 40px rgba(0,0,0,.7);border:1px solid rgba(255,255,255,.07);}}
.av{{width:84px;height:84px;border-radius:50%;background:linear-gradient(135deg,#25d366,#075e35);
display:flex;align-items:center;justify-content:center;font-size:2.5rem;margin-bottom:10px;}}
.av.ring{{animation:rp 1.2s ease infinite;}}
.av.live{{box-shadow:0 0 0 5px rgba(37,211,102,.3);}}
@keyframes rp{{0%,100%{{box-shadow:0 0 0 0 rgba(37,211,102,.8);}}70%{{box-shadow:0 0 0 20px rgba(37,211,102,0);}}}}
.nm{{color:#fff;font-size:1.1rem;font-weight:700;margin-bottom:4px;}}
.st{{color:rgba(255,255,255,.4);font-size:.75rem;margin-bottom:14px;text-align:center;}}
.pls{{display:{"flex" if is_active else "none"};gap:5px;margin-bottom:12px;}}
.pls span{{width:6px;height:6px;border-radius:50%;background:#25d366;animation:pl .7s ease infinite alternate;}}
.pls span:nth-child(2){{animation-delay:.2s;}}.pls span:nth-child(3){{animation-delay:.4s;}}
@keyframes pl{{from{{opacity:.15;transform:scale(.5);}}to{{opacity:1;transform:scale(1.5);}}}}
</style>
<div class="wrap">
  <div class="{av_cls}">🏪</div>
  <div class="nm">কাস্টমার কেয়ার</div>
  <div class="st">{st_txt}</div>
  <div class="pls"><span></span><span></span><span></span></div>
</div>""", height=240)

    # Streamlit native buttons — NO query params, NO rerun loop
    c1,c2,c3 = st.columns([1,2,1])
    with c2:
        if not is_active:
            if st.button("📞  কল করুন", use_container_width=True, key=f"bcall_{shop_phone}"):
                st.session_state.call_active  = True
                st.session_state.call_greeted = False
                st.session_state.audio_b64    = ""
                st.rerun()
        else:
            if st.button("📵  কল কাটুন", use_container_width=True, key=f"bend_{shop_phone}"):
                st.session_state.call_active  = False
                st.session_state.call_greeted = False
                st.session_state.audio_b64    = ""
                st.rerun()

    # Mic input — voice থেকে text
    if is_active:
        st.markdown("<p style='color:rgba(140,190,255,.5);font-size:.75rem;text-align:center;margin-top:8px;'>🎤 নিচে টাইপ বা ভয়েস দিন</p>", unsafe_allow_html=True)
        col_i, col_b = st.columns([4,1])
        with col_i:
            user_input = st.text_input("", placeholder="বলুন বা টাইপ করুন...", key=f"vi_{shop_phone}", label_visibility="collapsed")
        with col_b:
            if st.button("➤", key=f"vsend_{shop_phone}"):
                if user_input.strip():
                    with st.spinner("..."):
                        reply = get_ai_sales_response(user_input.strip(), shop_context)
                        st.session_state.audio_b64 = text_to_audio_b64(reply)
                        st.session_state.audio_id += 1
                    st.rerun()


def hash_pass(p): return hashlib.sha256(str(p).encode()).hexdigest()

def register_user_db(phone, email, password):
    if supabase is None: return "ERROR: ডাটাবেস নেই"
    try:
        c = supabase.table("merchants").select("phone").eq("phone", phone).execute()
        if c.data: return "EXISTS"
        expiry = "2099-12-31"  # সম্পূর্ণ বিনামূল্যে — কোনো মেয়াদ নেই
        insert_data = {"phone": phone, "email": email, "pin": hash_pass(password), "expiry_date": expiry}
        try:
            insert_data["status"] = "FREE"
            supabase.table("merchants").insert(insert_data).execute()
        except Exception:
            insert_data.pop("status", None)
            supabase.table("merchants").insert(insert_data).execute()
        supabase.table("merchant_data").insert({
            "merchant_phone": phone, "rules": "দোকানের নিয়ম এখানে লিখুন...", "inventory": []
        }).execute()
        return "SUCCESS"
    except Exception as e:
        return f"ERROR: {e}"

def verify_login_db(identifier, password):
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

def save_profile(phone, data):
    """data = {owner_name, company_name}"""
    if supabase:
        try:
            supabase.table("merchant_data").update({"profile": data}).eq("merchant_phone", phone).execute()
        except: pass

def load_profile(phone):
    if supabase:
        try:
            res = supabase.table("merchant_data").select("profile").eq("merchant_phone", phone).execute()
            if res.data and res.data[0].get("profile"):
                return res.data[0]["profile"]
        except: pass
    return {}

def get_full_ai_context(phone):
    info = load_user_memory(phone)
    products = load_inventory(phone)
    profile = load_profile(phone)
    company = profile.get("company_name", "") or "আমাদের দোকান"
    ctx = f"[দোকানের নাম]: {company}\n[নিয়ম]: {info}\n\n[পণ্যসমূহ]:\n"
    for p in products:
        ctx += f"- {p.get('name','')}: {p.get('desc','')}\n"
    return ctx

BASE_URL      = os.environ.get("RENDER_EXTERNAL_URL", "https://global-ai-shop.onrender.com").strip().rstrip("/")
VOICE_API_URL = os.environ.get("VOICE_API_URL", BASE_URL).strip().rstrip("/")

def get_short_link(phone):
    # Customer লিংক এখন FastAPI page এ যাবে — Streamlit না
    return f"{BASE_URL}/?shop={phone}"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
#MainMenu,footer,header{visibility:hidden}
.block-container{padding-top:0 !important;padding-bottom:2rem !important;max-width:1400px}
.stApp{
  background:#020710;
  background-image:
    radial-gradient(ellipse 70% 50% at 5% 0%,   rgba(0,160,255,0.12) 0%,transparent 55%),
    radial-gradient(ellipse 50% 40% at 95% 100%, rgba(120,0,255,0.10) 0%,transparent 55%),
    radial-gradient(ellipse 35% 25% at 50% 50%,  rgba(0,255,150,0.04) 0%,transparent 65%);
  color:#dde6f5;font-family:'Plus Jakarta Sans',sans-serif;
}
h1,h2,h3,h4{font-family:'Syne',sans-serif !important}
.page-header{padding:2.5rem 0 0.5rem;text-align:center;}
.page-header h1{
  font-family:'Syne',sans-serif;font-size:clamp(2.2rem,5vw,4rem);font-weight:800;
  background:linear-gradient(135deg,#38d9ff 0%,#2563ff 45%,#a855f7 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  letter-spacing:-2px;line-height:1.05;margin:0;
}
.page-header p{font-size:0.78rem;color:rgba(160,200,255,0.45);letter-spacing:5px;text-transform:uppercase;margin-top:0.5rem;font-weight:500;}
.g-card{
  background:rgba(10,18,36,0.6);backdrop-filter:blur(32px) saturate(200%);
  border-radius:22px;border:1px solid rgba(255,255,255,0.065);
  box-shadow:0 24px 64px rgba(0,0,0,0.55),inset 0 1px 0 rgba(255,255,255,0.08);
  padding:28px 30px;margin-bottom:18px;transition:border-color .4s,box-shadow .4s;
}
.g-card:hover{border-color:rgba(56,217,255,0.16);}
.kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:4px}
.kpi{background:rgba(0,160,255,0.06);border:1px solid rgba(0,160,255,0.14);border-radius:16px;padding:18px 20px;text-align:center;}
.kpi-val{font-family:'Syne',sans-serif;font-size:1.9rem;font-weight:800;background:linear-gradient(135deg,#38d9ff,#2563ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.kpi-lbl{font-size:0.72rem;color:rgba(140,190,255,0.55);text-transform:uppercase;letter-spacing:1.8px;margin-top:3px;}
.sec-head{font-family:'Syne',sans-serif;font-size:1.05rem;font-weight:700;display:flex;align-items:center;gap:8px;margin-bottom:1rem;}
.stTabs [data-baseweb="tab-list"]{background:rgba(6,12,26,0.7);border-radius:16px;padding:5px;gap:3px;border:1px solid rgba(255,255,255,0.055);margin-bottom:0;}
.stTabs [data-baseweb="tab"]{background:transparent !important;border-radius:12px;color:rgba(140,180,255,0.5) !important;font-family:'Plus Jakarta Sans',sans-serif !important;font-weight:600 !important;font-size:0.82rem !important;padding:10px 18px !important;transition:all .25s;border:1px solid transparent !important;}
.stTabs [aria-selected="true"]{background:rgba(56,217,255,0.1) !important;color:#38d9ff !important;border:1px solid rgba(56,217,255,0.22) !important;}
[data-baseweb="tab-panel"]{padding-top:1.2rem !important}
.stButton>button{background:rgba(255,255,255,0.04) !important;color:rgba(210,230,255,0.88) !important;border:1px solid rgba(255,255,255,0.08) !important;border-radius:12px !important;padding:10px 20px !important;font-family:'Plus Jakarta Sans',sans-serif !important;font-weight:600 !important;font-size:0.87rem !important;width:100%;transition:all .22s !important;}
.stButton>button:hover{background:rgba(56,217,255,0.1) !important;border-color:rgba(56,217,255,0.38) !important;color:#38d9ff !important;transform:translateY(-1px) !important;}
.btn-primary>button{background:linear-gradient(135deg,#38d9ff 0%,#2563ff 100%) !important;color:#fff !important;border:none !important;border-radius:50px !important;font-size:0.95rem !important;font-weight:700 !important;padding:13px 26px !important;}
.btn-danger>button{background:rgba(255,50,80,0.07) !important;color:#ff5c6e !important;border:1px solid rgba(255,50,80,0.22) !important;}
.stTextInput input,.stTextArea textarea{background:rgba(4,10,24,0.75) !important;border:1px solid rgba(255,255,255,0.08) !important;color:#e2eeff !important;border-radius:12px !important;padding:12px 15px !important;font-family:'Plus Jakarta Sans',sans-serif !important;}
.stTextInput label,.stTextArea label,.stFileUploader label{color:rgba(140,190,255,0.65) !important;font-size:0.75rem !important;font-weight:700 !important;letter-spacing:1.2px !important;text-transform:uppercase !important;}
[data-testid="stSidebar"]{background:rgba(3,8,20,0.95) !important;border-right:1px solid rgba(255,255,255,0.055) !important;}
.prod-card{background:rgba(255,255,255,0.028);border:1px solid rgba(255,255,255,0.055);border-radius:14px;padding:13px;margin-bottom:9px;transition:all .28s;}
.trial-badge{display:inline-block;background:linear-gradient(135deg,rgba(251,191,36,0.15),rgba(245,158,11,0.08));border:1px solid rgba(251,191,36,0.3);color:#fbbf24;border-radius:8px;padding:3px 10px;font-size:0.72rem;font-weight:700;letter-spacing:1px;}
.premium-badge{display:inline-block;background:linear-gradient(135deg,rgba(56,217,255,0.15),rgba(37,99,255,0.08));border:1px solid rgba(56,217,255,0.3);color:#38d9ff;border-radius:8px;padding:3px 10px;font-size:0.72rem;font-weight:700;letter-spacing:1px;}
.expiry-box{background:rgba(0,230,118,0.07);border:1px solid rgba(0,230,118,0.18);border-radius:14px;padding:14px 16px;text-align:center;}
.expiry-num{font-family:'Syne',sans-serif;font-size:2rem;font-weight:800;color:#00e676;}
.expiry-lbl{font-size:0.7rem;color:rgba(100,200,130,0.55);text-transform:uppercase;letter-spacing:2px;margin-top:2px;}
.expiry-bar-bg{background:rgba(255,255,255,0.07);border-radius:99px;height:5px;margin-top:10px;overflow:hidden;}
.expiry-bar{background:linear-gradient(90deg,#00e676,#00b4d8);height:5px;border-radius:99px;}
.link-box{background:rgba(56,217,255,0.05);border:1px solid rgba(56,217,255,0.14);border-radius:12px;padding:12px 14px;font-family:monospace;font-size:0.78rem;color:#38d9ff;word-break:break-all;cursor:pointer;}
hr{border:none !important;border-top:1px solid rgba(255,255,255,0.055) !important;margin:1.2rem 0 !important;}
.stSpinner>div{border-top-color:#38d9ff !important;}
[data-testid="stDataFrame"]{border-radius:14px;overflow:hidden;border:1px solid rgba(255,255,255,0.065);}
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
.g-card,.page-header{animation:fadeUp .55s ease both;}
.cust-hero{min-height:100vh;background:#010409;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:2rem 1.5rem;text-align:center;background-image:radial-gradient(ellipse 60% 40% at 50% 0%, rgba(37,211,102,0.1) 0%,transparent 60%);}
.cust-store-name{font-family:'Syne',sans-serif;font-size:clamp(1.6rem,5vw,2.8rem);font-weight:800;color:#fff;margin-bottom:.4rem;}
.cust-tagline{color:rgba(180,230,200,0.55);font-size:.9rem;max-width:380px;line-height:1.6;margin-bottom:2.5rem;}
</style>
""", unsafe_allow_html=True)

if 'phone'      not in st.session_state: st.session_state.phone      = None
if 'logged_in'  not in st.session_state: st.session_state.logged_in  = False
if 'shop_rules' not in st.session_state: st.session_state.shop_rules = ""

def customer_page(shop_phone):
    import streamlit.components.v1 as _cv1

    sub_data   = get_or_create_user(shop_phone)
    expiry_str = sub_data[3] if sub_data else "2099-01-01"
    biz_nm     = sub_data[1] if sub_data else "কাস্টমার কেয়ার"
    # সম্পূর্ণ বিনামূল্যে — expired কখনো হবে না
    is_expired = False

    profile  = load_profile(shop_phone)
    biz_name = profile.get("company_name","") or biz_nm
    products = load_inventory(shop_phone)
    rules    = load_user_memory(shop_phone)
    gkey     = _get_secret("GEMINI_API_KEY") or GEMINI_API_KEY

    prod_lines = [p.get("name","") + ": " + p.get("desc","") for p in products[:15]]
    ctx = "দোকান: " + biz_name + ". নিয়ম: " + rules[:150] + ". পণ্য: " + " | ".join(prod_lines[:10])
    ctx_js = str(ctx).replace("\\","\\\\").replace("`","'").replace("$","").replace("\n"," ")
    biz_js = str(biz_name).replace("<","").replace(">","").replace("`","").replace("$","").replace("\n","")
    gkey_js = str(gkey).strip()

    st.markdown("""<style>
    #MainMenu,footer,header,[data-testid="stHeader"],[data-testid="stToolbar"],
    [data-testid="stDecoration"],[data-testid="stStatusWidget"]{display:none!important;}
    .block-container{padding:0!important;max-width:100%!important;}
    .stApp{background:#010409!important;}
    section[data-testid="stSidebar"]{display:none!important;}
    iframe{border:none!important;display:block!important;}
    </style>""", unsafe_allow_html=True)

    if is_expired:
        _cv1.html("""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{background:#010409;display:flex;align-items:center;justify-content:center;
min-height:100vh;font-family:sans-serif;margin:0;}
.box{background:#161b22;border-radius:20px;padding:32px 24px;text-align:center;
border:1px solid rgba(255,59,48,.3);max-width:300px;width:90%;}
</style></head><body><div class="box">
<div style="font-size:3rem;margin-bottom:12px;">🔒</div>
<div style="color:#ff5c6e;font-size:1rem;font-weight:700;margin-bottom:8px;">সেবার মেয়াদ শেষ</div>
<div style="color:rgba(255,150,150,.5);font-size:.8rem;">ব্যবসায়ীকে জানান — মেয়াদ বাড়াতে হবে।</div>
</div></body></html>""", height=300)
        return

    html = """<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>""" + biz_js + """</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
html,body{width:100%;min-height:100vh;background:#010409;overflow-x:hidden;}
body{font-family:"Noto Sans Bengali",sans-serif;display:flex;flex-direction:column;
align-items:center;justify-content:flex-start;padding:20px 16px 40px;
background-image:radial-gradient(ellipse 70% 50% at 50% 0%,rgba(37,211,102,.09) 0%,transparent 60%);}
.card{background:linear-gradient(180deg,#0d1117,#161b22);border-radius:24px;
padding:30px 20px 26px;width:100%;max-width:340px;
box-shadow:0 8px 40px rgba(0,0,0,.8);border:1px solid rgba(255,255,255,.07);
display:flex;flex-direction:column;align-items:center;}
.shop{color:rgba(255,255,255,.25);font-size:.65rem;letter-spacing:3px;
text-transform:uppercase;margin-bottom:20px;}
.av{width:90px;height:90px;border-radius:50%;
background:linear-gradient(135deg,#25d366,#075e35);
display:flex;align-items:center;justify-content:center;font-size:2.8rem;margin-bottom:12px;}
.av.ring{animation:rp 1.1s ease infinite;}
.av.live{box-shadow:0 0 0 6px rgba(37,211,102,.3);}
@keyframes rp{0%,100%{box-shadow:0 0 0 0 rgba(37,211,102,.8);}
70%{box-shadow:0 0 0 28px rgba(37,211,102,0);}}
.nm{color:#fff;font-size:1.2rem;font-weight:700;margin-bottom:5px;}
.st{min-height:20px;font-size:.76rem;color:rgba(255,255,255,.38);
margin-bottom:16px;text-align:center;line-height:1.4;}
.st.green{color:#25d366;}
.tmr{color:rgba(255,255,255,.25);font-size:.74rem;margin-bottom:10px;
font-variant-numeric:tabular-nums;display:none;}
.pulse{display:none;gap:5px;margin-bottom:12px;align-items:center;}
.pulse span{width:6px;height:6px;border-radius:50%;background:#25d366;
animation:pl .65s ease infinite alternate;}
.pulse span:nth-child(2){animation-delay:.2s;}.pulse span:nth-child(3){animation-delay:.4s;}
@keyframes pl{from{opacity:.15;transform:scale(.5);}to{opacity:1;transform:scale(1.5);}}
.ltxt{color:#25d366;font-size:.72rem;display:none;margin-bottom:8px;
animation:bk .9s infinite alternate;text-align:center;}
@keyframes bk{from{opacity:.3;}to{opacity:1;}}
.bcall{width:70px;height:70px;border-radius:50%;background:#25d366;border:none;
cursor:pointer;display:flex;align-items:center;justify-content:center;
box-shadow:0 6px 24px rgba(37,211,102,.55);animation:pg 1.8s ease infinite;}
@keyframes pg{0%,100%{box-shadow:0 0 0 0 rgba(37,211,102,.6);}
70%{box-shadow:0 0 0 22px rgba(37,211,102,0);}}
.bcall:active{transform:scale(.92);}
.bend{width:70px;height:70px;border-radius:50%;background:#ff3b30;border:none;
cursor:pointer;align-items:center;justify-content:center;
box-shadow:0 6px 22px rgba(255,59,48,.5);display:none;}
.bend:active{transform:scale(.92);}
svg{width:28px;height:28px;fill:white;pointer-events:none;}
.lbl{color:rgba(255,255,255,.2);font-size:.66rem;margin-top:7px;}
.err{color:#ff5c6e;font-size:.72rem;margin-top:8px;text-align:center;display:none;}
</style>
</head>
<body>
<div class="card">
  <div class="shop">""" + biz_js + """</div>
  <div class="av" id="av">🏪</div>
  <div class="nm">কাস্টমার কেয়ার</div>
  <div class="st" id="st">কল করতে নিচের সবুজ বাটন চাপুন</div>
  <div class="tmr" id="tmr">00:00</div>
  <div class="pulse" id="pulse"><span></span><span></span><span></span></div>
  <div class="ltxt" id="ltxt">🎤 বলুন...</div>
  <button class="bcall" id="bcall" onclick="startCall()">
    <svg viewBox="0 0 24 24"><path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1-9.4 0-17-7.6-17-17 0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1L6.6 10.8z"/></svg>
  </button>
  <button class="bend" id="bend" onclick="endCall()">
    <svg viewBox="0 0 24 24"><path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.12-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z"/></svg>
  </button>
  <div class="lbl" id="lbl">📞 কল করুন</div>
  <div class="err" id="err"></div>
</div>
<script>
var CTX  = """" + ctx_js + """";
var VAPI = """" + VOICE_API_URL.rstrip("/") + """";
var active=false, rec=null, sec=0, tid=null, busy=false, audioCtx=null, ringTmr=null;

function $(i){return document.getElementById(i);}
function setSt(t,g){$("st").textContent=t;$("st").className="st"+(g?" g":"");}
function showP(v){$("pulse").style.display=v?"flex":"none";}
function showL(v){$("ltxt").style.display=v?"block":"none";}
function showErr(t){var e=$("err");e.innerHTML=t;e.style.display=t?"block":"none";}

function getAC(){
  if(!audioCtx)audioCtx=new(window.AudioContext||window.webkitAudioContext)();
  if(audioCtx.state==="suspended")audioCtx.resume();
  return audioCtx;
}

function playRing(){
  var c=getAC();
  function tone(f,s,d){
    var o=c.createOscillator(),g=c.createGain();
    o.connect(g);g.connect(c.destination);o.type="sine";o.frequency.value=f;
    var t=c.currentTime+s;
    g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.12,t+.06);
    g.gain.setValueAtTime(.12,t+d-.06);g.gain.linearRampToValueAtTime(0,t+d);
    o.start(t);o.stop(t+d+.1);
  }
  function ring(){tone(440,0,.45);tone(480,.05,.45);tone(440,.72,.45);tone(480,.77,.45);}
  ring();
  ringTmr=setInterval(ring,2800);
}
function stopRing(){if(ringTmr){clearInterval(ringTmr);ringTmr=null;}}

function playB64(b64){
  try{
    var c=getAC(),bin=atob(b64),buf=new ArrayBuffer(bin.length),v=new Uint8Array(buf);
    for(var i=0;i<bin.length;i++)v[i]=bin.charCodeAt(i);
    c.decodeAudioData(buf,
      function(dec){
        var s=c.createBufferSource();s.buffer=dec;s.connect(c.destination);
        s.onended=function(){busy=false;showP(false);if(active){setSt("বলুন...",true);showL(true);startListen();}};
        s.start(0);
      },
      function(){busy=false;if(active)startListen();}
    );
  }catch(e){busy=false;if(active)startListen();}
}

function speakFallback(text){
  if(!window.speechSynthesis){busy=false;if(active)startListen();return;}
  window.speechSynthesis.cancel();
  var u=new SpeechSynthesisUtterance(text||"জ্বি বলুন।");
  u.lang="bn-IN";u.rate=0.9;u.volume=1;
  var vs=window.speechSynthesis.getVoices();
  var bn=vs.find(function(v){return v.lang&&(v.lang.startsWith("bn")||v.lang.startsWith("hi"));});
  if(bn)u.voice=bn;
  u.onend=function(){busy=false;showP(false);if(active){setSt("বলুন...",true);showL(true);startListen();}};
  u.onerror=function(){busy=false;if(active)startListen();};
  var fx=setInterval(function(){if(!window.speechSynthesis.speaking)clearInterval(fx);else window.speechSynthesis.resume();},3000);
  window.speechSynthesis.speak(u);
}

function speak(data){
  busy=true;showP(true);showL(false);setSt("বলছে...",true);
  if(data.audio&&data.audio.length>100){playB64(data.audio);}
  else{speakFallback(data.reply||"জ্বি বলুন।");}
}

var GKEY = """" + gkey_js + """";
var SYS = "তুমি একজন বাংলাদেশী দোকানের কাস্টমার কেয়ার। কখনো বলবে না তুমি AI। জ্বি ভাই/আপু বলো। সর্বোচ্চ ২-৩ বাক্যে উত্তর দাও। সবসময় বাংলায়। দোকানের তথ্য: " + CTX;

async function geminiCall(msg){
  try{
    var prompt = SYS + "\n\nকাস্টমার: " + msg + "\n\nউত্তর:";
    var r = await fetch(
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key="+GKEY,
      {method:"POST",headers:{"Content-Type":"application/json"},
       body:JSON.stringify({contents:[{parts:[{text:prompt}]}],generationConfig:{temperature:0.85,maxOutputTokens:100}})}
    );
    if(!r.ok) throw new Error("HTTP "+r.status);
    var d = await r.json();
    var txt = d.candidates[0].content.parts[0].text.trim().replace(/\[.*?\]/gs,"").trim();
    return {reply: txt, audio: ""};
  }catch(e){return {reply:"জ্বি বলুন, কীভাবে সাহায্য করতে পারি?",audio:""};}}

async function apiCall(ep,msg){
  if(ep==="greet"){
    return await geminiCall("কাস্টমার এইমাত্র কল করেছে। আন্তরিকভাবে আসসালামু আলাইকুম বলো, নিজেকে কাস্টমার কেয়ার হিসেবে পরিচয় দাও, কীভাবে সাহায্য করতে পারো জিজ্ঞেস করো।");
  }
  return await geminiCall(msg);
}

function startListen(){
  if(!active||busy)return;
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){setSt("Chrome এ খুলুন",false);showErr("Voice সাপোর্ট নেই — Chrome browser ব্যবহার করুন");return;}
  try{
    if(rec){try{rec.abort();}catch(e){}}
    rec=new SR();
    rec.lang="bn-IN";rec.continuous=false;rec.interimResults=true;rec.maxAlternatives=1;
    rec.onstart=function(){setSt("বলুন...",true);showL(true);showErr("");};
    rec.onresult=function(e){
      var txt="",fin=false;
      for(var i=e.resultIndex;i<e.results.length;i++){
        if(e.results[i].isFinal){txt+=e.results[i][0].transcript;fin=true;}
        else setSt("শুনছি: "+e.results[i][0].transcript,true);
      }
      if(fin&&txt.trim()){
        showL(false);setSt("বুঝছি...",false);
        if(rec){try{rec.abort();}catch(ex){}}
        apiCall("chat",txt.trim()).then(speak);
      }
    };
    rec.onend=function(){showL(false);if(active&&!busy)setTimeout(startListen,600);};
    rec.onerror=function(ev){
      showL(false);
      if(ev.error==="not-allowed"||ev.error==="permission-denied"){
        showErr("⚠️ মাইক্রোফোন Allow করুন<br>Address bar এ 🔒 ক্লিক → Allow → Reload");
        active=false;endCall();return;
      }
      if(ev.error==="network"){showErr("নেটওয়ার্ক সমস্যা। আবার চেষ্টা করুন।");}
      if(active&&!busy)setTimeout(startListen,1200);
    };
    rec.start();
  }catch(e){if(active&&!busy)setTimeout(startListen,1500);}
}

function startCall(){
  getAC();
  showErr("");
  $("bcall").style.display="none";
  $("av").className="av ring";
  setSt("রিং হচ্ছে...",false);
  $("lbl").textContent="সংযুক্ত হচ্ছে...";
  playRing();
  setTimeout(function(){
    stopRing();active=true;
    $("av").className="av live";
    $("bend").style.display="flex";
    $("tmr").style.display="block";
    $("lbl").textContent="📵 কাটুন";
    setSt("সংযুক্ত",true);
    tid=setInterval(function(){
      sec++;
      var m=String(Math.floor(sec/60)).padStart(2,"0"),s=String(sec%60).padStart(2,"0");
      $("tmr").textContent=m+":"+s;
    },1000);
    apiCall("greet","").then(speak);
  },2000);
}

function endCall(){
  active=false;busy=false;stopRing();
  if(tid){clearInterval(tid);tid=null;}
  if(rec){try{rec.abort();}catch(e){}}
  if(window.speechSynthesis)window.speechSynthesis.cancel();
  $("av").className="av";
  $("bend").style.display="none";
  $("bcall").style.display="flex";
  $("tmr").style.display="none";
  showP(false);showL(false);
  setSt("কল শেষ। আবার করতে পারেন।",false);
  $("lbl").textContent="📞 আবার কল করুন";
  sec=0;
}

if(window.speechSynthesis){
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged=function(){window.speechSynthesis.getVoices();};
}
</script>
</body></html>"""

    _cv1.html(html, height=700, scrolling=True)


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
                    st.session_state.phone = phone
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
            <div style='background:rgba(37,211,102,0.07);border:1px solid rgba(37,211,102,0.25);border-radius:10px;padding:10px 14px;margin:10px 0;'>
              <p style='color:#25d366;font-size:0.85rem;font-weight:700;margin:0;'>🎉 সম্পূর্ণ বিনামূল্যে!</p>
              <p style='color:rgba(37,211,102,0.6);font-size:0.75rem;margin:2px 0 0;'>রেজিস্ট্রেশন করলেই শুরু — কোনো পেমেন্ট লাগবে না।</p>
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
                        st.success("🎉 অ্যাকাউন্ট তৈরি হয়েছে!")
                        st.balloons()
                    elif status == "EXISTS":
                        st.warning("⚠️ এই নম্বরে আগে থেকে অ্যাকাউন্ট আছে।")
                    else:
                        st.error(f"🚨 {status.replace('ERROR:','').strip()}")
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

def dashboard():
    phone     = st.session_state.phone
    user_data = get_or_create_user(phone)
    owner_phone, biz_name, email, expiry, status = user_data

    profile     = load_profile(owner_phone)
    p_name      = profile.get("owner_name", "") or biz_name
    p_company   = profile.get("company_name", "") or biz_name

    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<h3 style='font-family:Syne;color:#38d9ff;text-align:center;font-size:1rem;letter-spacing:2px;text-transform:uppercase;'>⚡ কন্ট্রোল প্যানেল</h3>", unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)

        # ── প্রোফাইল কার্ড ──
        st.markdown(f"""
        <div style='background:rgba(56,217,255,0.05);border:1px solid rgba(56,217,255,0.1);border-radius:14px;padding:14px 16px;margin-bottom:10px;'>
          <div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;'>
            <div style='width:42px;height:42px;border-radius:50%;background:linear-gradient(135deg,#38d9ff,#2563ff);display:flex;align-items:center;justify-content:center;font-size:1.3rem;'>🏪</div>
            <div>
              <p style='color:#e2eeff;font-weight:700;font-size:0.88rem;margin:0;'>{p_company}</p>
              <p style='color:rgba(140,180,255,0.5);font-size:0.72rem;margin:0;'>{owner_phone}</p>
            </div>
          </div>
          <span style='display:inline-block;background:linear-gradient(135deg,rgba(37,211,102,0.15),rgba(0,200,80,0.08));border:1px solid rgba(37,211,102,0.35);color:#25d366;border-radius:8px;padding:3px 12px;font-size:0.72rem;font-weight:700;letter-spacing:1px;'>✅ FREE</span>
        </div>
        """, unsafe_allow_html=True)

        # ── প্রোফাইল এডিট ──
        with st.expander("✏️ প্রোফাইল এডিট করুন"):
            new_owner   = st.text_input("আপনার নাম", value=p_name, key="p_owner")
            new_company = st.text_input("কোম্পানির নাম", value=p_company, key="p_company")
            if st.button("💾 প্রোফাইল সেভ", key="save_prof"):
                save_profile(owner_phone, {"owner_name": new_owner, "company_name": new_company})
                st.success("✅ প্রোফাইল সেভ হয়েছে!")
                time.sleep(0.4); st.rerun()
        # ── সম্পূর্ণ বিনামূল্যে — কোনো মেয়াদ নেই ──
        st.markdown("""
        <div style='background:rgba(37,211,102,0.07);border:1px solid rgba(37,211,102,0.2);
        border-radius:13px;padding:12px 16px;margin-bottom:14px;text-align:center;'>
          <p style='color:#25d366;font-size:.82rem;font-weight:700;margin:0;'>🎉 সম্পূর্ণ বিনামূল্যে</p>
          <p style='color:rgba(37,211,102,0.5);font-size:.7rem;margin:3px 0 0;'>কোনো পেমেন্ট লাগবে না</p>
        </div>
        """, unsafe_allow_html=True)
        short_link = get_short_link(owner_phone)
        st.markdown("""<p style='font-size:0.7rem;color:rgba(140,180,255,0.45);text-transform:uppercase;
        letter-spacing:1.5px;margin-bottom:6px;'>🔗 কাস্টমার কল লিংক</p>""", unsafe_allow_html=True)
        st.markdown(f"""
        <div style='background:rgba(37,211,102,0.07);border:2px solid rgba(37,211,102,0.3);
        border-radius:14px;padding:14px;margin-bottom:6px;'>
          <p style='color:#25d366;font-size:.7rem;font-weight:700;margin-bottom:6px;letter-spacing:1px;'>
          📞 এই লিংকটি কাস্টমারকে দিন</p>
          <div style='background:rgba(0,0,0,.3);border-radius:8px;padding:10px;
          font-family:monospace;font-size:.72rem;color:#38d9ff;word-break:break-all;
          cursor:pointer;border:1px solid rgba(56,217,255,.15);'
          onclick="navigator.clipboard.writeText('{short_link}');
          this.innerHTML='✅ কপি হয়েছে!';
          setTimeout(()=>this.innerHTML='{short_link}',2500);"
          title="ক্লিক করলে কপি হবে">
            {short_link}
          </div>
          <p style='color:rgba(37,211,102,.5);font-size:.65rem;margin-top:6px;'>
          👆 ক্লিক করলে কপি হবে<br>Facebook/WhatsApp এ শেয়ার করুন</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div class='btn-danger'>", unsafe_allow_html=True)
        if st.button("🔴 লগআউট"):
            st.session_state.logged_in = False
            st.session_state.phone = None
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="page-header" style="padding-top:1rem;">
      <h1>GLOBAL AI WORKSPACE</h1>
      <p>আপনার ব্যবসার সম্পূর্ণ AI কন্ট্রোল প্যানেল</p>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊  ড্যাশবোর্ড","📞  কল সেন্টার","🧠  AI ট্রেনিং","🛍️  ইনভেন্টরি","📦  অর্ডার ভল্ট"
    ])

    with tab1:
        df = get_all_orders(owner_phone)
        total_sales = int(df['total_amount'].sum()) if df is not None and not df.empty and 'total_amount' in df.columns else 0
        total_calls = len(df) if df is not None and not df.empty else 0
        real_orders = len(df[df['status'].str.contains('REAL', na=False)]) if df is not None and not df.empty and 'status' in df.columns else 0
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
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",margin=dict(l=0,r=0,t=8,b=0))
            fig.update_traces(fillcolor="rgba(56,217,255,0.07)",line=dict(color="#38d9ff",width=2))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("<div style='text-align:center;padding:3rem 0;'><p style='font-size:2.5rem;'>📡</p><p style='color:rgba(140,180,255,0.4);font-size:.88rem;'>এখনো কোনো ডাটা নেই।<br>কাস্টমার লিংক শেয়ার করুন।</p></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        if df is not None and not df.empty:
            st.markdown("<div class='g-card'>", unsafe_allow_html=True)
            st.markdown("<p class='sec-head' style='color:#f59e0b;'>⚡ সাম্প্রতিক অর্ডার</p>", unsafe_allow_html=True)
            show_cols = [c for c in ['customer_name','customer_phone','district','total_amount','trust_score','status','order_date'] if c in df.columns]
            st.dataframe(df[show_cols].head(10), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

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

    with tab3:
        st.markdown("<div class='g-card'>", unsafe_allow_html=True)
        st.markdown("<p class='sec-head' style='color:#fbbf24;'>🧠 দোকানের তথ্য ও নিয়মকানুন</p>", unsafe_allow_html=True)
        st.markdown("<p style='color:rgba(140,190,255,0.45);font-size:.82rem;margin-bottom:12px;'>এই তথ্য AI পড়বে এবং কাস্টমারকে সঠিক উত্তর দেবে।</p>", unsafe_allow_html=True)
        rules = st.text_area("ডেলিভারি চার্জ, রিটার্ন পলিসি, বিশেষ অফার লিখুন:",
            value=st.session_state.shop_rules, height=120,
            placeholder="যেমন: ঢাকার ভেতরে ডেলিভারি ৬০ টাকা, বাইরে ১২০ টাকা...")
        st.markdown("<div class='btn-primary'>", unsafe_allow_html=True)
        if st.button("💾 সেভ করুন", key="save_rules"):
            save_user_memory(phone, rules)
            st.session_state.shop_rules = rules
            st.success("✅ AI-এর মেমোরি আপডেট হয়েছে!")
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with tab4:
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

    with tab5:
        st.markdown("<div class='g-card'>", unsafe_allow_html=True)
        st.markdown("<p class='sec-head' style='color:#a855f7;'>📦 কাস্টমার অর্ডার ভল্ট</p>", unsafe_allow_html=True)
        df_v = get_all_orders(owner_phone)
        if df_v is not None and not df_v.empty:
            show = [c for c in ['customer_name','customer_phone','village','district','quantity','total_amount','trust_score','status','order_date'] if c in df_v.columns]
            st.dataframe(df_v[show] if show else df_v, use_container_width=True)
            csv = df_v.to_csv(index=False).encode('utf-8')
            st.download_button("📥 CSV ডাউনলোড করুন", csv, "orders.csv", "text/csv", key="dl_csv")
        else:
            st.markdown("<div style='text-align:center;padding:3rem 0;'><p style='font-size:3rem;'>📭</p><p style='color:rgba(140,180,255,0.35);font-size:.85rem;'>কোনো অর্ডার নেই।</p></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

def main():
    qp = st.query_params

    # ১. কাস্টমার লিংক — ?shop=PHONE
    #    লগইন নেই, সরাসরি call UI দেখাবে
    if "shop" in qp:
        shop = str(qp["shop"]).strip()
        customer_page(shop)
        return

    # ২. অ্যাডমিন — লগইন প্রয়োজন
    if not st.session_state.get("logged_in", False):
        auth_page()
        return
    dashboard()

# ════════════════════════════════════════════════════════
#  Flask API — /chat এবং /greet endpoint
#  Streamlit এর সাথেই চলবে, আলাদা server লাগবে না
# ════════════════════════════════════════════════════════
from flask import Flask, request, jsonify
from threading import Thread
import io as _fio, base64 as _fb64

_flask = Flask(__name__)

def _flask_get_reply(message, shop_context):
    import re
    gkey = _get_secret("GEMINI_API_KEY")
    grkey = _get_secret("GROQ_API_KEY")
    sys_prompt = (
        "তুমি একজন বাংলাদেশী দোকানের অভিজ্ঞ কাস্টমার কেয়ার প্রতিনিধি। "
        "তুমি কখনো বলবে না যে তুমি AI বা রোবট। "
        "কেউ সালাম দিলে আগে ওয়ালাইকুম আসসালাম বলো। "
        "জ্বি ভাই/আপু বলো। সর্বোচ্চ ২-৩ বাক্যে উত্তর দাও। সবসময় বাংলায়।"
    )
    prompt = sys_prompt + f"\n\n[দোকান]: {shop_context[:300]}\n\nকাস্টমার: {message}\n\nউত্তর:"
    if gkey:
        try:
            import requests as _r
            r = _r.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={gkey}",
                json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.85,"maxOutputTokens":100}},
                timeout=15)
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return re.sub(r"\[.*?\]","",txt,flags=re.DOTALL).strip()
        except: pass
    if grkey:
        try:
            import requests as _r
            r = _r.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":f"Bearer {grkey}","Content-Type":"application/json"},
                json={"model":"llama3-8b-8192","messages":[{"role":"system","content":sys_prompt},{"role":"user","content":message}],"max_tokens":100},
                timeout=15)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except: pass
    return "জ্বি বলুন, কীভাবে সাহায্য করতে পারি?"

def _flask_to_audio(text):
    try:
        from gtts import gTTS
        tts = gTTS(text=text[:400], lang="bn", slow=False)
        buf = _fio.BytesIO()
        tts.write_to_fp(buf); buf.seek(0)
        return _fb64.b64encode(buf.read()).decode()
    except: return ""

@_flask.route("/chat", methods=["POST"])
def _flask_chat():
    d = request.get_json(force=True) or {}
    reply = _flask_get_reply(d.get("message",""), d.get("shop_context",""))
    return jsonify({"reply": reply, "audio": _flask_to_audio(reply)})

@_flask.route("/greet", methods=["POST"])
def _flask_greet():
    d = request.get_json(force=True) or {}
    msg = "কাস্টমার কল করেছে। আন্তরিকভাবে আসসালামু আলাইকুম বলো, কাস্টমার কেয়ার হিসেবে পরিচয় দাও, কীভাবে সাহায্য করতে পারো জিজ্ঞেস করো।"
    reply = _flask_get_reply(msg, d.get("shop_context",""))
    return jsonify({"reply": reply, "audio": _flask_to_audio(reply)})

@_flask.route("/health")
def _flask_health():
    return jsonify({"ok": True})

def _run_flask():
    _flask.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)

# Flask কে background এ চালাও
_t = Thread(target=_run_flask, daemon=True)
_t.start()

if __name__ == "__main__":
    main()



