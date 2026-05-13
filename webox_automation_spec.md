# WeBox Menu Automation — Claude Code Spec
### Goal: Automatically pull the daily WeBox menu every weekday at 7:00 AM PT, upload it to Google Drive, maintain a rolling 5-workday archive, and make it available for Claude to analyze alongside the meal planner.

---

## Overview

The existing `webox_scrape.py` script calls the WeBox API and exports the daily menu to a CSV. This spec extends that script and adds a GitHub Actions workflow to:

1. Run automatically every weekday at 7:00 AM Pacific Time
2. Upload the resulting CSV to a dedicated Google Drive folder
3. Maintain a rolling 5-workday archive — oldest file deleted when a new one is added
4. Overwrite today's file if it already exists (idempotent runs)

Claude will read the Drive folder on demand to analyze available menu items against the user's macro planner.

---

## Architecture

```
GitHub Actions (cron: Mon-Fri 7am PT)
    ↓
webox_scrape.py (modified)
    ↓ fetches menu from WeBox API
    ↓ exports CSV: webox_menu_YYYY-MM-DD_lunch.csv
    ↓ uploads to Google Drive folder "WeBox Daily Menus"
    ↓ deletes files older than 5 workdays from that folder
Google Drive folder: "WeBox Daily Menus"
    → webox_menu_2026-05-13_lunch.csv
    → webox_menu_2026-05-12_lunch.csv
    → webox_menu_2026-05-11_lunch.csv
    → webox_menu_2026-05-08_lunch.csv
    → webox_menu_2026-05-07_lunch.csv  ← oldest kept
Claude reads folder on demand
```

---

## Part 1 — One-Time Google Cloud Setup

This is required before any code changes. Follow these steps exactly once.

### Step 1: Create a Google Cloud Project

1. Go to https://console.cloud.google.com
2. Click the project dropdown at the top → **New Project**
3. Name it `webox-menu-automation`
4. Click **Create**

### Step 2: Enable the Google Drive API

1. In your new project, go to **APIs & Services → Library**
2. Search for "Google Drive API"
3. Click it → click **Enable**

### Step 3: Create a Service Account

A service account lets GitHub Actions authenticate with Google Drive without any user interaction or browser login.

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → Service Account**
3. Name it `webox-drive-uploader`
4. Click **Create and Continue** → skip optional steps → click **Done**

### Step 4: Download the Service Account Key

1. On the Credentials page, click your new service account
2. Go to the **Keys** tab
3. Click **Add Key → Create New Key → JSON**
4. A JSON file downloads to your computer — **keep this safe, treat it like a password**

### Step 5: Create the Google Drive Folder and Share It

1. Open Google Drive
2. Create a new folder named **WeBox Daily Menus** (exact name matters — the script references it)
3. Right-click the folder → **Share**
4. Paste the service account email address (found on the Credentials page, looks like `webox-drive-uploader@webox-menu-automation.iam.gserviceaccount.com`)
5. Set role to **Editor**
6. Click **Share**

The script will now be able to read and write to this folder using the service account credentials.

---

## Part 2 — GitHub Secrets Configuration

In your existing GitHub repo, add the following secrets. Go to **Settings → Secrets and Variables → Actions → New Repository Secret** for each.

| Secret Name | Value |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Paste the entire contents of the JSON key file downloaded in Step 4 |
| `WEBOX_COOKIE` | The full cookie string from `COOKIE_HEADER` in `webox_scrape.py` |
| `WEBOX_ADDRESS_ID` | `239098` (or whatever your address ID is) |

**Why secrets?** The WeBox cookie contains your auth token and will expire. Storing it as a secret means you update it in one place — no code changes needed when it expires. The service account JSON is sensitive credentials that must never be committed to the repo.

**Cookie expiry note:** The JWT token embedded in your WeBox cookie expires periodically. When the script starts failing, update the `WEBOX_COOKIE` secret with a fresh cookie from your browser's DevTools. To get a fresh cookie: open WeBox in Chrome → F12 → Network tab → find any API request → copy the Cookie header value.

---

## Part 3 — Script Modifications

Claude Code should modify `webox_scrape.py` to add two new capabilities:

### 3.1 — Add Google Drive Upload

Add a new function `upload_to_drive(csv_path, folder_name, service_account_json_str)` that:

1. Authenticates using the service account JSON passed as a string (from env var)
2. Finds the Google Drive folder by name (`"WeBox Daily Menus"`)
3. Checks if a file with today's filename already exists in that folder
4. If it exists → delete it (overwrite behavior)
5. Uploads the new CSV to that folder
6. Returns the uploaded file's Drive ID

**Required pip packages to add:**
```
google-api-python-client>=2.0.0
google-auth>=2.0.0
google-auth-httplib2>=0.1.0
```

Add a `requirements.txt` to the repo if one doesn't exist.

### 3.2 — Add Rolling 5-Workday Cleanup

Add a new function `cleanup_old_files(folder_name, service_account_json_str, keep_days=5)` that:

1. Lists all CSV files in the `"WeBox Daily Menus"` folder
2. Parses the date from each filename using the pattern `webox_menu_YYYY-MM-DD_lunch.csv`
3. Calculates the 5 most recent workdays (Mon-Fri only, no weekends) from today
4. Deletes any files whose date is not in that set of 5 workdays
5. Logs which files were deleted

**Workday logic:** Use Python's `datetime` module. To find the last 5 workdays: start from today, step backwards, skip Saturday (weekday 5) and Sunday (weekday 6), collect until 5 days accumulated.

### 3.3 — Modify `main()` to Accept Environment Variables

Update `main()` so that when running in GitHub Actions (no interactive terminal), it reads from environment variables instead of prompting:

```python
# Priority order: CLI arg → env var → interactive prompt
date = args.date or os.environ.get("WEBOX_DATE") or input("Enter date:")
address_id = args.address_id or int(os.environ.get("WEBOX_ADDRESS_ID", 239098))
cookie = args.cookie or os.environ.get("WEBOX_COOKIE") or COOKIE_HEADER
```

Also add at the end of `main()`:
```python
service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
if service_account_json:
    upload_to_drive(output_path, "WeBox Daily Menus", service_account_json)
    cleanup_old_files("WeBox Daily Menus", service_account_json, keep_days=5)
else:
    print("GOOGLE_SERVICE_ACCOUNT_JSON not set — skipping Drive upload.")
```

This means the script still works locally without Drive credentials — Drive upload only activates when the env var is present.

### 3.4 — Updated Output Path for CI

When running in GitHub Actions, there's no `~/OneDrive/Desktop` path. Update the default output path:

```python
if os.environ.get("GITHUB_ACTIONS"):
    default_output = f"webox_menu_{args.date}_{args.time.lower()}.csv"
else:
    default_output = os.path.join(
        os.path.expanduser("~"), "OneDrive", "Desktop",
        f"webox_menu_{args.date}_{args.time.lower()}.csv"
    )
```

---

## Part 4 — GitHub Actions Workflow

Create this file at `.github/workflows/webox_daily.yml` in the repo:

```yaml
name: WeBox Daily Menu Pull

on:
  schedule:
    # 7:00 AM Pacific Daylight Time (PDT) = 14:00 UTC (Mar-Nov)
    # In winter (PST), this runs at 6:00 AM — update to 15:00 UTC Nov-Mar if needed
    - cron: '0 14 * * 1-5'
  workflow_dispatch:
    # Allows manual trigger from GitHub Actions UI — useful for testing
    # and for pulling today's menu if the scheduled run fails

jobs:
  pull-menu:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Set today's date (Pacific Time)
        run: |
          # Force Pacific timezone for date calculation
          echo "WEBOX_DATE=$(TZ='America/Los_Angeles' date +%Y-%m-%d)" >> $GITHUB_ENV

      - name: Run WeBox scraper
        env:
          WEBOX_DATE: ${{ env.WEBOX_DATE }}
          WEBOX_ADDRESS_ID: ${{ secrets.WEBOX_ADDRESS_ID }}
          WEBOX_COOKIE: ${{ secrets.WEBOX_COOKIE }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
        run: |
          python webox_scrape.py \
            --date "$WEBOX_DATE" \
            --time Lunch \
            --page-size 500

      - name: Confirm upload
        run: echo "WeBox menu for $WEBOX_DATE uploaded to Google Drive successfully."
```

**Notes on the workflow:**
- `workflow_dispatch` adds a manual trigger button in the GitHub Actions UI — critical for testing and for days when the scheduled run needs to be re-run
- `page-size 500` fetches the full menu in one API call instead of paginating
- The date is calculated in Pacific Time so the filename always matches the correct calendar day regardless of where GitHub's servers are located

---

## Part 5 — File Naming Convention

Files saved to Google Drive will follow this exact pattern:

```
webox_menu_2026-05-13_lunch.csv
webox_menu_2026-05-12_lunch.csv
webox_menu_2026-05-09_lunch.csv
webox_menu_2026-05-08_lunch.csv
webox_menu_2026-05-07_lunch.csv
```

The date in the filename is always the date the menu was available for ordering, in Pacific Time. Weekends are never included — the rolling 5 days will always be the last 5 Monday-Friday dates.

---

## Part 6 — How Claude Uses This Data

Once the folder is populated, Claude reads the WeBox menu CSV on demand via the Google Drive MCP connector. The workflow:

1. User opens Claude and asks: *"What should I order from WeBox for lunch today?"*
2. Claude fetches today's planner from Google Drive (Meal Prep Master sheet)
3. Claude fetches today's WeBox menu CSV from the `WeBox Daily Menus` folder
4. Claude filters the menu for in-stock items only (`stockStatus = "Instock"`)
5. Claude cross-references item names with any uploaded nutrition PDFs from those restaurants
6. Claude recommends the best macro fit for the user's remaining daily targets

**Important limitation:** The WeBox CSV contains item names, prices, and ratings — but no macro data. Macro analysis requires either an uploaded nutrition PDF for that restaurant, or Claude's estimation based on the dish description. To improve accuracy over time, upload nutrition PDFs from WeBox partner restaurants to the same Google Drive folder as they become available.

---

## Part 7 — Token Refresh Process

The WeBox cookie will expire periodically. When it does, the GitHub Actions run will fail with an authentication error. Here's the refresh process:

1. Open https://www.webox.com in Chrome while logged in
2. Press F12 → go to the **Network** tab
3. Refresh the page or click anything that makes an API call
4. Find any request to `webox.com/api/...`
5. In the request headers, find the **Cookie** header
6. Copy the entire value (it's a long string)
7. Go to your GitHub repo → Settings → Secrets → update `WEBOX_COOKIE` with the new value

No code changes needed. The Actions workflow picks up the new cookie automatically on the next run.

---

## Part 8 — Claude Code Instructions

When handing this spec to Claude Code, give it the following instruction:

> "Modify `webox_scrape.py` according to the spec in `webox_automation_spec.md`. Create `requirements.txt` if it doesn't exist. Create `.github/workflows/webox_daily.yml`. Do not change any existing scraping logic — only add the Drive upload function, the rolling cleanup function, the env var fallbacks in main(), and the CI output path fix. Test that the script still runs locally without Drive credentials."

---

## Summary Checklist

**One-time setup (you do this manually):**
- [ ] Create Google Cloud project `webox-menu-automation`
- [ ] Enable Google Drive API
- [ ] Create service account `webox-drive-uploader`
- [ ] Download service account JSON key
- [ ] Create `WeBox Daily Menus` folder in personal Google Drive
- [ ] Share that folder with the service account email (Editor access)
- [ ] Add `GOOGLE_SERVICE_ACCOUNT_JSON` secret to GitHub repo
- [ ] Add `WEBOX_COOKIE` secret to GitHub repo
- [ ] Add `WEBOX_ADDRESS_ID` secret to GitHub repo

**Claude Code does this:**
- [ ] Add `requirements.txt` with Google API packages
- [ ] Add `upload_to_drive()` function to script
- [ ] Add `cleanup_old_files()` function to script
- [ ] Update `main()` to read env vars and call Drive functions
- [ ] Fix output path for CI environment
- [ ] Create `.github/workflows/webox_daily.yml`

**Verify it works:**
- [ ] Trigger workflow manually from GitHub Actions UI
- [ ] Confirm CSV appears in `WeBox Daily Menus` Drive folder
- [ ] Confirm Claude can read it via Google Drive MCP
- [ ] Wait for next scheduled run to confirm automation works end-to-end
