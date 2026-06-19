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
│       ├── llm.py             Groq / Ollama feedback + mock fallback
│       ├── audio_storage.py   Firebase Storage / R2 / local disk
│       ├── firestore_client.py  Admin SDK wrapper
│       ├── schemas.py         Pydantic contracts
│       └── config.py          env-driven settings
├── .github/workflows/ CI/CD — auto-deploy on push to prod (see below)
│   ├── deploy-backend.yml   → Google Cloud Run
│   └── deploy-frontend.yml  → Cloudflare Pages
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
  ```console
    # For Ollama installation
    irm https://ollama.com/install.ps1 | iex

    # To Run Ollama qwen2.5:7b model
    ollama run qwen2.5:7b-instruct 
  ```

## Run everything with Docker (recommended)

One command brings up both the FastAPI backend and the nginx-served frontend.

**Prerequisites:** Docker, a Firebase project (see [step 1](#firebase-setup-one-time-2-min)),
and *(optional)* Ollama running on the host for real LLM feedback.

### Firebase Setup (one-time, ~2 min)

1. Create a project at <https://console.firebase.google.com>.
2. **Build → Authentication → Sign-in method →** enable **Email/Password**.
3. **Build → Firestore Database → Create database** (test mode is fine locally).
4. **Build → Storage → Get started** to enable Cloud Storage, then copy the
   **bucket name** shown at the top (e.g. `my-project.appspot.com` or
   `my-project.firebasestorage.app`) → `FIREBASE_STORAGE_BUCKET` in `backend/.env`.
5. **Project settings → General → Your apps →** register a **Web app** and copy
   the config values (these go in `frontend/.env.local`).
6. **Project settings → Service accounts → Generate new private key**. Save the
   JSON as `backend/serviceAccount.json` (git-ignored).

```bash
# 1. Firebase Admin key for the backend (Console -> Project settings ->
#    Service accounts -> Generate new private key)
#    save it here:
#    backend/serviceAccount.json

# 2. Firebase web config for the frontend build
# Basically make your own env with variables given in env.example
cp .env.example .env          # then fill in the VITE_FIREBASE_* values

# 3. Up!
docker compose up --build
```

Then open **<http://localhost:5173>** (frontend); the API is on
<http://localhost:8000> (Swagger at `/docs`).

- The **first** build is slow (it downloads PyTorch and bakes the Whisper `base`
  model into the backend image). Subsequent `docker compose up` starts are quick.
- Audio is persisted in the `audio_data` volume; metadata/auth live in your cloud
  Firestore, so both containers share state.
- No Ollama running? Feedback falls back to a deterministic mock — the app still
  works end to end.
- Stop with `Ctrl+C`; `docker compose down` removes the containers (add `-v` to
  also wipe the audio volume).

> The `VITE_FIREBASE_*` values are baked into the frontend at build time, so
> after changing `.env` re-run with `--build`. (Firebase **web** keys are public
> by design — not secrets.) The Admin `serviceAccount.json` **is** a secret: it's
> mounted read-only at runtime and never copied into the image.

For running the pieces individually (or without Docker), see
[Manual setup](#setup-5-minutes) below.

## Setup (5 minutes)

### 1. Firebase (one-time, ~2 min)

Follow [firebase setup step](#firebase-setup-one-time-2-min)

### 2. Backend

> **Just want to poke the API?** See
> [Quick backend check via Swagger](#quick-backend-check-via-swagger) below — it
> runs on any Python (incl. 3.13/3.14) with no Whisper, Firebase, or Ollama.

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

**Important Notes** Before setting up the local backend instance make sure it won't be able to fetch the audio files from the docker volume.
It will only able to get the audio file from backend/audio_store folder. It may show list of all the audio files uploaded by the students, however
that is because submission detail of the file and user details both are stored in firestore. Which is only one instance, here we have 2 ways to run,
locally or by docker.

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

### Free & persistent setup (no Cloud Storage, no billing)

Firebase **Auth and Firestore are free** (Spark plan, no card). Only Cloud
Storage now asks you to enable billing. To run fully free with data shared and
persisted between frontend and backend:

1. **Leave `FIREBASE_STORAGE_BUCKET` empty** in `backend/.env`. Audio is then
   stored on the backend disk (`audio_store/`, persists across restarts) and
   served from `/api/audio/{key}`.
2. **Point the backend at the same cloud Firestore the frontend uses** — install
   the full `requirements.txt` (so `firebase-admin` is present) and set
   `GOOGLE_APPLICATION_CREDENTIALS=./serviceAccount.json`. Both apps then read and
   write the same Firestore project, so the frontend sees every upload live.

> ⚠️ **Watch the startup log.** It prints `store=FirestoreClient` when sharing
> cloud Firestore. If you see `store=InMemoryStore` (and a warning), the backend
> is isolated — the frontend won't see its data and it's lost on restart. That
> happens when `firebase-admin` isn't installed or the credentials are missing.

Only the audio bytes stay on the backend; everything the frontend needs (status,
transcript, feedback, reviews) lives in the shared, persistent Firestore.

### Quick backend check via Swagger

To exercise the API on its own — without Whisper, Firebase, or Ollama — install
just the core deps and run. The app boots in **dev mode**: a mock transcriber +
an in-memory store stand in, so the full upload → processing → done flow works
and is visible in the interactive docs. Runs on any Python, including 3.13/3.14.

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements-core.txt
uvicorn app.main:app --port 8000
```

Open **<http://localhost:8000/docs>** (Swagger UI; ReDoc at `/redoc`) and:

1. **POST `/api/submissions`** — upload any small audio file (auth is auto-skipped
   in dev mode). You get back `{ id, status: "processing" }`.
2. **GET `/api/submissions/{id}`** — see it already flipped to `done` with a
   (mock) transcription and feedback.
3. **GET `/api/submissions`** / **GET `/api/audio/{id}`** — list everything / play
   the stored clip.

The startup logs tell you which backends are live (real vs. mock/in-memory).
Start Ollama and/or install the full `requirements.txt` to swap the mocks for the
real thing.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local    # paste your Firebase web config
npm run dev
```

Open <http://localhost:5173>, sign up with any email/password, and you're in.

### 4. Try it

On first login each account picks a role (**Student** or **Teacher**), stored in
`users/{uid}`. Create one of each to see both sides.

- **Student:** record up to 30s → **Submit** → watch
  *Uploading → Processing → Done*, then read the transcription and AI feedback.
  Each submission shows the teacher's review, or **"Pending review"** until a
  teacher gets to it. Students only see their own submissions.
- **Teacher:** sees **all** submissions, plays the audio, reads the AI
  transcript + feedback, ticks **"AI transcript is accurate"**, and writes
  **improvement notes**. Saving flips the student's view to *Reviewed*.

## Configuration reference

**Backend** (`backend/.env`):

| Var | Default | Purpose |
|-----|---------|---------|
| `WHISPER_MODEL` | `base` | Whisper size (`tiny`…`large`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint (used when `GROQ_API_KEY` is empty) |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Feedback model for Ollama |
| `GROQ_API_KEY` | _(empty)_ | Set to use [Groq](https://console.groq.com/keys) (free) instead of Ollama |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Feedback model for Groq |
| `GOOGLE_APPLICATION_CREDENTIALS` | `./serviceAccount.json` | Firebase admin creds (path to JSON file) |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | _(empty)_ | Same creds, as raw JSON — for hosts with no file mounts and no IAM-based ADC (e.g. via Secret Manager) |
| `FIREBASE_STORAGE_BUCKET` | _(empty)_ | Bucket for audio; empty falls through to R2, then local disk |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET_NAME` / `R2_PUBLIC_BASE_URL` | _(empty)_ | [Cloudflare R2](https://dash.cloudflare.com) (free 10GB) audio storage, used when Firebase Storage isn't configured |
| `VERIFY_AUTH` | `true` | Verify Firebase ID token on upload |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Base for audio playback URLs (local-disk storage only) |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed origins (comma-separated) |

**Frontend** (`frontend/.env.local`): the six `VITE_FIREBASE_*` values plus
`VITE_API_BASE_URL`.

## Deploying for free (with CI/CD)

Every push to `prod` can auto-deploy both halves of the app at no cost:

| Layer | Service | Free tier |
|---|---|---|
| Frontend | **Cloudflare Pages** | Unlimited bandwidth, no card required |
| Backend | **Google Cloud Run** (Docker) | 2M requests/mo, 360k GiB-sec, 180k vCPU-sec — needs a card on file, but no charge while inside the free tier |
| LLM | **Groq API** | Free rate-limited tier, replaces Ollama (no GPU needed) |
| Audio storage | **Cloudflare R2** | 10GB storage, no card required |
| Auth + DB | **Firebase** (Spark plan) | Already free, as used locally |

The workflows live at [.github/workflows/deploy-backend.yml](.github/workflows/deploy-backend.yml)
and [.github/workflows/deploy-frontend.yml](.github/workflows/deploy-frontend.yml).
Each only runs when files under its respective `backend/` or `frontend/`
folder change.

### One-time setup

1. **Groq** — create a free key at <https://console.groq.com/keys>.
2. **Cloudflare R2** — in the Cloudflare dashboard, create a bucket and an
   R2 API token (Account → R2 → Manage API Tokens). Enable the bucket's
   public access ("r2.dev" URL or a custom domain) for `R2_PUBLIC_BASE_URL`.
3. **Google Cloud Run**:
   - Create a GCP project; enable the Cloud Run and Artifact Registry APIs.
   - Create an Artifact Registry Docker repo:
     `gcloud artifacts repositories create voicecheck --repository-format=docker --location=<region>`
   - Create a deploy service account with roles **Cloud Run Admin**,
     **Artifact Registry Writer**, **Service Account User**, and download its
     JSON key (`gcloud iam service-accounts keys create ...`). Many GCP
     projects now block key creation by default
     (`iam.disableServiceAccountKeyCreation`) — if so, either disable that
     org policy for the project, or create the service account (and its key)
     in a *different* project you control and grant it those same three
     roles **on this project** instead (cross-project IAM grants are normal):
     ```bash
     DEPLOY_SA="voicecheck-deployer@<other-project-id>.iam.gserviceaccount.com"
     gcloud projects add-iam-policy-binding <this-project-id> --member="serviceAccount:$DEPLOY_SA" --role="roles/run.admin"
     gcloud projects add-iam-policy-binding <this-project-id> --member="serviceAccount:$DEPLOY_SA" --role="roles/artifactregistry.writer"
     gcloud projects add-iam-policy-binding <this-project-id> --member="serviceAccount:$DEPLOY_SA" --role="roles/iam.serviceAccountUser"
     ```
   - Create a **dedicated runtime service account** for the Cloud Run service
     itself (kept separate from the deploy SA above, least-privilege) and
     grant it Firestore access on whichever project hosts your Firestore
     database (may be a different project than the one running Cloud Run):
     ```bash
     gcloud iam service-accounts create voicecheck-runtime --project=<cloud-run-project-id>
     gcloud projects add-iam-policy-binding <firestore-project-id> \
       --member="serviceAccount:voicecheck-runtime@<cloud-run-project-id>.iam.gserviceaccount.com" \
       --role="roles/datastore.user"
     ```
     This SA is referenced via `--service-account` in the workflow's deploy
     flags — leave `GOOGLE_APPLICATION_CREDENTIALS`/`_JSON` empty; ADC picks
     it up automatically.
   - After the first deploy, set the runtime secrets/env vars once — they
     persist across future CI deploys since the workflow never passes
     `--set-env-vars` (Cloud Run carries forward whatever isn't touched):
     ```bash
     gcloud run services update voicecheck-backend --region=<region> \
       --set-env-vars=CORS_ORIGINS=<your-pages-url>,PUBLIC_BASE_URL=<your-run-url> \
       --set-secrets=GROQ_API_KEY=groq-api-key:latest
     ```
4. **Cloudflare Pages** — create an API token with the *Pages: Edit*
   permission, and note your Account ID (Cloudflare dashboard sidebar).
5. **GitHub repo secrets** (Settings → Secrets and variables → Actions):

   | Secret | Value |
   |---|---|
   | `GCP_PROJECT_ID` | Your GCP project id (the one running Cloud Run/Artifact Registry) |
   | `GCP_REGION` | e.g. `us-central1` |
   | `GCP_SA_KEY` | The deploy service account's JSON key contents |
   | `CLOUDFLARE_API_TOKEN` | Cloudflare Pages-Edit token |
   | `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
   | `VITE_FIREBASE_*` (all six) | Your Firebase web app config |
   | `VITE_API_BASE_URL` | Your Cloud Run service URL, shown after the first deploy (e.g. `https://voicecheck-backend-xxxxx-uc.a.run.app`) |

Push to `prod` and both deploys kick off automatically — check progress under
the repo's **Actions** tab.

### Why this combo

- Cloud Run's disk is **ephemeral** per instance, so audio can't live there —
  that's what R2 is for. Firestore (metadata) and Groq (LLM) are both already
  external services, so they're unaffected.
- Ollama needs more RAM than fits comfortably alongside Whisper on a
  cost-conscious Cloud Run instance, so Groq stands in for it. The
  `generate_feedback` switch in `app/llm.py` already auto-picks Groq when
  `GROQ_API_KEY` is set — same code path, no extra branching needed for local
  vs. hosted.
- `BackgroundTasks` runs the transcribe → feedback → Firestore-write pipeline
  **after** the HTTP response is sent. Cloud Run throttles a container's CPU
  to zero the instant it finishes a response by default, which would starve
  that work — the deploy workflow passes `--no-cpu-throttling` to keep CPU
  allocated for it.
- Cold starts: with `--min-instances=0` (the free-tier default used here),
  an idle service scales to zero and the next request pays for reloading
  Whisper + torch from scratch (several seconds). Setting `--min-instances=1`
  removes that at the cost of paying for an always-on instance.

## How the real-time status works

1. Student records → `POST /api/submissions` with the audio + Firebase ID token.
2. Backend verifies the token, **creates the Firestore doc** with
   `status: "processing"`, saves the audio, and schedules a background task,
   then returns the new id.
3. The frontend attaches `onSnapshot` to that doc. "Uploading" is the brief
   client-side state before the id exists; everything after is driven by
   Firestore.
4. The background task transcribes (Whisper) → generates feedback (Groq or
   Ollama) → **updates the doc** to `status: "done"`. The snapshot fires and
   the UI re-renders with the result. On failure it writes `status: "error"`.

## Design decisions & assumptions

- **Per-account roles.** Each account chooses Student or Teacher on first login;
  the role lives in `users/{uid}` and decides which view renders. Students see
  only their own submissions; teachers see all and can review. For a take-home
  this is enforced client-side + via security rules; production would promote the
  teacher role to a Firebase **custom claim** so it can't be self-assigned
  (sketched in `DEPLOYMENT.md` / `firestore.rules`).
- **Pluggable audio storage.** Three backends behind one interface, tried in
  order: **Firebase Storage** (if `FIREBASE_STORAGE_BUCKET` is set) → **Cloudflare
  R2** (if `R2_BUCKET_NAME` is set — free, used for the hosted deploy since HF
  Spaces' disk is ephemeral) → local disk served from `/api/audio/{key}` (dev
  fallback). Whichever is active, Whisper still reads a transient local copy
  that's deleted after transcription. See `app/audio_storage.py`.
- **Backend owns the pipeline; teachers own the review.** The Admin SDK writes
  the audio/transcript/AI feedback (clients can't touch those); teachers may only
  update the review fields (`reviewStatus`, `transcriptVerified`, `teacherNotes`,
  …), enforced in `firestore.rules`.
- **Pluggable LLM, with mock fallback.** `generate_feedback` uses **Groq**
  when `GROQ_API_KEY` is set (the hosted deploy — free tier, no GPU needed),
  otherwise local **Ollama** (offline dev). If neither responds, the pipeline
  returns deterministic placeholder feedback so the end-to-end flow always
  works for evaluation. See `app/llm.py`.
- **`BackgroundTasks` for processing.** Fine for a single-user demo; a real
  deployment would use a proper queue (see `DEPLOYMENT.md`).

## Open questions (handling ambiguity)

- *Security:* Currently Backend APIs are exposed which can be improved. Auth methods
  can be included like apikey, BearerToken, user/password.
- *Roles:* should student/teacher be enforced server-side, or is a shared
  account acceptable for the demo? Assumed the latter; left a clean upgrade path.
- *LLM:* the spec says "an LLM" without specifying one. Chose local Ollama
  (`qwen2.5:7b`) for offline dev with no API keys, and Groq (free tier) as the
  drop-in hosted equivalent — same code path, picked automatically by whether
  `GROQ_API_KEY` is set. Mock fallback either way.
- *Audio retention / file-size limits / a "prompt" for students to read* are out
  of scope here but flagged for a follow-up.

## Scripts

| Location | Command | Does |
|----------|---------|------|
| frontend | `npm run dev` | Vite dev server |
| frontend | `npm run build` | Type-check + production build |
| backend | `uvicorn app.main:app --reload` | Dev server |
| backend | `docker build -t voicecheck-api .` | Container build |
