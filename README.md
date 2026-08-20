# USEVA 2.0

A modern grocery/pantry management web app built with Flask + SQLite + HTML/CSS/JS.

## Features
- Dashboard
- Pantry inventory
- Separate Expiry Soon / Expired tracker
- Manual grocery entry
- Shopping list
- Manual receipts
- Spending/insights dashboard
- Waste logging
- Responsive mobile UI
- Demo data seeding
- Upload-ready image field for future OCR/AI integration

## Run on Windows

```powershell
cd useva_2_0
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Run on macOS/Linux

```bash
cd useva_2_0
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Database
SQLite is created automatically as `useva.db`.

Tables:
- categories
- pantry_item
- receipt
- receipt_item
- shopping_item
- waste_log

## Next production upgrades
1. Flask-Login user accounts and household sharing
2. PostgreSQL for production
3. OCR receipt extraction API
4. Vision model for Grocery Snap
5. Recipe recommendation engine
6. Email/browser expiry notifications
7. CSV/PDF exports
8. CSRF protection and environment-based secrets
9. REST API
10. Cloud image storage


## USEVA 2.0 Smart Scan

### 1. Scan Receipt
The Receipts page now accepts a receipt image. USEVA:
- saves the original image
- runs local Tesseract OCR when available
- extracts store name, total and simple line items
- falls back to Gemini Vision when `GEMINI_API_KEY` is configured
- stores the scanned receipt and extracted items
- lets you add the extracted items to the pantry

For local OCR on Windows, install the Tesseract OCR application separately and make sure `tesseract.exe` is on PATH. Then install the Python packages from `requirements.txt`.

### 2. Grocery Snap
Grocery Snap accepts a grocery photo from desktop or mobile camera and uses Gemini Vision to identify visible products. The detected list can be reviewed and selected before adding items to the pantry.

Set your Gemini key before starting Flask:

```powershell
$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
python app.py
```

For a permanent Windows environment variable:

```powershell
setx GEMINI_API_KEY "YOUR_GEMINI_API_KEY"
```

Restart the terminal after `setx`.

### Recommended test flow
1. Open `/receipts`.
2. Upload a clear grocery receipt.
3. Click **Scan Receipt**.
4. Confirm the scanned receipt appears in History.
5. Click **+ Pantry** to import its detected items.
6. Open **Grocery Snap** from the dashboard quick-add button.
7. Upload/take a grocery photo.
8. Review detected products and click **Add selected to pantry**.

Never commit your Gemini API key to GitHub.


## Scan and editing behavior

- Receipt Scan uses AI vision first when `GEMINI_API_KEY` is configured, with conservative multi-pass Tesseract OCR as a fallback.
- Scanned line items are shown for review before pantry import. Item name, quantity, line price, category, and custom category can be edited.
- Selecting `Other` exposes a custom category field, so users can create names such as `Frozen Foods`. User-created categories are stored and reused by Receipt Scan, Grocery Snap, Manual Entry, and Pantry.
- Pantry items have an Edit action for correcting names, quantity, unit, price, dates, location, notes, and category.
- The packaged database is intentionally empty except for the nine built-in categories. Demo data is available only through the explicit **Load demo data** action in Settings.
- Uploaded test scan files are not included in the packaged database/uploads folder.

## Latest USEVA 2.0 updates
- Manual-entry modal is vertically scrollable so the **Add to pantry** button remains reachable on smaller screens.
- Location is a shared dropdown: **Pantry, Fridge, Cupboards, Freezer, Counter, Other**.
- The same location choices are available in Manual Entry, Receipt Scan, Grocery Snap and Pantry Edit.
- Branch profiles are available from the top bar and Settings. Each branch has separate pantry, receipts, shopping list, waste records and insights.
- Settings includes **Clear current branch data** and **Clear all inventory data**, each protected by two confirmations. Categories/custom categories and branch accounts remain.
- The packaged database starts clean: no pantry, receipt, receipt-item, shopping-list or waste records are preloaded. Demo data is available only through **Load demo data**.

## Authentication, private branches and separate databases

USEVA 2.0 now requires an account before opening the app.

- **Username + password:** register with a username, email and password (passwords are stored as secure Werkzeug hashes, never plaintext).
- **Google Login:** configure `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`. The Google OAuth redirect URI is `http://127.0.0.1:5000/auth/google/callback` for local development.
- **Private branches:** each account gets its own `Home` branch. The branch switcher and **＋** button only operate on branches belonging to the signed-in account.
- **User data isolation:** pantry, receipts, shopping and waste records carry the authenticated user's ID and are filtered by both user and branch.
- **Separate databases:** `auth.db` stores credentials/account identity, `useva.db` stores grocery/pantry data, and `activity.db` stores account activity history.
- **Activity page:** open **Activity** from the sidebar to review recent actions for the signed-in account.

### Google Cloud setup

1. Create an OAuth 2.0 Web Application client in Google Cloud Console.
2. Add `http://127.0.0.1:5000/auth/google/callback` as an authorized redirect URI.
3. Put the generated values in `.env`:

```text
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
```

Do not commit `.env`, OAuth secrets or API keys to GitHub.

### Run

```powershell
python -m venv venv
venv\Scriptsctivate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` and create an account.
