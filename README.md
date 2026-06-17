# VoiceCheck

An async voice-feedback tool. Students record up to 30 seconds of audio and
submit it; the backend transcribes it with Whisper, asks a local LLM for
structured feedback, and writes the result to Firestore. The student watches the
status go **Uploading → Processing → Done** live via a Firestore real-time
listener, and teachers review every submission, play back the audio, read the
AI feedback, and leave comments.

```
┌──────────────┐   1. upload audio (POST)   ┌─────────────────────┐
│   Frontend   │ ─────────────────────────► │   FastAPI backend   │
│ React + Vite │                            │  Whisper + Ollama   │
│              │ ◄───────────────────────── │                     │
└──────┬───────┘   3. real-time updates     └──────────┬──────────┘
       │                  (onSnapshot)                  │ 2. write results
       │                                                ▼
       │              ┌─────────────────────────────────────────┐
       └────────────► │              Firestore                   │
         read/listen  │  submissions/{id} + .../comments         │
                      └─────────────────────────────────────────┘
```

The frontend never calls Whisper or the LLM directly. It uploads to the backend
and then **observes Firestore** — that listener is the core real-time UX
pattern.

## Repository layout

```
voicecheck/
├── frontend/          React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── auth/          Firebase Auth context
│       ├── components/    Student view, Teacher view, recorder, etc.
│       ├── lib/           Backend upload client
│       ├── firebase.ts    Firebase init
│       └── types.ts       Shared Firestore types
├── backend/           Python + FastAPI + Docker
│   └── app/
│       ├── main.py            FastAPI app, routes, startup
│       ├── pipeline.py        transcribe → feedback → persist
│       ├── transcription.py   Whisper (loaded once at startup)
│       ├── llm.py             Ollama feedback + mock fallback
│       ├── firestore_client.py  Admin SDK wrapper
│       ├── schemas.py         Pydantic contracts
│       └── config.py          env-driven settings
├── firestore.rules    Security rules
├── README.md
└── DEPLOYMENT.md      GCP deployment writeup (not implemented)
```

## Prerequisites

- **Node 18+**
- **Python 3.11 or 3.12** for the backend. ⚠️ `openai-whisper` ships only as a
  source tarball and does **not** build on Python 3.13/3.14 (its `setup.py`
  relies on pre-PEP-667 `exec`/`locals()` semantics). If you only have 3.13/3.14,
  use the **Docker** path below — it builds on 3.11 inside the container.
- **ffmpeg** on your PATH (Whisper needs it) — `choco install ffmpeg` /
  `brew install ffmpeg` / `apt install ffmpeg` *(not needed for the Docker path)*
- A **Firebase project** with Email/Password auth and Firestore enabled
- **Docker** *(optional, but the simplest backend path)*
- **[Ollama](https://ollama.com)** with `qwen2.5:7b` pulled *(optional — the
  backend falls back to mock feedback if Ollama isn't running)*

## Setup (≈5 minutes)

### 1. Firebase (one-time, ~2 min)

1. Create a project at <https://console.firebase.google.com>.
2. **Build → Authentication → Sign-in method →** enable **Email/Password**.
3. **Build → Firestore Database → Create database** (test mode is fine locally).
4. **Project settings → General → Your apps →** register a **Web app** and copy
   the config values (these go in `frontend/.env.local`).
5. **Project settings → Service accounts → Generate new private key**. Save the
   JSON as `backend/serviceAccount.json` (git-ignored).

### 2. Backend

**Option A — Docker (recommended; works regardless of your local Python):**

```bash
cd backend
cp .env.example .env          # set PUBLIC_BASE_URL and creds as needed
docker build -t voicecheck-api .
docker run --rm -p 8000:8000 \
  -v "$PWD/serviceAccount.json:/app/serviceAccount.json:ro" \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  voicecheck-api
```

The image bakes in the Whisper `base` model so cold starts don't re-download it.

**Option B — local venv (Python 3.11 / 3.12 only):**

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
# source .venv/bin/activate                         # macOS/Linux
pip install --upgrade "pip" "setuptools<81" wheel
pip install -r requirements.txt -c constraints.txt  # constraint fixes whisper's build

cp .env.example .env          # defaults are fine; points at serviceAccount.json
uvicorn app.main:app --reload --port 8000
```

The first start downloads the Whisper `base` model (~140 MB) and loads it once.
The `constraints.txt` / `setuptools<81` step is required because `openai-whisper`'s
`setup.py` imports `pkg_resources`, which setuptools ≥81 no longer bundles.

*(Optional)* For real LLM feedback instead of the mock:
```bash
ollama pull qwen2.5:7b && ollama serve
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local    # paste your Firebase web config
npm run dev
```

Open <http://localhost:5173>, sign up with any email/password, and you're in.

### 4. Try it

- **Student tab:** record up to 30s → **Submit** → watch
  *Uploading → Processing → Done* with transcription + feedback.
- **Teacher tab:** see every submission, play the audio, read feedback, and
  post a comment.

> The Student/Teacher switch in the header is a simple UI toggle — see
> [Design decisions](#design-decisions).

## Configuration reference

**Backend** (`backend/.env`):

| Var | Default | Purpose |
|-----|---------|---------|
| `WHISPER_MODEL` | `base` | Whisper size (`tiny`…`large`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Feedback model |
| `GOOGLE_APPLICATION_CREDENTIALS` | `./serviceAccount.json` | Firebase admin creds (empty = ADC) |
| `VERIFY_AUTH` | `true` | Verify Firebase ID token on upload |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Base for audio playback URLs |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed origins (comma-separated) |

**Frontend** (`frontend/.env.local`): the six `VITE_FIREBASE_*` values plus
`VITE_API_BASE_URL`.

## How the real-time status works

1. Student records → `POST /api/submissions` with the audio + Firebase ID token.
2. Backend verifies the token, **creates the Firestore doc** with
   `status: "processing"`, saves the audio, and schedules a background task,
   then returns the new id.
3. The frontend attaches `onSnapshot` to that doc. "Uploading" is the brief
   client-side state before the id exists; everything after is driven by
   Firestore.
4. The background task transcribes (Whisper) → generates feedback (Ollama) →
   **updates the doc** to `status: "done"`. The snapshot fires and the UI
   re-renders with the result. On failure it writes `status: "error"`.

## Design decisions & assumptions

- **One-account role toggle.** The spec asks for "simple email login" and
  separate student/teacher views but no role management, so a header switch
  lets a single account demo both. Production would gate views with Firebase
  custom claims (sketched in `DEPLOYMENT.md` / `firestore.rules`).
- **Audio lives on the backend** at `/api/audio/{id}` for local simplicity. In
  production this is a Cloud Storage object served via signed URL — the
  `audioUrl` field already isolates that change.
- **Backend owns all submission writes** via the Admin SDK; clients only read
  submissions and write comments (enforced in `firestore.rules`). This keeps the
  pipeline as the single source of truth.
- **Mock LLM fallback.** If Ollama isn't running the pipeline returns
  deterministic placeholder feedback so the end-to-end flow always works for
  evaluation.
- **`BackgroundTasks` for processing.** Fine for a single-user demo; a real
  deployment would use a proper queue (see `DEPLOYMENT.md`).

## Open questions (handling ambiguity)

- *Roles:* should student/teacher be enforced server-side, or is a shared
  account acceptable for the demo? Assumed the latter; left a clean upgrade path.
- *LLM:* the spec says "an LLM" without specifying one. Chose local Ollama
  (`qwen2.5:7b`) so the project runs fully offline with no API keys, with a mock
  fallback.
- *Audio retention / file-size limits / a "prompt" for students to read* are out
  of scope here but flagged for a follow-up.

## Scripts

| Location | Command | Does |
|----------|---------|------|
| frontend | `npm run dev` | Vite dev server |
| frontend | `npm run build` | Type-check + production build |
| backend | `uvicorn app.main:app --reload` | Dev server |
| backend | `docker build -t voicecheck-api .` | Container build |
