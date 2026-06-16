# DEPLOYMENT.md

> This is a **written deployment plan**, not an implemented one. It describes how
> VoiceCheck would run on GCP, how secrets are handled, the CI/CD shape, and the
> Whisper cold-start trade-off.

## 1. Architecture on GCP

```
                          ┌────────────────────────────┐
        Browser  ───────► │  Firebase Hosting (CDN)     │   static React build
                          └──────────────┬─────────────┘
                                         │ XHR/fetch (audio upload + ID token)
                                         ▼
                          ┌────────────────────────────┐
                          │  Cloud Run: voicecheck-api  │   FastAPI + Whisper
                          │  (container, min-instances) │
                          └───┬───────────┬─────────┬───┘
                  writes      │           │ reads    │ pulls feedback
                  results     │           │ creds    │
                              ▼           ▼          ▼
                   ┌──────────────┐ ┌───────────┐ ┌──────────────────┐
                   │  Firestore   │ │  Secret   │ │  LLM provider     │
                   │ submissions/ │ │  Manager  │ │ (Vertex AI or     │
                   │  + comments  │ └───────────┘ │  self-hosted LLM) │
                   └──────────────┘               └──────────────────┘
                              ▲
        signed URL playback   │  audio objects
                   ┌──────────┴───────────┐
                   │ Cloud Storage bucket │  gs://voicecheck-audio
                   └──────────────────────┘
```

| Component | GCP service | Notes |
|-----------|-------------|-------|
| **Frontend** (static SPA) | **Firebase Hosting** | Global CDN, free TLS, atomic deploys + instant rollback. (Cloud Storage + Cloud CDN is an alternative.) |
| **Backend API + Whisper** | **Cloud Run** | Containerised FastAPI. CPU + memory sized for the model; scales to many instances. |
| **Auth** | **Firebase Auth** | Email/Password; ID tokens verified by the backend via Admin SDK. |
| **Database** | **Firestore** (native mode) | `submissions/{id}` + `comments` subcollection. Powers the real-time listener. |
| **Audio storage** | **Cloud Storage** | One object per submission; served to teachers via short-lived **signed URLs**. |
| **LLM** | **Vertex AI** managed model, *or* a self-hosted Ollama/vLLM on a GPU Cloud Run / GKE node | The `llm.py` abstraction means swapping the endpoint is a config change. |
| **Secrets** | **Secret Manager** | See §2. |

### Code changes needed for production (already isolated)
- **Audio:** replace the local `audio_store` write + `/api/audio/{id}` route with
  a Cloud Storage upload and a signed-URL `audioUrl`. Only `main.py` and
  `firestore_client.create_submission` touch this.
- **Background work:** move `process_submission` off `BackgroundTasks` onto a
  proper queue (see §5).
- **Credentials:** drop `serviceAccount.json`; Cloud Run uses its attached
  service account via Application Default Credentials (already supported — leave
  `GOOGLE_APPLICATION_CREDENTIALS` empty).

## 2. Secrets management

**Principle: no secrets in the repo, in images, or in env files committed to git.**

| Secret | Where | How it's consumed |
|--------|-------|-------------------|
| Backend service-account identity | Cloud Run **runtime service account** | No JSON file at all — ADC. Grant `roles/datastore.user` + `roles/storage.objectAdmin`. |
| LLM API key (if using a hosted provider) | **Secret Manager** → mounted as a Cloud Run secret env var | Read once at startup via `config.py`. |
| Firebase **web** config (`VITE_FIREBASE_*`) | Build-time env in CI | Not secret (client-side by design), but injected at build, not committed. |

- Cloud Run references secrets with `--set-secrets LLM_API_KEY=llm-api-key:latest`;
  rotation = add a new secret version, no redeploy of code.
- CI authenticates to GCP via **Workload Identity Federation** (OIDC from GitHub
  Actions) — no long-lived JSON keys stored in GitHub.
- Principle of least privilege: separate service accounts for the deploy pipeline
  vs. the running service.

## 3. CI/CD — two independent pipelines

Frontend and backend deploy separately so a UI tweak never rebuilds the
multi-hundred-MB Whisper image, and vice-versa. Both triggered on push to `main`,
path-filtered.

### Backend pipeline (`.github/workflows/backend.yml`)
Trigger: changes under `backend/**`.
1. `pip install` + lint + `pytest`.
2. `docker build` (model baked into the image — see §5) and push to **Artifact
   Registry**.
3. `gcloud run deploy voicecheck-api` with the new image, secrets, and
   `--min-instances` setting.
4. Smoke test `/healthz`; auto-rollback to previous revision on failure.

```yaml
# sketch
on: { push: { branches: [main], paths: ['backend/**'] } }
jobs:
  deploy:
    permissions: { id-token: write }          # Workload Identity Federation
    steps:
      - uses: actions/checkout@v4
      - run: cd backend && pip install -r requirements.txt && pytest
      - uses: google-github-actions/auth@v2    # OIDC, keyless
      - run: gcloud builds submit backend --tag $REGION-docker.pkg.dev/$PROJECT/vc/api
      - run: gcloud run deploy voicecheck-api --image .../api --region $REGION
             --min-instances=1 --cpu=2 --memory=4Gi
             --set-secrets LLM_API_KEY=llm-api-key:latest
```

### Frontend pipeline (`.github/workflows/frontend.yml`)
Trigger: changes under `frontend/**`.
1. `npm ci`, `npm run build` (type-check + Vite build), inject `VITE_*` env.
2. `firebase deploy --only hosting` (and `--only firestore:rules` when
   `firestore.rules` changes).
3. Hosting keeps previous versions for one-click rollback.

**Environments:** PRs deploy to a preview channel (Firebase Hosting preview +
a `--no-traffic` Cloud Run revision); `main` promotes to production.

## 4. Firestore rules
`firestore.rules` is deployed from the frontend pipeline. Production hardening:
attach **custom claims** (`role: teacher`) at sign-up/admin time, restrict
students to reading their own submissions, and keep teacher list-reads behind the
claim. The backend already owns all submission writes via the Admin SDK (which
bypasses rules), so clients stay read-only on submissions.

## 5. The Whisper cold-start trade-off

Whisper `base` is ~140 MB of weights that must be in memory before the first
transcription. On Cloud Run, a brand-new instance must pull the image, start the
process, and **load the model** — several seconds of cold start. The relevant
knobs and their trade-offs:

| Strategy | Cold start | Cost | Verdict |
|----------|-----------|------|---------|
| **Bake the model into the image** (our `Dockerfile` does this) | Faster — no runtime download, model loads from local disk | Larger image | ✅ Do this. Avoids a network fetch on every cold instance. |
| **Download model at runtime** | Slowest — network pull on every new instance | Small image | ❌ Avoid. |
| **`min-instances >= 1`** | ~Zero (an instance is always warm) | Pay for idle CPU/RAM 24/7 | ✅ For interactive UX. The main lever. |
| **`min-instances = 0`** | Full cold start on the first request after idle | Cheapest; scales to zero | OK for a low-traffic internal tool; bad UX for sporadic use. |
| **Bigger model (`small`/`medium`)** | Slower load + slower inference + more RAM | More $$ | Only if accuracy demands it. `base` is enough here. |
| **GPU instances** | Faster inference, slower/cap-limited scaling, pricier | High | Only at real volume. |

**Recommendation:** bake `base` into the image **and** run `min-instances=1` so
the model is loaded and warm. Because the model loads **once at startup**
(`transcription.py`), keeping the instance warm means the cost is paid a single
time per instance, not per request. Set generous request concurrency limits low
(e.g. `--concurrency=4`) since transcription is CPU-bound, and scale **out** with
more instances rather than more threads per instance.

### Async processing at scale
`BackgroundTasks` runs in-process, so a crash mid-transcription loses the job and
a slow LLM ties up the instance. Production design:
- Upload handler writes the audio to Cloud Storage, creates the Firestore doc
  (`processing`), and publishes a **Pub/Sub** message — then returns immediately.
- A separate **worker** Cloud Run service (push-subscribed) does Whisper + LLM and
  updates Firestore. This decouples the latency-sensitive upload path from the
  heavy ML path, lets each scale independently, and gives automatic retries +
  dead-lettering. The frontend's real-time listener is unchanged — it still just
  watches the document.

## 6. Observability & ops (brief)
- **Cloud Logging/Monitoring** for request latency, transcription duration, and
  error rate; alert on `status: "error"` write rate.
- **Uptime check** on `/healthz`.
- **Cost guardrails:** budget alerts; cap max instances.
