# Lessons Learned — Deploying VoiceCheck

A retrospective of taking VoiceCheck (async voice-feedback app for PronunCise)
from a working local project to a live, free-tier, CI/CD-driven deployment.

This documents **what we deployed**, **the problems we hit**, **the choices we
made and why**, and **how it can still be optimized**.

---

## 1. The goal

Host the whole stack live, with a CI/CD pipeline, **without spending any
money**, and keep the AI model working.

The app has three moving parts:

- **Frontend** — React + TypeScript + Vite + Tailwind (static build).
- **Backend** — FastAPI + Whisper (transcription) + an LLM (feedback), running
  an async pipeline via `BackgroundTasks`.
- **External services** — Firebase Auth + Firestore (metadata), an LLM
  provider, and audio storage.

---

## 2. The final architecture

| Layer | Service chosen | Free tier |
|---|---|---|
| Frontend | **Cloudflare Pages** | Unlimited bandwidth, no card required |
| Backend | **Google Cloud Run** (Docker) | 2M req/mo, 360k GiB-sec, 180k vCPU-sec; card on file, no charge inside free tier |
| LLM | **Groq API** | Free rate-limited tier (replaces local Ollama, no GPU needed) |
| Audio storage | **Cloudflare R2** | 10 GB, S3-compatible, no card required |
| Auth + DB | **Firebase** (Spark plan) | Already free |
| CI/CD | **GitHub Actions** | Free for this usage |

Deploys trigger on every push to the **`prod`** branch — backend and frontend
have separate workflows, each path-filtered to its own folder so unrelated
changes don't trigger a deploy.

---

## 3. Key decisions and why

### 3.1 Why Cloud Run for the backend (not Hugging Face)
- **Hugging Face Spaces** would work but couples us to their runtime and
  sleeping behavior; we wanted a plain Docker container we fully control.
- **Cloud Run** runs our actual `Dockerfile` as a container, scales to zero
  (so it's free when idle), and supports the knobs we need
  (`--no-cpu-throttling`, custom memory/CPU, a dedicated runtime identity).

### 3.2 Why Groq instead of Ollama in production
- Ollama needs a local model + meaningful RAM, which doesn't fit comfortably
  alongside Whisper on a cost-conscious Cloud Run instance, and there's no GPU.
- Groq offers a free hosted API. The code already had a provider switch:
  `provider = "Groq" if settings.groq_api_key else "Ollama"`, falling back to
  deterministic mock feedback if neither is reachable. So **the same code path**
  serves local dev (Ollama) and production (Groq) with zero branching — just an
  env var difference.

### 3.3 Why Cloudflare R2 for audio (not Firebase Storage, not local disk)
- **Cloud Run's disk is ephemeral** — each instance gets a fresh, empty
  filesystem, and instances are created/destroyed on demand. Anything written
  locally vanishes when the instance recycles or scales to zero.
- **Firebase Storage** would work but is a paid add-on beyond modest limits.
- **R2** is S3-compatible, has a free 10 GB tier, no card required, and serves
  files from a public `r2.dev` URL independent of the backend host. The audio
  storage layer is pluggable (`create_audio_storage`), so this was a config
  choice, not a rewrite.

### 3.4 Why a dedicated runtime service account
Rather than letting Cloud Run use the implicit default compute service account,
we created a dedicated, least-privilege `voicecheck-runtime` SA granted **only**
Firestore access. The deploy SA (used by CI to build/push/deploy) is kept
separate from the runtime SA (the identity the running service uses). This is
cleaner security hygiene and made the cross-project Firestore grant explicit.

### 3.5 Why JSON key auth (after trying Workload Identity Federation)
We initially set up keyless **Workload Identity Federation** (the more secure,
recommended approach for GitHub Actions → GCP). After hitting friction with the
pool/provider/`principalSet` binding setup, we pivoted back to the simpler
**service-account JSON key** stored as a GitHub secret. Trade-off accepted: a
long-lived secret in exchange for far less setup complexity, acceptable for a
free-tier hobby/project deployment. (WIF remains the better choice for anything
production-critical.)

### 3.6 Why deploy from the `prod` branch (not `main`)
`main` stays the working/integration branch; `prod` is the explicit "ship it"
trigger. This avoids deploying every in-progress commit and gives an obvious
promotion step.

### 3.7 Why declarative env vars in the workflow (the final big improvement)
Originally, runtime config (`GROQ_API_KEY`, `CORS_ORIGINS`, `PUBLIC_BASE_URL`,
R2 creds…) was set manually with `gcloud run services update` after deploying.
That's error-prone and easy to forget. We moved to the workflow **writing a
full env-vars YAML from GitHub secrets and re-applying it on every deploy**, so
the live service can never silently drift from what's declared in the repo's
secrets. Single source of truth, reproducible deploys, no manual post-steps.

---

## 4. Problems we faced (and how we fixed them)

### 4.1 Two separate GCP projects caused repeated confusion
There were **two** GCP projects:
- `voicecheck-d3xxxx` — Firebase / Firestore.
- `voicecheck-49xxxx` — Cloud Run / Artifact Registry / deploy SA.

This mismatch was the root cause of several downstream errors. **Fix:** be
explicit about which project ID goes where in every command, and use
**cross-project IAM grants** (a service account in project A can be granted
roles on project B).

### 4.2 Org policy blocked service-account key creation
`gcloud iam service-accounts keys create` failed with
`FAILED_PRECONDITION: Key creation is not allowed on this service account`
because the org policy `constraints/iam.disableServiceAccountKeyCreation` was
enforced on `voicecheck-49xxxx`.
**Fix:** create the deployer SA and its key in the *other* project
(`voicecheck-d3xxxx`, where key creation wasn't blocked) and grant it the
needed roles **cross-project** on `voicecheck-49xxxx`.

### 4.3 "Service account …-compute@… does not exist"
The Firestore IAM grant was run against the wrong project's default compute SA
(which had never been provisioned).
**Fix:** stop relying on the implicit default compute SA entirely — create an
explicit `voicecheck-runtime` SA and grant *it* `roles/datastore.user` on the
Firestore project, then wire it in via `--service-account`.

### 4.4 Firestore "API has not been used in project voicecheck-49xxxx"
After a successful deploy, Firestore calls failed. `firebase_admin` with
Application Default Credentials inferred the project from the **Cloud Run
metadata server** (`voicecheck-49xxxx`) instead of the actual Firestore project
(`voicecheck-d3xxxx`).
**Fix (two layers):**
- Quick: set `GOOGLE_CLOUD_PROJECT=voicecheck-d3xxxx` as an env var (firebase_admin
  checks env vars before the metadata server).
- Proper: added a `FIRESTORE_PROJECT_ID` setting and pass
  `options={"projectId": ...}` explicitly to `firebase_admin.initialize_app()`,
  so project resolution no longer depends on where the code happens to run.

### 4.5 Cloudflare Pages deploy: "Project not found"
The frontend deploy failed with
`Project not found. The specified project name does not match any of your
existing projects.` The `cloudflare/pages-action` **deploys to an existing
project — it does not create one**, contrary to an earlier assumption.
**Fix:** create the Pages project once up front (dashboard, or
`npx wrangler pages project create voicecheck --production-branch=prod`), then
re-run the workflow.

### 4.6 Finding the Cloudflare Account ID
Not obvious from the API Tokens page.
**Fix:** it's in the dashboard URL (`dash.cloudflare.com/<ACCOUNT_ID>/…`) or the
Workers & Pages / R2 overview page's right sidebar.

### 4.7 Audio playback failed: `ERR_CONNECTION_REFUSED` to localhost:8000
With R2 not yet configured, the backend fell back to local-disk storage and
built playback URLs from `PUBLIC_BASE_URL`, which still defaulted to
`http://localhost:8000`. The browser tried to reach the *user's own machine*,
not the server — and also tripped a Mixed-Content warning (HTTPS page → HTTP
resource).
**Fix:** set `PUBLIC_BASE_URL` to the real Cloud Run URL (and, properly,
configure R2 so audio is served from a durable public URL instead of the
ephemeral container disk).

### 4.8 Feedback was always the mock fallback
Logs showed `Ollama feedback failed (Connection refused); using mock fallback`.
`GROQ_API_KEY` was never set on Cloud Run, so the provider switch chose Ollama
(which isn't running there). The earlier successful Groq test was **local only**.
**Fix:** set `GROQ_API_KEY` on the service. Note: submissions created *before*
the fix keep their mock feedback baked into Firestore — only new submissions
pick up the real provider.

### 4.9 CORS blocked the frontend after it went live
The browser's `Origin` header is matched **exactly** — no trailing slash, no
path. The backend's `CORS_ORIGINS` still pointed at `localhost`, so requests
from the live Pages URL were blocked (showing up as a generic "Upload failed").
**Fix:** set `CORS_ORIGINS` to the exact Pages origins
(`https://prod.voicecheck-8xy.pages.dev`, plus the bare project domain), with
**no trailing slash**.

### 4.10 `gcloud` env-var flag footgun: `--set-` vs `--update-`
`--set-env-vars` / `--set-secrets` **replace the entire set** (wiping anything
not listed). `--update-env-vars` / `--update-secrets` **merge** (preserve the
rest). An early claim that `--set-env-vars` "carries forward whatever isn't
touched" was **wrong** and was corrected.
**Rule:** use `--update-env-vars` for incremental changes; only use `--set-`
when you intentionally want a full replace (which is exactly what the final
declarative workflow does, on purpose, from a complete YAML).

### 4.11 Multiple comma-separated origins in one `gcloud` flag
`CORS_ORIGINS` contains commas, but `gcloud` uses commas to separate env-var
entries.
**Fix:** the `^@^` delimiter trick
(`--update-env-vars="^@^CORS_ORIGINS=a,b"`), or — better — the env-vars **YAML
file** approach the final workflow uses, which sidesteps escaping entirely.

### 4.12 Untracked workflow files vanished
The `.github/workflows/*.yml` files were untracked and got wiped from disk
(committing only already-tracked files, plus a clean step). They had to be
fully recreated.
**Lesson:** commit infra/workflow files early; don't leave them untracked.

### 4.13 CPU throttling would starve the background pipeline
Cloud Run throttles CPU after the HTTP response is sent by default, but our
pipeline (transcribe → feedback → Firestore write) runs **after** the response
via `BackgroundTasks`.
**Fix:** deploy with `--no-cpu-throttling` so background work actually completes.

---

## 5. How to reproduce the deploy (condensed runbook)

1. **Groq**: create a free API key.
2. **Cloudflare R2**: create a bucket, an Object-Read/Write API token, and
   enable the bucket's public `r2.dev` URL.
3. **GCP**: create/choose a project; enable Cloud Run + Artifact Registry APIs;
   create the Artifact Registry Docker repo; create the deploy SA (+ JSON key,
   possibly cross-project) and the dedicated `voicecheck-runtime` SA (granted
   Firestore access on the Firestore project).
4. **Cloudflare Pages**: create the Pages project once; get an API token + the
   Account ID.
5. **GitHub repo secrets**: `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_SA_KEY`,
   `GROQ_API_KEY`, `FIRESTORE_PROJECT_ID`, `PUBLIC_BASE_URL`, `CORS_ORIGINS`,
   the `R2_*` set, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, the six
   `VITE_FIREBASE_*`, and `VITE_API_BASE_URL`.
6. **Push to `prod`** → both workflows deploy automatically.

See `README.md` → "Deploying for free" for the full commands.

---

## 6. How we can still optimize

### Reliability & correctness
- **Cold starts:** `--min-instances=0` means the first request after idle pays a
  cold-start penalty (container boot + Whisper model load). Set
  `--min-instances=1` for a warm instance (trade-off: leaves the free tier and
  costs a little). Or keep 0 and add a frontend "warming up…" state.
- **Whisper model load time:** loading the model on every cold start is slow.
  Consider baking the model into the image, using a smaller model, or caching it.
- **Migrate to Workload Identity Federation:** remove the long-lived
  `GCP_SA_KEY` JSON key in favor of keyless OIDC auth — eliminates a standing
  credential secret.
- **Consolidate to a single GCP project** (or fully document the two-project
  setup): the split was the source of most of the IAM/Firestore pain.

### Cost & performance
- **Right-size memory/CPU:** `2Gi`/`2 vCPU` was chosen conservatively for
  Whisper. Profile actual usage and trim if possible to stay deeper inside the
  free tier.
- **Frontend bundle is >500 kB** (Vite warned). Code-split with dynamic
  `import()` and/or `manualChunks` to cut initial load.
- **R2 lifecycle rules:** auto-expire old audio objects to stay under 10 GB
  without manual cleanup.

### Developer experience & safety
- **Staging environment:** a second Cloud Run service + Pages project fed from a
  `staging` branch, so `prod` isn't the first place a change runs live.
- **Smoke test in CI:** after deploy, hit a health endpoint and fail the
  workflow if it's unhealthy (catch bad deploys before users do).
- **Secret validation step:** fail fast in CI if a required secret is empty,
  rather than deploying a silently-broken service (this would have caught the
  missing `GROQ_API_KEY` / `PUBLIC_BASE_URL` immediately).
- **Structured logging + error reporting:** wire Cloud Run logs into a
  dashboard/alert so failures (like the Firestore-API error) surface
  proactively instead of via user reports.
- **Remove dead code:** the `FirebaseAudioStorage` class is no longer reachable
  from the `create_audio_storage` factory — delete it or restore it as an
  intentional option to avoid confusion.

### Data
- **Custom domain** for both Pages (frontend) and the R2 public bucket, instead
  of `*.pages.dev` / `pub-*.r2.dev`, for a more professional URL and stable
  CORS origins.
- **Backfill/cleanup:** the early test submissions have broken audio URLs and
  mock feedback baked into Firestore — a one-off cleanup script could remove or
  reprocess them.

---

## 7. The single biggest takeaway

**Runtime configuration should live in one declarative place, applied
automatically — never typed by hand after the fact.** Almost every production
incident here (wrong CORS origin, missing Groq key, localhost playback URL, the
`--set` vs `--update` footgun) traced back to config being set manually and
drifting out of sync. Moving the full env-var set into the deploy workflow,
sourced from version-controlled secrets and re-applied on every deploy, removed
that entire category of problems.

---

## Appendix A — Full step-by-step deployment guide (beginner friendly)

This is the exact path we followed, written so someone who has never deployed
anything can follow along. Do the parts **in order** — later steps depend on
values you collect in earlier ones.

Before you start, keep a blank notepad open. Throughout, you'll copy down small
pieces of text (IDs, URLs, keys). At the very end you paste them all into GitHub
as "secrets". A 🔑 means "write this value down — you'll need it later."

The real values we used are shown as examples so you can see the shape of each
one. Yours will be different.

### Part 0 — Accounts you need (all free)
1. A **GitHub** account, with this project pushed to a repository.
2. A **Google Cloud** account — go to <https://console.cloud.google.com>, sign
   in, and add a credit/debit card when asked. (Cloud Run requires a card on
   file, but you will **not** be charged while you stay inside the free tier.)
3. A **Cloudflare** account — <https://dash.cloudflare.com>.
4. A **Groq** account — <https://console.groq.com>.
5. A **Firebase** project (you already had this from local development).

> Two important IDs we'll keep referring to. We had **two separate Google
> projects** — this is the #1 thing that confused us, so be deliberate about
> which is which:
> - **Firebase / Firestore project** — holds login + the database.
>   Example: `voicecheck-d3xxxx`. 🔑
> - **Google Cloud project** — runs the backend container.
>   Example: `voicecheck-49xxxx`. 🔑
>
> If you're starting fresh, life is much simpler if you use **one** project for
> both. We had two only because the Firebase project already existed.

---

### Part 1 — Get the Groq API key (the AI model)
1. Go to <https://console.groq.com/keys>.
2. Click **Create API Key**, give it a name, click create.
3. Copy the key immediately (it's shown only once). 🔑 `GROQ_API_KEY`

---

### Part 2 — Set up Cloudflare R2 (where audio files are stored)
1. In the Cloudflare dashboard, left sidebar → **R2 Object Storage**.
   (If it asks you to enable R2, accept — it's free, no card needed.)
2. **Create a bucket** → name it e.g. `voicecheck-audio` → Create.
   🔑 `R2_BUCKET_NAME` = `voicecheck-audio`
3. Find your **Account ID**: look at the address bar — the URL is
   `https://dash.cloudflare.com/<long-id>/...`. That long id is it.
   🔑 `R2_ACCOUNT_ID`
4. Create an access key pair: in **R2 Object Storage** → **Manage API Tokens**
   (top-right) → **Create API Token**:
   - Permission: **Object Read & Write**.
   - Apply to your bucket (or all buckets).
   - Click create. It shows an **Access Key ID** and a **Secret Access Key**
     **once**. Copy both now.
     🔑 `R2_ACCESS_KEY_ID`  🔑 `R2_SECRET_ACCESS_KEY`
5. Make the bucket's files publicly readable: open the bucket → **Settings** →
   **Public access** → enable the **r2.dev** subdomain. Cloudflare gives you a
   URL like `https://pub-abc123.r2.dev`.
   🔑 `R2_PUBLIC_BASE_URL` (no trailing slash)

---

### Part 3 — Prepare Google Cloud (the backend host)

You'll run commands in **Cloud Shell** — a terminal built into the Google Cloud
website (no installs). Open it with the `>_` icon at the top-right of
<https://console.cloud.google.com>.

First tell Cloud Shell which project is your **Google Cloud project**:
```bash
gcloud config set project voicecheck-49xxxx
```

**3.1 Turn on the services we use**
```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com
```

**3.2 Create a place to store the container image**
("Artifact Registry" is just Google's storage for Docker images. `us-central1`
is the region — a data-center location; any nearby region works, just be
consistent everywhere.)
```bash
gcloud artifacts repositories create voicecheck \
  --repository-format=docker --location=us-central1
```
🔑 region = `us-central1` (this is your `GCP_REGION`)

**3.3 Create the "deployer" identity that GitHub will use**
A *service account* is a robot user. This one lets GitHub Actions build and
deploy on your behalf.
```bash
gcloud iam service-accounts create voicecheck-deployer \
  --project=voicecheck-49xxxx
```
Give it the three permissions it needs:
```bash
DEPLOY_SA="voicecheck-deployer@voicecheck-49xxxx.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding voicecheck-49xxxx --member="serviceAccount:$DEPLOY_SA" --role="roles/run.admin"
gcloud projects add-iam-policy-binding voicecheck-49xxxx --member="serviceAccount:$DEPLOY_SA" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding voicecheck-49xxxx --member="serviceAccount:$DEPLOY_SA" --role="roles/iam.serviceAccountUser"
```

**3.4 Download a key file for the deployer**
This JSON file is the deployer's password — GitHub will hold it.
```bash
gcloud iam service-accounts keys create voicecheck-deployer-key.json \
  --iam-account=$DEPLOY_SA
```

> ⚠️ **If this fails** with `Key creation is not allowed on this service
> account`, your organization blocks key creation on this project (policy
> `iam.disableServiceAccountKeyCreation`). This happened to us. The workaround:
> create the deployer **in your other project** (the Firebase one,
> `voicecheck-d3xxxx`, where it wasn't blocked) and grant it the same three
> roles **on the Google Cloud project** instead. Same three
> `add-iam-policy-binding` commands as above, but with the SA email ending in
> `@voicecheck-d3xxxx.iam.gserviceaccount.com`.

Now open the key file's contents so you can copy them:
```bash
cat voicecheck-deployer-key.json
```
Copy the **entire** output (the whole `{ ... }` block). 🔑 `GCP_SA_KEY`

**3.5 Create the "runtime" identity the backend runs as**
Separate robot user, with the *least* access needed — only the database.
```bash
gcloud iam service-accounts create voicecheck-runtime \
  --project=voicecheck-49xxxx
```
Grant it database access **on the Firebase project** (note: the project name
here is the *Firestore* one, `voicecheck-d3xxxx` — this cross-project grant is
exactly what tripped us up, so double-check it):
```bash
gcloud projects add-iam-policy-binding voicecheck-d3xxxx \
  --member="serviceAccount:voicecheck-runtime@voicecheck-49xxxx.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

---

### Part 4 — Create the Cloudflare Pages project (the frontend host)

The deploy automation can only *publish to* an existing Pages project; it does
**not** create one. So make an empty one first.

Easiest way (dashboard):
1. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** tab →
   **Upload assets** (NOT "Connect to Git").
2. Project name: type exactly **`voicecheck`** (must match what the workflow
   expects).
3. Upload any tiny placeholder folder when asked (it gets overwritten on the
   first real deploy). Click **Deploy site**.

Then create an API token so GitHub can publish to it:
1. Profile → **API Tokens** → **Create Token** → use the **Edit Cloudflare
   Pages** template → create.
2. Copy the token. 🔑 `CLOUDFLARE_API_TOKEN`
3. Your `CLOUDFLARE_ACCOUNT_ID` is the same Account ID from Part 2, step 3. 🔑

After the first successful deploy, Cloudflare gives the site a URL like
`https://prod.voicecheck-8xy.pages.dev`. 🔑 (you'll need it for CORS in Part 6)

---

### Part 5 — Collect the Firebase web values
These are the public config values your frontend uses to talk to Firebase. In
the Firebase console → Project settings → "Your apps" → web app config, copy
the six values:
🔑 `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`,
`VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_STORAGE_BUCKET`,
`VITE_FIREBASE_MESSAGING_SENDER_ID`, `VITE_FIREBASE_APP_ID`.

(They're already in your local root `.env` file too.)

---

### Part 6 — Put every value into GitHub as "secrets"

In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add each of these (name on the left, the value you wrote
down on the right):

| Secret name | What it is | Example |
|---|---|---|
| `GCP_PROJECT_ID` | Google Cloud project | `voicecheck-49xxxx` |
| `GCP_REGION` | region | `us-central1` |
| `GCP_SA_KEY` | the whole deployer JSON key file contents | `{ "type": ... }` |
| `GROQ_API_KEY` | Groq key | `gsk_...` |
| `FIRESTORE_PROJECT_ID` | the Firebase project (only needed because ours differs from `GCP_PROJECT_ID`) | `voicecheck-d3xxxx` |
| `PUBLIC_BASE_URL` | the backend's own URL (you'll fill this after the first backend deploy — see note) | `https://voicecheck-backend-xxxx.us-central1.run.app` |
| `CORS_ORIGINS` | your Pages URL(s), comma-separated, **no trailing slash** | `https://prod.voicecheck-8xy.pages.dev,https://voicecheck-8xy.pages.dev` |
| `R2_ACCOUNT_ID` | Cloudflare account id | `abc123...` |
| `R2_ACCESS_KEY_ID` | R2 access key | from Part 2 |
| `R2_SECRET_ACCESS_KEY` | R2 secret | from Part 2 |
| `R2_BUCKET_NAME` | bucket name | `voicecheck-audio` |
| `R2_PUBLIC_BASE_URL` | bucket public URL | `https://pub-abc123.r2.dev` |
| `CLOUDFLARE_API_TOKEN` | Pages token | from Part 4 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account id | same as `R2_ACCOUNT_ID` |
| `VITE_FIREBASE_API_KEY` … (all six) | Firebase web config | from Part 5 |
| `VITE_API_BASE_URL` | the backend's URL (same value as `PUBLIC_BASE_URL`) | `https://voicecheck-backend-xxxx.us-central1.run.app` |

> **Chicken-and-egg with the backend URL:** you don't know the exact Cloud Run
> URL until the backend has deployed once. So: add every other secret first,
> deploy the backend (Part 7), copy the URL it prints, then come back and add
> `PUBLIC_BASE_URL` and `VITE_API_BASE_URL`, and re-run the deploys. This is
> normal — we did exactly this.

---

### Part 7 — Deploy

Everything is automated by two workflow files already in the repo:
`.github/workflows/deploy-backend.yml` and `.../deploy-frontend.yml`. They run
when you push to the **`prod`** branch (each only when its own folder changes),
or you can run them by hand.

**To deploy:**
- Push your changes to the `prod` branch:
  ```bash
  git checkout prod
  git merge main          # or however you promote changes
  git push origin prod
  ```
- OR trigger manually: GitHub repo → **Actions** tab → pick the workflow →
  **Run workflow**.

Watch progress under the **Actions** tab. A green check = success.

**First-run order that worked for us:**
1. Deploy the **backend** first. When it finishes, open it in the Google Cloud
   console → Cloud Run → `voicecheck-backend` and copy its URL (e.g.
   `https://voicecheck-backend-903100285094.us-central1.run.app`).
2. Put that URL into the `PUBLIC_BASE_URL` and `VITE_API_BASE_URL` GitHub
   secrets, and make sure it's part of `CORS_ORIGINS` logic (CORS is the Pages
   URL, not the backend URL — don't mix these up).
3. Re-run the backend deploy (so it picks up `PUBLIC_BASE_URL`), then deploy the
   **frontend**.

> Because the backend workflow re-applies **all** runtime settings from your
> GitHub secrets on every deploy, you never have to run `gcloud` config
> commands by hand. Change a setting = update the secret = re-run the workflow.

---

### Part 8 — Check it actually works
1. Open your Pages URL (`https://prod.voicecheck-8xy.pages.dev`).
2. Sign up / log in.
3. Record and submit a short clip.
4. It should move to "processing" then "done", show real AI feedback (not the
   generic mock text), and let you play the audio back.
5. If something fails, open the browser's **DevTools → Console** tab — the error
   there tells you which piece is misconfigured. Cross-reference it with the
   "Problems we faced" section above; we hit most of the common ones.

> Remember: any submission you made **before** fixing a setting keeps its old
> (broken) data saved in the database. Always test with a **fresh** submission
> after each fix.
