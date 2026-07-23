# 📚 LectureSnap
### Upload anything. Understand everything.

> An AI-powered pipeline that turns any lecture recording, meeting video, or PDF into structured study notes, visual slides, and a teacher-style narrated video — all stored on Backblaze B2.

---


## 🎥 Demo Video

> 📺 **Watch the complete LectureSnap demo on YouTube**

[![Watch LectureSnap Demo](https://img.youtube.com/vi/7TEhAo5l5b4/maxresdefault.jpg)](https://youtu.be/7TEhAo5l5b4)

🔗 **YouTube Demo:** https://youtu.be/7TEhAo5l5b4

🔗 https://jumpshare.com/s/KMiDfXSERt4oo6gxI9Bg

## 🌐 Live Demo

LectureSnap is deployed on Render and can be accessed here:

**Public URL:**  
https://lecturesnap.onrender.com

### API Documentation (Swagger UI)

https://lecturesnap.onrender.com/docs

### OpenAPI Specification

https://lecturesnap.onrender.com/openapi.json

### 🎓 AI Teacher-Style Video Demo
Demonstrates the AI-generated teacher narration and educational video output.

https://youtu.be/-ZJSYHItllc


## 🚀 Features

- 📄 PDF, Audio & Video Processing
- 🎙 OpenAI Whisper Transcription
- 🧠 AI Topic Identification using Groq Llama 3.1
- 📝 Intelligent Study Notes
- 🖼 Professional Slide Generation
- 🗣 AI Teacher Narration
- 🎬 Automatic Educational Video Generation
- ☁ Backblaze B2 Cloud Storage 



## The Problem

Think about what happens after a 1-hour lecture ends.

A student has a recording sitting on their phone. To use it, they have two choices — rewatch the whole thing (wastes an hour) or take notes manually while it plays (tedious, and most people do it poorly). A 100-page PDF textbook has the same problem. Nobody reads it fully. The information is locked inside, and extracting it takes hours of effort that most students simply don't spend.

The result: students go into exams having only half-understood the content, not because they aren't smart enough, but because the format of the material made it hard to learn from.

**This is the context fragmentation problem.** Knowledge exists inside recordings and documents, but there is no fast, intelligent way to pull it out, organise it, and explain it the way a real teacher would.

Existing tools do not solve this:
- Note-taking apps require manual effort
- Transcription tools give you a wall of text, not understanding
- AI chatbots answer questions but don't proactively teach
- Slide generators exist but produce thin, generic content

Nobody has properly built a pipeline that goes all the way from raw input — a PDF, a video, an audio recording — to a complete, high-quality study kit including structured notes, visual slides, and a narrated teacher video, fully automatically.

---
# 💡 Solution

LectureSnap automatically converts learning material into a complete study kit.

Every upload becomes:

✅ Structured Notes

✅ AI Topic Summary

✅ Professional Slides

✅ Teacher-style Narrated Video

✅ Stored permanently on Backblaze B2

---



---


## 🏗 Architecture

```
        Upload File
    (PDF / Audio / Video)
              │
              ▼
      Text Extraction
 (PyMuPDF / Whisper)
              │
              ▼
      AI Topic Analysis
      (Groq Llama 3.1)
              │
              ▼
     Professional Slides
 (Pollinations + Pillow)
              │
              ▼
      Teacher Narration
   (Edge-TTS + FFmpeg)
              │
              ▼
     Backblaze B2 Storage
```

---




## ⚙  How Each Stage Works

### Stage 1 — Text Extraction
The uploaded file goes directly to Backblaze B2 cloud storage. Then:
- **PDF files** → PyMuPDF extracts every word from every page, grouped into sections with page references
- **Audio files** → OpenAI Whisper transcribes speech to text with timestamps
- **Video files** → Whisper extracts and transcribes the audio track

Output: a structured JSON file (`extracted_text.json`) saved to B2, containing the full text and positional metadata.

### Stage 2 — AI Structuring (Groq, free)
The extracted text is sent to **Groq's Llama 3.1** model (free API) with a carefully designed prompt that acts like a teacher, not a summariser.

Groq reads the document and identifies the **4 to 5 most important topics** — not all topics, just the ones that matter most. For each topic it generates:
- A **concept explanation** — what is this and why does it matter, in simple language
- **4 detailed key points** — explained clearly, not just copied text fragments
- A **key fact** — a specific number, example, or detail from the document
- A **specific image keyword** for photo search

Output: `topics.json` saved to B2. This becomes the single source of truth for everything downstream.

### Stage 3 — Slide Generation (Pollinations.ai, free)
For each topic, LectureSnap:
1. Fetches a **real, photorealistic image** from Pollinations.ai using the topic's specific image keyword (e.g. "solar panels field golden hour" or "green forest trees sunlight")
2. Builds a **1280×720 professional slide** using Pillow — topic number, title, concept explanation, 4 key points, key fact highlight box, and the photo
3. Saves each slide as a PNG to Backblaze B2

Every slide has a unique colour theme (Indigo → Emerald → Violet → Amber → Cyan → Rose). If the image fetch fails, a geometric art fallback generates automatically so the pipeline never breaks.

### Stage 4 — Teacher Video (edge-tts + ffmpeg)
This is where LectureSnap does something no other tool does.

**Script generation:** Groq writes a spoken teaching script — not bullet points read aloud, but actual classroom teaching. The script opens each topic with a real-world scenario students can relate to, uses analogies to connect to things they already know, explains the concept in simple language, and drops in the key fact naturally. Example:

> *"Think about the last time you sat under a tree on a hot day. Did you notice how it was cooler there? That's not a coincidence. Trees don't just give us wood — they're running an entire air conditioning and water management system for the planet. Forests produce the oxygen we breathe through photosynthesis, absorb carbon dioxide that causes global warming, and regulate rainfall by acting as giant sponges..."*

**Voice generation:** The script is converted to speech using **Microsoft edge-tts** (free, no API key, neural voice `en-US-JennyNeural`) at +20% speaking rate — natural teacher pace. Falls back to Google TTS if edge-tts is unavailable.

**Video assembly:** ffmpeg stitches the slides and narration into a complete MP4 — each slide displayed for the duration of its narration, with smooth fade transitions between topics.

Output: `teacher_video.mp4` uploaded to Backblaze B2. Downloadable directly from the app.

---

## ☁ Why Backblaze B2

Every file produced at every stage is saved to Backblaze B2:

```
recordings/
  {session-id}/
    input/
      original.pdf          ← the uploaded file
    processing/
      extracted_text.json   ← Stage 1 output
      topics.json           ← Stage 2 output
    slides/
      slide_01.png          ← Stage 3 output
      slide_02.png
      ...
      manifest.json
    video/
      script.txt            ← Stage 4 teaching script
      narration.mp3         ← Stage 4 voice audio
      teacher_video.mp4     ← Stage 4 final video
    metadata.json
```

This means every output is durable, versioned, and accessible. Users can come back to any past session, re-download any file, or regenerate a single slide without reprocessing everything. B2 is the backbone that makes the pipeline production-ready — not just a demo.

---

## Genblaze Workflow

LectureSnap is designed as a modular AI media pipeline where each generation stage is independent and provider-agnostic.

The current implementation orchestrates multiple AI services to generate educational media:

- AI topic generation
- AI image generation
- AI voice narration
- AI video assembly
- Persistent storage in Backblaze B2

The media pipeline is intentionally modular, allowing AI providers to be replaced or extended without changing the overall workflow.

This architecture aligns with the orchestration approach promoted by Genblaze and can be adapted to use Genblaze-supported providers as the project evolves.


---

## 🛠 Tech Stack

| Component | Technology | 
|---|---|
| Backend | Python + FastAPI | 
| Cloud Storage | Backblaze B2 | 
| PDF Extraction | PyMuPDF | Free |
| Audio Transcription | OpenAI Whisper | 
| AI Structuring | Groq API (Llama 3.1) | 
| Image Generation | Pollinations.ai | 
| Slide Creation | Pillow | 
| Voice Synthesis | Microsoft edge-tts | 
| Video Assembly | ffmpeg | 
| Frontend | HTML + Vanilla JS | 

---

## ▶ How to Run

### Step 1 — Prerequisites

Install Python 3.10 and the following:
```bash
py -3.10 -m pip install fastapi uvicorn[standard] python-multipart boto3 openai pymupdf==1.24.7 python-dotenv httpx==0.27.2 Pillow gtts moviepy imageio imageio-ffmpeg edge-tts
```

Also install **ffmpeg** — download from https://ffmpeg.org and add to your system PATH.

### Step 2 — Configure environment

Copy `.env.example` to `.env` and fill in:

```env
# Backblaze B2 (get from backblaze.com — free account, 10GB included)
B2_KEY_ID=your_key_id
B2_APP_KEY=your_application_key
B2_BUCKET_NAME=your_bucket_name
B2_ENDPOINT=https://s3.us-east-005.backblazeb2.com

# Groq (free — get from console.groq.com, no credit card)
GROQ_API_KEY=gsk_your_groq_key

# OpenAI (only needed for audio/video uploads — PDF works without it)
OPENAI_API_KEY=sk-your_openai_key
```

### Step 3 — Run

```bash
py -3.10 -m uvicorn main:app --reload
```

Open your browser at **http://localhost:8000**

### Step 4 — Use it

1. Drop a PDF, audio, or video file onto the upload area
2. Click **Identify Topics with AI** — Groq reads and structures your document
3. Click **Generate Study Slides** — real photos + content for each topic
4. Click **Generate Teacher Video** — AI narrates a full lesson (takes 3-5 minutes)
5. Download your MP4

---

## ⭐ What Makes LectureSnap Different

| Feature | Traditional tools | LectureSnap |
|---|---|---|
| Works on PDF, video, audio | Sometimes | ✅ All three |
| Extracts full text | Basic OCR only | ✅ Full structured extraction |
| Explains concepts like a teacher | ❌ | ✅ With analogies and real examples |
| Generates visual slides with real photos | ❌ | ✅ |
| Produces a narrated teaching video | ❌ | ✅ |
| Stores everything durably in cloud | ❌ | ✅ Backblaze B2 |
| Requires manual effort | Lots | Nearly zero |
| Cost to use | Often paid | Mostly free APIs |

---

## 📂  Project Structure

```
lecturesnapfull/
├── main.py              ← All pipeline logic (4 stages + API endpoints)
├── requirements.txt     ← Python dependencies
├── .env.example         ← Environment variable template
├── static/
│   └── index.html       ← Full frontend (single file, no framework)
└── README.md            ← This file
```

---

## Built For

**Backblaze Generative AI Media Hackathon 2026**

LectureSnap demonstrates a complete agentic generative media pipeline:
- **Generate** → Groq generates structured content and teaching scripts; Pollinations generates images; edge-tts generates voice audio
- **Evaluate** → Quality checks on each image (retry if failed); script validation before video assembly
- **Store** → Every intermediate and final output saved to Backblaze B2 with provenance metadata
- **Serve** → Users stream the final video directly from B2 via the download endpoint

This is not a wrapper around a single AI call. It is a multi-stage pipeline where each stage's output feeds the next, with durable cloud storage at every step — exactly what production generative media applications require.

---

# 👩‍💻 Author

*Built by Niveditha *


*Linkdin: https://www.linkedin.com/in/niveditha-89ba04356/*
