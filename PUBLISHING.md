# AEROWIND — Safe Publishing Checklist

Follow these steps **in order** before pushing to a public GitHub repository.

---

## Step 1 — Handle the nested `frontend/.git` repository

The `frontend/` directory was bootstrapped with `create-next-app` and already
contains its own Git history (`frontend/.git/`).
If you initialise a Git repo at the AEROWIND root with that directory present,
Git will treat `frontend/` as an **untracked submodule / gitlink** — its source
code will **not** be committed and will appear as an empty folder to cloners.

**Choose exactly ONE of the options below:**

### Option A — Remove the nested history (recommended)

```powershell
# WARNING: This deletes only the nested .git — no source files are affected.
Remove-Item -Recurse -Force d:\AEROWIND\frontend\.git
```

After this, `frontend/` becomes a plain directory and will be committed normally.

### Option B — Keep frontend as a proper Git submodule

Only choose this if you want to maintain the frontend as a separate repo.
This is more complex and requires setting up a separate remote for it.

---

## Step 2 — Initialise the root repository

```powershell
cd d:\AEROWIND
git init
git branch -M main
```

---

## Step 3 — Verify nothing sensitive will be committed

```powershell
# Show every file Git currently sees (should NOT include .env, *.db, etc.)
git status
```

Double-check these are **absent** from the output:
- `backend/.env` or any `.env` file (not `.env.example`)
- `aerowind.db` / `backend/aerowind.db`
- Any `*.key`, `*.pem`, `*.p12` files
- `frontend/node_modules/` or `frontend/.next/`
- `backend/__pycache__/` directories

---

## Step 4 — Stage and commit

```powershell
git add .
git status   # review the staged list one more time
git commit -m "chore: initial public release"
```

---

## Step 5 — Create the GitHub repository and push

```powershell
# Replace <YOUR_GITHUB_USERNAME> and <REPO_NAME>
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<REPO_NAME>.git
git push -u origin main
```

---

## Step 6 — Post-publish checks

1. Browse the repository on GitHub and confirm:
   - No `.env` file is present (only `.env.example`)
   - No `*.db` database files are present
   - `frontend/` contains actual source files (not an empty gitlink)
   - No API keys appear anywhere in the file tree
2. Enable **GitHub Secret Scanning** (Settings → Security → Secret scanning)
3. Enable **Dependabot alerts** (Settings → Security → Dependabot)

---

## Notes on the current license

The project README currently states:
> *"AEROWIND — Hackathon project. All rights reserved."*

This means the project is **not yet open-source**. Before publishing publicly,
decide on a licence and add a `LICENSE` file (e.g. MIT, Apache-2.0).
GitHub's licence picker: <https://choosealicense.com/>

Do **not** add a licence file that you did not deliberately choose — omitting
it is safer than accidentally claiming a licence you didn't intend.
