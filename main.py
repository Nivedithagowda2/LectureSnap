import os, io, uuid, json, textwrap, tempfile, math, time, subprocess, shutil
import urllib.request, urllib.error, urllib.parse
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont
import fitz

load_dotenv()

app = FastAPI(title="LectureSnap")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

B2_KEY_ID      = os.getenv("B2_KEY_ID")
B2_APP_KEY     = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
B2_ENDPOINT    = os.getenv("B2_ENDPOINT")
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY        = os.getenv("GROQ_API_KEY")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

TOPIC_COLORS = [
    (99,102,241),(16,185,129),(139,92,246),
    (245,158,11),(6,182,212),(244,63,94),
]
def topic_color(tid): return TOPIC_COLORS[(tid-1)%len(TOPIC_COLORS)]

# ── B2 ────────────────────────────────────────────────────────
def get_b2():
    return boto3.client("s3",endpoint_url=B2_ENDPOINT,
        aws_access_key_id=B2_KEY_ID,aws_secret_access_key=B2_APP_KEY,
        config=Config(signature_version="s3v4"))
def upload_to_b2(path,key,ct): get_b2().upload_file(path,B2_BUCKET_NAME,key,ExtraArgs={"ContentType":ct})
def upload_bytes_to_b2(data,key,ct): get_b2().put_object(Bucket=B2_BUCKET_NAME,Key=key,Body=data,ContentType=ct)
def download_from_b2(key):
    sfx=Path(key).suffix or ".tmp"
    with tempfile.NamedTemporaryFile(delete=False,suffix=sfx) as t: path=t.name
    get_b2().download_file(B2_BUCKET_NAME,key,path); return path


def stream_from_b2(key: str) -> StreamingResponse:
    obj = get_b2().get_object(Bucket=B2_BUCKET_NAME, Key=key)
    body = obj["Body"]

    def iter_bytes():
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

    filename = Path(key).name
    return StreamingResponse(
        iter_bytes(),
        media_type=obj.get("ContentType", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# ── FONT ──────────────────────────────────────────────────────
def font(size,bold=False):
    paths=[
        f"C:\\Windows\\Fonts\\{'arialbd' if bold else 'arial'}.ttf",
        f"C:\\Windows\\Fonts\\{'calibrib' if bold else 'calibri'}.ttf",
        f"C:\\Windows\\Fonts\\{'segoeuib' if bold else 'segoeui'}.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf".format("-Bold" if bold else ""),
        "/usr/share/fonts/truetype/liberation/LiberationSans-{}.ttf".format("Bold" if bold else "Regular"),
    ]
    for p in paths:
        try: return ImageFont.truetype(p,size)
        except: continue
    return ImageFont.load_default()

# ══════════════════════════════════════════════════════════════
# WEEK 1 — EXTRACT
# ══════════════════════════════════════════════════════════════
def extract_pdf(path):
    doc=fitz.open(path); pages,full=[],""
    for i in range(len(doc)):
        t=doc[i].get_text().strip()
        pages.append({"page":i+1,"text":t}); full+=t+"\n"
    total=len(pages); gs=max(1,total//8); secs=[]
    for i in range(0,total,gs):
        g=pages[i:i+gs]
        secs.append({"start_page":g[0]["page"],"end_page":g[-1]["page"],"text":" ".join(p["text"] for p in g)})
    return {"source_type":"pdf","full_text":full,"total_pages":total,"pages":pages,"sections":secs}

def transcribe_audio(path):
    import openai; c=openai.OpenAI(api_key=OPENAI_API_KEY)
    with open(path,"rb") as f:
        r=c.audio.transcriptions.create(model="whisper-1",file=f,response_format="verbose_json",timestamp_granularities=["segment"])
    return {"source_type":"audio","full_text":r.text,
            "segments":[{"start":round(s.start,2),"end":round(s.end,2),"text":s.text.strip()} for s in r.segments]}

AUDIO={".mp3",".wav",".m4a",".ogg",".flac"}
VIDEO={".mp4",".mov",".avi",".webm",".mkv"}
PDF={".pdf"}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    name=file.filename or "upload"; ext=Path(name).suffix.lower()
    if ext in PDF: ft,ct="pdf","application/pdf"
    elif ext in VIDEO: ft,ct="video","video/mp4"
    elif ext in AUDIO: ft,ct="audio","audio/mpeg"
    else: raise HTTPException(400,f"Unsupported type '{ext}'.")
    sid=str(uuid.uuid4()); tp=jp=mp=None
    try:
        with tempfile.NamedTemporaryFile(delete=False,suffix=ext) as t:
            t.write(await file.read()); tp=t.name
        b2o=f"recordings/{sid}/input/original{ext}"; upload_to_b2(tp,b2o,ct)
        ex=extract_pdf(tp) if ft=="pdf" else transcribe_audio(tp)
        with tempfile.NamedTemporaryFile(mode="w",delete=False,suffix=".json",encoding="utf-8") as j:
            json.dump(ex,j,indent=2,ensure_ascii=False); jp=j.name
        b2t=f"recordings/{sid}/processing/extracted_text.json"; upload_to_b2(jp,b2t,"application/json")
        wc=len(ex["full_text"].split())
        meta={"session_id":sid,"original_filename":name,"file_type":ft,"status":"extracted",
              "b2_original":b2o,"b2_text":b2t,
              "stats":{"source_type":ft,"word_count":wc,
                       **({"total_pages":ex["total_pages"]} if ft=="pdf" else {}),
                       **({"segments":len(ex.get("segments",[]))} if ft!="pdf" else {})}}
        with tempfile.NamedTemporaryFile(mode="w",delete=False,suffix=".json",encoding="utf-8") as m:
            json.dump(meta,m,indent=2); mp=m.name
        upload_to_b2(mp,f"recordings/{sid}/metadata.json","application/json")
        preview=ex["full_text"][:2000]+"\n\n[... truncated ...]" if len(ex["full_text"])>2000 else ex["full_text"]
        return {"session_id":sid,"file_type":ft,"status":"success","stats":meta["stats"],"preview":preview}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500,str(e))
    finally:
        for p in [tp,jp,mp]:
            if p and os.path.exists(p):
                try: os.unlink(p)
                except: pass

# ══════════════════════════════════════════════════════════════
# WEEK 2 — STRUCTURE
# ══════════════════════════════════════════════════════════════
def build_condensed(ex):
    src=ex.get("source_type","pdf")
    if src=="pdf" and ex.get("sections"):
        return "\n\n".join(f"[Pages {s['start_page']}-{s['end_page']}]: {' '.join(s['text'].split()[:200])}"
                           for s in ex["sections"])
    elif src=="audio" and ex.get("segments"):
        segs=ex["segments"]; chunk=max(1,len(segs)//6); parts=[]
        for i in range(0,len(segs),chunk):
            g=segs[i:i+chunk]; text=" ".join(s["text"] for s in g)
            parts.append(f"[{g[0]['start']:.0f}s-{g[-1]['end']:.0f}s]: {' '.join(text.split()[:200])}")
        return "\n\n".join(parts)
    return " ".join(ex.get("full_text","").split()[:1000])

def call_groq(condensed,src):
    if not GROQ_API_KEY: raise HTTPException(500,"GROQ_API_KEY missing.")
    pos="page range" if src=="pdf" else "time range"
    prompt=f"""You are an expert teacher creating educational slide content.

Analyze this document and select only 4 to 5 of the MOST IMPORTANT topics.
For each topic generate rich educational content that helps students truly understand the concept.

Return ONLY this JSON (no markdown, no explanation):
{{
  "document_title": "clear title of this document",
  "summary": "2 sentence overview of entire document",
  "topics": [
    {{
      "id": 1,
      "title": "Topic Name",
      "concept": "Simple 1-2 sentence explanation of WHAT this concept is and WHY it matters to a student",
      "key_points": [
        "First important point explained clearly with details and examples",
        "Second important point explained clearly with details and examples",
        "Third important point explained clearly with details and examples",
        "Fourth important point explained clearly with details and examples"
      ],
      "key_fact": "One memorable specific fact, number, or real example from the document",
      "position": "{pos} here",
      "image_keyword": "3-4 specific nature words for photo search e.g. forest trees sunlight"
    }}
  ]
}}

Rules:
- Select ONLY 4-5 most important topics (not all topics)
- concept must explain the topic simply like a teacher to a student
- key_points must be EDUCATIONAL and DETAILED not just copied text fragments
- key_fact must be a specific fact from the document with a real number or example
- image_keyword must describe a REAL NATURE PHOTOGRAPH e.g. "green forest trees", "river water flowing", "solar panels field", "coal mining dark" — be specific and visual
- Return ONLY JSON

Document:
{condensed}"""

    payload=json.dumps({"model":"llama-3.1-8b-instant",
        "messages":[{"role":"system","content":"You are an expert teacher. Return ONLY valid JSON. No markdown."},
                    {"role":"user","content":prompt}],
        "temperature":0.3,"max_tokens":2000}).encode("utf-8")

    req=urllib.request.Request("https://api.groq.com/openai/v1/chat/completions",data=payload,
        headers={"Content-Type":"application/json","Authorization":f"Bearer {GROQ_API_KEY}",
                 "User-Agent":"LectureSnap/1.0","Accept":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=60) as resp:
            result=json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise HTTPException(500,f"Groq error {e.code}: {e.read().decode()}")

    raw=result["choices"][0]["message"]["content"].strip()
    if "```" in raw:
        raw="\n".join(l for l in raw.split("\n") if not l.strip().startswith("```")).strip()
    s,e=raw.find("{"),raw.rfind("}")+1
    if s==-1: raise HTTPException(500,"Groq returned invalid JSON. Try again.")
    return json.loads(raw[s:e])

@app.post("/api/structure/{session_id}")
async def structure(session_id:str):
    tp=pp=None
    try:
        tp=download_from_b2(f"recordings/{session_id}/processing/extracted_text.json")
        with open(tp,encoding="utf-8") as f: ex=json.load(f)
        src=ex.get("source_type","pdf")
        data=call_groq(build_condensed(ex),src)
        data.update({"session_id":session_id,"source_type":src,"status":"structured"})
        with tempfile.NamedTemporaryFile(mode="w",delete=False,suffix=".json",encoding="utf-8") as pf:
            json.dump(data,pf,indent=2,ensure_ascii=False); pp=pf.name
        upload_to_b2(pp,f"recordings/{session_id}/processing/topics.json","application/json")
        return {"session_id":session_id,"status":"success",
                "document_title":data.get("document_title",""),
                "summary":data.get("summary",""),
                "topics":data.get("topics",[]),
                "topic_count":len(data.get("topics",[]))}
    except HTTPException: raise
    except json.JSONDecodeError as e: raise HTTPException(500,f"Invalid JSON — try again. ({e})")
    except Exception as e: raise HTTPException(500,str(e))
    finally:
        for p in [tp,pp]:
            if p and os.path.exists(p):
                try: os.unlink(p)
                except: pass

# ══════════════════════════════════════════════════════════════
# WEEK 3 — SLIDE GENERATION WITH REAL PHOTOS
# ══════════════════════════════════════════════════════════════

def fetch_real_photo(keyword:str, topic_id:int):
    """
    Try multiple sources for real photographs.
    Uses flux-realism model on Pollinations for photorealistic output.
    """
    time.sleep(2)  # avoid rate limiting

    # ── Try 1: Pollinations flux-realism (photorealistic AI photos) ──
    prompt = urllib.parse.quote(
        f"ultra realistic photograph of {keyword}, "
        f"DSLR camera shot, natural lighting, outdoor, high quality, "
        f"vibrant colors, photorealistic, nature photography, no text, no people"
    )
    models = ["flux-realism", "flux"]
    for model in models:
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=520&height=720&nologo=true&seed={topic_id*23}&model={model}"
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/jpeg,image/png,image/*",
                    "Accept-Language": "en-US,en;q=0.9",
                })
                with urllib.request.urlopen(req, timeout=45) as r:
                    data = r.read()
                    if len(data) > 5000:
                        return data
            except Exception:
                if attempt == 0: time.sleep(3)

    return None  # geometric art fallback


def draw_art(draw,x0,w,h,color,tid):
    r,g,b=color
    dark=tuple(max(0,c-110) for c in color)
    mid=tuple(max(0,c-55) for c in color)
    lite=tuple(min(255,c+70) for c in color)
    cx,cy=x0+w//2,h//2
    for i in range(24):
        t=i/24; br=int(dark[0]+(mid[0]-dark[0])*t); bg2=int(dark[1]+(mid[1]-dark[1])*t); bb=int(dark[2]+(mid[2]-dark[2])*t)
        bx=x0+int(i*w/24); draw.rectangle([bx,0,bx+w//24+2,h],fill=(br,bg2,bb))
    for rad,alpha in [(min(w,h)//2-20,180),(min(w,h)*7//20,120),(min(w,h)*2//5,80)]:
        draw.ellipse([cx-rad,cy-rad,cx+rad,cy+rad],outline=(*color,alpha),width=2)
    r4=min(w,h)//5; draw.ellipse([cx-r4,cy-r4,cx+r4,cy+r4],fill=mid)
    r5=r4//2; draw.ellipse([cx-r5,cy-r5,cx+r5,cy+r5],fill=color)
    r_inner=r5+4; r_outer=min(w,h)*7//20-8
    for deg in range(0,360,30):
        a=math.radians(deg)
        draw.line([cx+int(r_inner*math.cos(a)),cy+int(r_inner*math.sin(a)),
                   cx+int(r_outer*math.cos(a)),cy+int(r_outer*math.sin(a))],fill=(*color,90),width=1)
    r_orbit=min(w,h)//2-24
    for i in range(8):
        a=math.radians(i*45+tid*18)
        draw.ellipse([cx+int(r_orbit*math.cos(a))-7,cy+int(r_orbit*math.sin(a))-7,
                      cx+int(r_orbit*math.cos(a))+7,cy+int(r_orbit*math.sin(a))+7],fill=lite)
    r_ring=min(w,h)//2-18
    for gx in range(x0+14,x0+w-14,26):
        for gy in range(14,h-14,26):
            dist=math.sqrt((gx-cx)**2+(gy-cy)**2)
            if dist>r_ring+8:
                alpha=max(0,1-(dist-r_ring)/70); dc=tuple(int(c*alpha) for c in color)
                if sum(dc)>8: draw.ellipse([gx-2,gy-2,gx+2,gy+2],fill=dc)
    wf=font(56,True); wt=str(tid); bb=draw.textbbox((0,0),wt,font=wf)
    draw.text((cx-(bb[2]-bb[0])//2,cy-(bb[3]-bb[1])//2),wt,
              fill=(*tuple(min(255,c+90) for c in color),210),font=wf)


def create_slide(topic,img_bytes):
    W,H=1280,720
    BG=(8,12,24); PANEL=(13,20,40); WHITE=(241,245,249); MUTED=(100,116,139); FACT_BG=(20,30,58)
    color=topic_color(topic.get("id",1))

    canvas=Image.new("RGB",(W,H),BG)
    draw=ImageDraw.Draw(canvas)
    RX=730

    # ── Right panel: real photo or geometric art ──────────────
    draw.rectangle([RX,0,W,H],fill=PANEL)
    if img_bytes:
        try:
            img=Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((W-RX,H),Image.LANCZOS)
            # Subtle dark overlay so text panel stays readable
            overlay=Image.new("RGB",(W-RX,H),(8,12,24))
            blended=Image.blend(img,overlay,0.15)   # 15% dark = mostly real photo
            canvas.paste(blended,(RX,0))
            # Very light color wash to tie photo to slide's color theme
            tint=Image.new("RGB",(W-RX,H),color)
            canvas.paste(Image.blend(canvas.crop((RX,0,W,H)),tint,0.08),(RX,0))
            draw=ImageDraw.Draw(canvas)
        except: img_bytes=None
    if not img_bytes:
        draw_art(draw,RX,W-RX,H,color,topic.get("id",1))
        draw=ImageDraw.Draw(canvas)

    # ── Left content panel ────────────────────────────────────
    draw.rectangle([0,0,RX,H],fill=PANEL)
    draw.rectangle([0,0,5,H],fill=color)
    draw.rectangle([0,0,RX,4],fill=color)
    draw.rectangle([RX-2,0,RX+2,H],fill=color)

    tid=topic.get("id",1)
    draw.rounded_rectangle([28,28,82,82],radius=14,fill=color)
    draw.text((42,38),str(tid),fill=WHITE,font=font(28,True))
    draw.text((94,46),topic.get("position",""),fill=MUTED,font=font(13))

    # Title
    title=topic.get("title","")
    wt=textwrap.fill(title,width=30)
    draw.text((28,96),wt,fill=WHITE,font=font(30,True))
    ty=104+(wt.count("\n")+1)*38

    # Concept
    concept=topic.get("concept","")
    if concept:
        wc=textwrap.fill(concept,width=56)
        draw.text((28,ty),wc,fill=tuple(min(255,c+60) for c in color),font=font(15))
        ty+=20+(wc.count("\n")+1)*20+6

    draw.rectangle([28,ty,RX-28,ty+1],fill=(22,32,58))
    ty+=12

    # Key points
    for pt in topic.get("key_points",[])[:4]:
        if ty>H-90: break
        draw.rounded_rectangle([28,ty+5,38,ty+15],radius=2,fill=tuple(min(255,c+40) for c in color))
        wpt=textwrap.fill(pt,width=55)
        draw.text((46,ty),wpt,fill=WHITE,font=font(15))
        ty+=22+(wpt.count("\n"))*18+8

    # Key fact box
    kfact=topic.get("key_fact","")
    if kfact and ty<H-70:
        box_y=H-62
        draw.rounded_rectangle([28,box_y,RX-28,H-16],radius=8,fill=FACT_BG)
        draw.rounded_rectangle([28,box_y,36,H-16],radius=8,fill=color)
        kfw=textwrap.fill(f"Key Fact: {kfact}",width=62)
        draw.text((44,box_y+8),kfw,fill=tuple(min(255,c+100) for c in color),font=font(13))

    draw.rectangle([0,H-34,W,H],fill=(5,8,16))
    draw.text((28,H-24),"LectureSnap",fill=color,font=font(13,True))
    draw.text((140,H-24),"AI Study Slides",fill=MUTED,font=font(13))
    draw.text((W-280,H-24),"Powered by Groq + Backblaze B2",fill=MUTED,font=font(12))

    out=io.BytesIO(); canvas.save(out,format="PNG",optimize=True)
    return out.getvalue()


@app.post("/api/slides/{session_id}")
async def generate_slides(session_id:str):
    tp=None
    try:
        tp=download_from_b2(f"recordings/{session_id}/processing/topics.json")
        with open(tp,encoding="utf-8") as f: tdata=json.load(f)
        topics=tdata.get("topics",[])
        if not topics: raise HTTPException(400,"No topics found. Run AI structuring first.")
        import base64; slides=[]
        for t in topics:
            tid=t.get("id",1)
            kw=t.get("image_keyword",t.get("title","nature"))
            img=fetch_real_photo(kw,tid)
            png=create_slide(t,img)
            key=f"recordings/{session_id}/slides/slide_{tid:02d}.png"
            upload_bytes_to_b2(png,key,"image/png")
            slides.append({"id":tid,"title":t.get("title",""),"position":t.get("position",""),
                           "had_image":img is not None,"b2_key":key,
                           "image_b64":base64.b64encode(png).decode("utf-8")})
        mf={"session_id":session_id,"slide_count":len(slides),
            "slides":[{"id":s["id"],"title":s["title"],"b2_key":s["b2_key"]} for s in slides]}
        upload_bytes_to_b2(json.dumps(mf,indent=2).encode(),
                           f"recordings/{session_id}/slides/manifest.json","application/json")
        return {"session_id":session_id,"status":"success","slide_count":len(slides),"slides":slides}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500,str(e))
    finally:
        if tp and os.path.exists(tp):
            try: os.unlink(tp)
            except: pass

@app.get("/",response_class=HTMLResponse)
async def root():
    with open("static/index.html",encoding="utf-8") as f: return f.read()

@app.get("/api/download/{path:path}")
async def download_file(path: str):
    key = urllib.parse.unquote(path)
    if not key.startswith("recordings/"):
        raise HTTPException(400, "Invalid download key")
    try:
        return stream_from_b2(key)
    except Exception as e:
        raise HTTPException(404, f"File not found: {e}")

app.mount("/static",StaticFiles(directory="static"),name="static")


# ════════════════════════════════════════════════════════════
# STEP 5 — TEACHER-STYLE SUMMARY VIDEO
# ════════════════════════════════════════════════════════════

# ── 5A: Write the teaching script (Groq) ───────────────────────────
def write_teaching_script(topics_data: dict) -> str:
    """Send topics JSON to Groq and get back a full spoken teaching script."""
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY missing.")

    topics = topics_data.get("topics", [])
    doc_title = topics_data.get("document_title", "this topic")
    topics_json = json.dumps(
        [{"id": t["id"], "title": t["title"], "concept": t.get("concept", ""),
          "key_points": t.get("key_points", []), "key_fact": t.get("key_fact", "")} for t in topics],
        indent=2
    )

    prompt = f"""You are an expert teacher explaining "{doc_title}" to a student who is learning it for the first time.

Write a natural, spoken lesson that sounds like a real teacher teaching in class.
The tone should be warm, clear, encouraging, and conversational.
Do NOT sound like a robot or a summary generator.

STYLE REQUIREMENTS:
- Speak directly to the student as if you are teaching them live.
- Use simple words first, then add deeper explanation.
- Explain what the idea means, why it matters, and how it connects to everyday life.
- Use analogies, comparisons, and real-world examples that make the concept easy to understand.
- Pause naturally with phrases like: "Let’s think about it this way...", "A good way to picture this is...", "Here’s the key idea...", "For example..."
- Make the explanation feel like a classroom lesson, not a list of bullets.
- Include one or two simple examples for each major topic so a student can truly understand it.
- End with a short summary that helps the student remember the main takeaway.

STRUCTURE:
- Start with a friendly introduction to the whole topic.
- Explain each topic step by step in a flowing lesson.
- Keep the pacing natural and educational.
- Make the lesson feel engaging and human.

OUTPUT RULES:
- Write ONLY the spoken script.
- No headings, no bullet points, no markdown, no labels like 'Topic 1'.
- Target 500-700 words so the explanation feels complete and rich.

Topics JSON:
{topics_json}

Write the complete teaching script now:"""

    payload = json.dumps({"model": "llama-3.1-8b-instant",
        "messages": [{"role": "system", "content": "You are an enthusiastic teacher. Write only the spoken script, no formatting."},
                     {"role": "user", "content": prompt}],
        "temperature": 0.7, "max_tokens": 1500}).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {GROQ_API_KEY}",
                 "User-Agent": "LectureSnap/1.0", "Accept": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise HTTPException(500, f"Groq error {e.code}: {e.read().decode()}")

    return result["choices"][0]["message"]["content"].strip()


# ── 5B: Generate voice with ElevenLabs ────────────────────────────────
def generate_voice_elevenlabs(script_text: str) -> bytes:
    """Call ElevenLabs TTS API and return MP3 bytes."""
    if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY == "your_elevenlabs_api_key_here":
        raise ValueError("ElevenLabs API key not configured")

    for model_id in ["eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_multilingual_v2"]:
        payload = json.dumps({
            "text": script_text,
            "model_id": model_id,
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8}
        }).encode("utf-8")

        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            data=payload,
            headers={"xi-api-key": ELEVENLABS_API_KEY,
                     "Content-Type": "application/json",
                     "Accept": "audio/mpeg",
                     "User-Agent": "LectureSnap/1.0"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            lower_body = body.lower()
            if "payment_required" in lower_body or "unsupported_model" in lower_body or "not available" in lower_body:
                continue
            raise ValueError(f"ElevenLabs error {e.code}: {body[:300]}")

    raise ValueError("ElevenLabs could not generate speech with the configured account")


def generate_voice_gtts_fallback(script_text: str) -> bytes:
    """Free Google TTS fallback — no API key, no quota."""
    from gtts import gTTS
    import io
    tts = gTTS(text=script_text, lang="en", slow=False)
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()


# ── 5C: Assemble video with ffmpeg ───────────────────────────────────
def get_audio_duration(audio_path: str) -> float:
    """Use ffprobe to get audio duration in seconds."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
            capture_output=True, text=True, timeout=30
        )
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except Exception:
        return 180.0  # safe fallback: 3 minutes


def assemble_video(slide_paths: list, audio_path: str, output_path: str, topics: list) -> None:
    """Assemble slides and narration into an MP4 using a simpler ffmpeg pipeline."""
    if not shutil.which("ffmpeg"):
        raise HTTPException(500,
            "ffmpeg not found on PATH. Install it: winget install ffmpeg  (Windows) "
            "or  apt install ffmpeg  (Linux). Then restart the server.")

    n = len(slide_paths)
    if n == 0:
        raise HTTPException(400, "No slides to assemble.")

    total_dur = get_audio_duration(audio_path)
    slide_dur = max(total_dur / n, 5.0)
    W, H = 1280, 720

    cmd = ["ffmpeg", "-y"]
    for sp in slide_paths:
        cmd += ["-loop", "1", "-framerate", "25", "-t", f"{slide_dur:.3f}", "-i", sp]
    cmd += ["-i", audio_path]

    filter_parts = []
    if n == 1:
        filter_parts.append(f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1[vout]")
    else:
        for i in range(n):
            filter_parts.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]")
        filter_parts.append(f"{''.join(f'[v{i}]' for i in range(n))}concat=n={n}:v=1:a=0[vout]")

    filtergraph = ";".join(filter_parts)
    cmd += [
        "-filter_complex", filtergraph,
        "-map", "[vout]",
        "-map", f"{n}:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-shortest",
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-1200:])
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "ffmpeg timed out after 10 minutes. Try fewer/smaller slides.")
    except Exception as e:
        raise HTTPException(500, f"ffmpeg failed: {e}")


# ── Step 5 endpoint ────────────────────────────────────────────────
@app.post("/api/video/{session_id}")
async def generate_video(session_id: str):
    tmp_files = []  # track all temp files for cleanup
    try:
        # ── Load topics.json from B2 ──
        tp = download_from_b2(f"recordings/{session_id}/processing/topics.json")
        tmp_files.append(tp)
        with open(tp, encoding="utf-8") as f:
            topics_data = json.load(f)
        topics = topics_data.get("topics", [])
        if not topics:
            raise HTTPException(400, "No topics found. Run AI structuring first.")

        # ── Load slide manifest from B2 ──
        mp = download_from_b2(f"recordings/{session_id}/slides/manifest.json")
        tmp_files.append(mp)
        with open(mp, encoding="utf-8") as f:
            manifest = json.load(f)
        slide_info = manifest.get("slides", [])
        if not slide_info:
            raise HTTPException(400, "No slides found. Run slide generation first.")

        # ── Download slide PNGs from B2 ──
        slide_paths = []
        for s in sorted(slide_info, key=lambda x: x["id"]):
            sp = download_from_b2(s["b2_key"])
            tmp_files.append(sp)
            # Rename with .png extension so ffmpeg recognises it
            png_path = sp + ".png"
            shutil.copy(sp, png_path)
            tmp_files.append(png_path)
            slide_paths.append(png_path)

        # ── 5A: Write teaching script ──
        script_text = write_teaching_script(topics_data)

        # Save script to B2
        script_bytes = script_text.encode("utf-8")
        upload_bytes_to_b2(script_bytes, f"recordings/{session_id}/video/script.txt", "text/plain")

        # ── 5B: Generate voice ──
        voice_source = "google_tts"
        elevenlabs_error = None
        if ELEVENLABS_API_KEY and ELEVENLABS_API_KEY != "your_elevenlabs_api_key_here":
            try:
                audio_bytes = generate_voice_elevenlabs(script_text)
                voice_source = "elevenlabs"
            except Exception as e:
                elevenlabs_error = str(e)
                print(f"[LectureSnap] ElevenLabs failed ({e}) — falling back to Google TTS (free)")
                audio_bytes = generate_voice_gtts_fallback(script_text)
        else:
            print("[LectureSnap] ElevenLabs not configured; using Google TTS fallback")
            audio_bytes = generate_voice_gtts_fallback(script_text)


        # Write audio to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as af:
            af.write(audio_bytes); audio_path = af.name
        tmp_files.append(audio_path)

        # Save narration to B2
        upload_bytes_to_b2(audio_bytes, f"recordings/{session_id}/video/narration.mp3", "audio/mpeg")

        # ── 5C: Assemble video ──
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as vf:
            video_path = vf.name
        tmp_files.append(video_path)

        topic_titles = [t.get("title", f"Topic {t.get('id',i+1)}") for i, t in enumerate(topics)]
        assemble_video(slide_paths, audio_path, video_path, topic_titles)

        # Upload MP4 to B2
        video_key = f"recordings/{session_id}/video/teacher_video.mp4"
        upload_to_b2(video_path, video_key, "video/mp4")

        return {
            "session_id": session_id,
            "status": "success",
            "voice_source": voice_source,
            "elevenlabs_error": elevenlabs_error,
            "slide_count": len(slide_paths),
            "script_preview": script_text[:400] + ("..." if len(script_text) > 400 else ""),
            "script_word_count": len(script_text.split()),
            "b2_video_key": video_key,
            "b2_audio_key": f"recordings/{session_id}/video/narration.mp3",
            "b2_script_key": f"recordings/{session_id}/video/script.txt",
        }


    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        for p in tmp_files:
            if p and os.path.exists(p):
                try: os.unlink(p)
                except: pass
