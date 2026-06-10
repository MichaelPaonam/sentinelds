# SentinelDS Landing Page

Single-page cyberpunk marketing site for the SentinelDS hackathon demo.

## Stack

- **Preact** + **Vite** (no React, Next.js, Tailwind, or shadcn)
- Plain CSS with design tokens

## Commands

```bash
cd landing
npm install
npm run dev      # start dev server
npm run build    # production build to dist/
npm run preview  # preview production build
npm run deploy   # build + deploy to Firebase Hosting
```

## Sections

1. **Hero** — glitch headline, HUD panel, scanline overlay
2. **How It Works** — Emit → Detect → Decide → Enforce
3. **Attacks Demo** — A1 prompt injection + A2 data poisoning
4. **Tech Stack** — ADK, Gemini, Dynatrace, Sentinel
5. **Team**

## Deploy to Firebase Hosting

Firebase Hosting serves the static `dist/` folder. It fits the Google Cloud hackathon
because Firebase projects link to the same GCP account as Cloud Run / Vertex.

### One-time setup

**1. Install Firebase CLI** (Node.js required):

```powershell
npm install -g firebase-tools
```

**2. Log in to Google:**

```powershell
firebase login
```

**3. Create or link a Firebase project** (skip if `sentinelds-28731` already has Firebase):

- Open [Firebase Console](https://console.firebase.google.com/)
- **Add project** → pick existing GCP project `sentinelds-28731`, or create a new one
- In the project, go to **Build → Hosting → Get started** (enables Hosting)

**4. Confirm the active project** (from the `landing/` folder):

```powershell
cd landing
firebase projects:list
firebase use sentinelds-28731
```

If your Firebase project ID differs, edit `.firebaserc` or run:

```powershell
firebase use --add
```

**5. Install landing dependencies** (if you have not already):

```powershell
npm install
```

Config is already in this folder:

- `firebase.json` — publish `dist/`, cache assets, SPA fallback
- `.firebaserc` — default project `sentinelds-28731`

You do **not** need to run `firebase init hosting` again unless you want to change settings.

### Deploy

```powershell
cd landing
npm run deploy
```

Or step by step:

```powershell
npm run build
firebase deploy --only hosting
```

When it finishes, the CLI prints your live URL, e.g.:

- `https://sentinelds-28731.web.app`
- `https://sentinelds-28731.firebaseapp.com`

(Custom domains can be added under **Hosting → Add custom domain** in the Firebase console.)

### Update after changes

Edit the site, then from `landing/`:

```powershell
npm run deploy
```

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `Firebase project not found` | Create Firebase for the GCP project in the console, then `firebase use <project-id>` |
| `HTTP Error: 403` | Run `firebase login` again; ensure your Google account has Editor/Owner on the GCP project |
| Blank page after deploy | Run `npm run build` first; confirm `landing/dist/index.html` exists |
| Wrong project deployed | Check `.firebaserc` and `firebase use` |
