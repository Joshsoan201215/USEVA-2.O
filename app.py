from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect as sa_inspect, text as sa_text, event
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from pathlib import Path
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import os, json, base64, re, mimetypes, hashlib, sqlite3
from io import BytesIO
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
try:
    from authlib.integrations.flask_client import OAuth
except ImportError:
    OAuth = None

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

try:
    from PIL import Image
except ImportError:
    Image = None
try:
    import pytesseract
except ImportError:
    pytesseract = None
try:
    import requests
except ImportError:
    requests = None

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "useva-change-this-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(BASE_DIR / "useva.db")
app.config["AUTH_DB"] = str(BASE_DIR / "auth.db")
app.config["ACTIVITY_DB"] = str(BASE_DIR / "activity.db")
app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID", "")
app.config["GOOGLE_CLIENT_SECRET"] = os.getenv("GOOGLE_CLIENT_SECRET", "")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = str(BASE_DIR / "static" / "uploads")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

db = SQLAlchemy(app)
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

class Branch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    icon = db.Column(db.String(20), default="🥦")
    color = db.Column(db.String(20), default="#4CAF50")
    items = db.relationship("PantryItem", backref="category", lazy=True)

class PantryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    name = db.Column(db.String(160), nullable=False)
    quantity = db.Column(db.Float, default=1)
    unit = db.Column(db.String(30), default="unit")
    price = db.Column(db.Float, default=0)
    purchase_date = db.Column(db.Date, default=date.today)
    expiry_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(80), default="Pantry")
    status = db.Column(db.String(30), default="active")
    notes = db.Column(db.Text, default="")
    image = db.Column(db.String(255), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"), nullable=True, index=True)

class Receipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    store_name = db.Column(db.String(160), default="Manual Entry")
    receipt_date = db.Column(db.Date, default=date.today)
    total = db.Column(db.Float, default=0)
    image = db.Column(db.String(255), nullable=True)
    image_hash = db.Column(db.String(64), nullable=True)
    receipt_signature = db.Column(db.String(64), nullable=True)
    source = db.Column(db.String(30), default="manual")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"), nullable=True, index=True)
    items = db.relationship("ReceiptItem", backref="receipt", cascade="all, delete-orphan")

class ReceiptItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey("receipt.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    quantity = db.Column(db.Float, default=1)
    unit = db.Column(db.String(30), default="unit")
    unit_price = db.Column(db.Float, default=0)
    category = db.Column(db.String(80), default="Other")
    purchase_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(80), default="Pantry")
    notes = db.Column(db.Text, default="")

class ShoppingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    name = db.Column(db.String(160), nullable=False)
    quantity = db.Column(db.Float, default=1)
    unit = db.Column(db.String(30), default="unit")
    checked = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default="normal")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"), nullable=True, index=True)

class WasteLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    item_name = db.Column(db.String(160), nullable=False)
    quantity = db.Column(db.Float, default=1)
    reason = db.Column(db.String(120), default="Expired")
    estimated_value = db.Column(db.Float, default=0)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)
    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"), nullable=True, index=True)


# -------------------- Authentication --------------------
def auth_conn():
    conn = sqlite3.connect(app.config["AUTH_DB"])
    conn.row_factory = sqlite3.Row
    return conn

def init_auth_db():
    conn = auth_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT UNIQUE,
        password_hash TEXT,
        google_sub TEXT UNIQUE,
        display_name TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login TEXT
    );
    CREATE TABLE IF NOT EXISTS auth_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()

def activity_conn():
    conn = sqlite3.connect(app.config["ACTIVITY_DB"])
    conn.row_factory = sqlite3.Row
    return conn

def init_activity_db():
    conn = activity_conn()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        endpoint TEXT,
        details TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def log_activity(action, details="", user_id=None):
    uid = user_id or session.get("user_id")
    if not uid:
        return
    try:
        conn = activity_conn()
        conn.execute(
            "INSERT INTO activity(user_id, action, endpoint, details) VALUES(?,?,?,?)",
            (int(uid), action, request.path if request else "", str(details)[:1000])
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def auth_user_by_id(user_id):
    if not user_id:
        return None
    conn = auth_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone()
    conn.close()
    return row

def ensure_user_data(user_id, display_name=None):
    """Create a private default branch and claim legacy unowned rows only for the first user."""
    # Branches are now private to each authenticated account.
    branch = Branch.query.filter_by(user_id=user_id).order_by(Branch.id.asc()).first()
    if branch is None:
        legacy_branch = Branch.query.filter(Branch.user_id.is_(None)).order_by(Branch.id.asc()).first()
        if legacy_branch:
            legacy_branch.user_id = user_id
            branch = legacy_branch
            for model in (PantryItem, Receipt, ShoppingItem, WasteLog):
                model.query.filter(model.user_id.is_(None)).update(
                    {"user_id": user_id, "branch_id": branch.id}, synchronize_session=False
                )
            db.session.commit()
        else:
            branch = Branch(user_id=user_id, name="Home")
            db.session.add(branch)
            db.session.commit()
    session["branch_id"] = branch.id
    return branch

def current_user():
    return auth_user_by_id(session.get("user_id"))

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify(ok=False, error="Please log in first.", login_required=True), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def google_ready():
    return bool(OAuth and app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"])

if OAuth:
    oauth = OAuth(app)
    if google_ready():
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
else:
    oauth = None

@app.before_request
def require_login_and_log():
    if request.endpoint in {"static", "login", "register", "google_login", "google_callback", "logout"}:
        return None
    if request.path.startswith("/static/"):
        return None
    if not session.get("user_id"):
        if request.path.startswith("/api/"):
            return jsonify(ok=False, error="Please log in first.", login_required=True), 401
        return redirect(url_for("login", next=request.path))
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        log_activity(f"{request.method} {request.path}")
    return None

@app.context_processor
def auth_globals():
    return {"auth_user": current_user(), "google_login_enabled": google_ready()}

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        conn = auth_conn()
        row = conn.execute(
            "SELECT * FROM users WHERE lower(username)=lower(?) OR lower(email)=lower(?)",
            (identifier, identifier)
        ).fetchone()
        if row and row["password_hash"] and check_password_hash(row["password_hash"], password):
            now = datetime.utcnow().isoformat()
            conn.execute("UPDATE users SET last_login=? WHERE id=?", (now, row["id"]))
            conn.execute("INSERT INTO auth_events(user_id,event) VALUES(?,?)", (row["id"], "login"))
            conn.commit(); conn.close()
            session["user_id"] = row["id"]
            ensure_user_data(row["id"], row["display_name"])
            log_activity("LOGIN", "Password login", row["id"])
            return redirect(request.args.get("next") or url_for("dashboard"))
        conn.close()
        error = "Invalid username/email or password."
    return render_template("login.html", error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        username = re.sub(r"[^A-Za-z0-9_.-]", "", request.form.get("username", "").strip())[:50]
        email = request.form.get("email", "").strip().lower()[:160]
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(username) < 3:
            error = "Username must be at least 3 characters."
        elif "@" not in email:
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            conn = auth_conn()
            try:
                cur = conn.execute(
                    "INSERT INTO users(username,email,password_hash,display_name) VALUES(?,?,?,?)",
                    (username, email, generate_password_hash(password), username)
                )
                uid = cur.lastrowid
                conn.execute("INSERT INTO auth_events(user_id,event) VALUES(?,?)", (uid, "register"))
                conn.commit(); conn.close()
                session["user_id"] = uid
                ensure_user_data(uid, username)
                log_activity("REGISTER", "New account", uid)
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                conn.close()
                error = "That username or email is already registered."
    return render_template("register.html", error=error)

@app.get("/auth/google")
def google_login():
    if not google_ready():
        flash("Google Login is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.", "error")
        return redirect(url_for("login"))
    redirect_uri = url_for("google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.get("/auth/google/callback")
def google_callback():
    if not google_ready():
        return redirect(url_for("login"))
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = oauth.google.userinfo()
        sub = str(userinfo["sub"])
        email = (userinfo.get("email") or "").lower()
        name = userinfo.get("name") or email.split("@")[0] or "Google User"
        conn = auth_conn()
        row = conn.execute("SELECT * FROM users WHERE google_sub=? OR lower(email)=lower(?)", (sub, email)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET google_sub=?, display_name=?, last_login=? WHERE id=?",
                (sub, name, datetime.utcnow().isoformat(), row["id"])
            )
            uid = row["id"]
        else:
            base = re.sub(r"[^A-Za-z0-9_.-]", "", email.split("@")[0] or "googleuser")[:45] or "googleuser"
            username = base
            n = 2
            while conn.execute("SELECT 1 FROM users WHERE lower(username)=lower(?)", (username,)).fetchone():
                username = f"{base}{n}"; n += 1
            cur = conn.execute(
                "INSERT INTO users(username,email,password_hash,google_sub,display_name,last_login) VALUES(?,?,?,?,?,?)",
                (username, email, None, sub, name, datetime.utcnow().isoformat())
            )
            uid = cur.lastrowid
            conn.execute("INSERT INTO auth_events(user_id,event) VALUES(?,?)", (uid, "google_register"))
        conn.commit(); conn.close()
        session["user_id"] = uid
        ensure_user_data(uid, name)
        log_activity("LOGIN", "Google login", uid)
        return redirect(url_for("dashboard"))
    except Exception as exc:
        flash(f"Google Login failed: {exc}", "error")
        return redirect(url_for("login"))

@app.get("/logout")
def logout():
    uid = session.get("user_id")
    if uid:
        log_activity("LOGOUT", "User logged out", uid)
    session.clear()
    return redirect(url_for("login"))

@app.get("/activity")
@login_required
def activity():
    conn = activity_conn()
    rows = conn.execute(
        "SELECT * FROM activity WHERE user_id=? ORDER BY id DESC LIMIT 100",
        (session["user_id"],)
    ).fetchall()
    conn.close()
    return render_template("activity.html", activities=rows)

LOCATION_CHOICES = ["Pantry", "Fridge", "Cupboards", "Freezer", "Counter", "Other"]

DEFAULT_CATEGORIES = [
    ("Produce","🥦","#65B741"), ("Dairy","🥛","#5DADE2"), ("Meat","🍗","#E57373"),
    ("Bakery","🍞","#D4A373"), ("Beverages","🥤","#8E7CC3"), ("Snacks","🍿","#F2C14E"),
    ("Frozen","🧊","#6EC6CA"), ("Pantry","🥫","#A1887F"), ("Other","🛒","#78909C")
]

# One shared category engine is used by Receipt Scan, Grocery Snap and Manual Entry.
# AI can suggest a category, but these rules normalize/fallback to USEVA's canonical
# category list so all three input methods always store the same category values.
CATEGORY_KEYWORDS = {
    "Produce": [
        "apple", "banana", "orange", "mango", "grape", "grapes", "papaya", "guava",
        "watermelon", "melon", "pineapple", "pomegranate", "kiwi", "lemon", "lime",
        "tomato", "potato", "onion", "garlic", "ginger", "carrot", "beans", "bean",
        "peas", "spinach", "palak", "lettuce", "cabbage", "cauliflower", "broccoli",
        "cucumber", "capsicum", "pepper", "brinjal", "eggplant", "okra", "lady finger",
        "beetroot", "radish", "corn", "avocado", "fruit", "vegetable", "veggie"
    ],
    "Dairy": [
        "milk", "curd", "yogurt", "yoghurt", "dahi", "paneer", "cheese", "butter",
        "cream", "ghee", "lassi", "buttermilk", "ice cream", "icecream", "egg", "eggs"
    ],
    "Meat": [
        "chicken", "mutton", "lamb", "beef", "pork", "meat", "fish", "prawn", "prawns",
        "shrimp", "crab", "seafood", "sausage", "salami", "ham", "turkey"
    ],
    "Bakery": [
        "bread", "bun", "buns", "croissant", "cake", "cakes", "muffin", "muffins",
        "donut", "doughnut", "pastry", "rusk", "toast", "biscuit", "biscuits", "cookies",
        "cookie", "pav", "naan", "roti", "chapati", "paratha", "pizza base"
    ],
    "Beverages": [
        "water", "juice", "cola", "coke", "pepsi", "sprite", "fanta", "soda", "soft drink",
        "drink", "beverage", "coffee", "tea", "milkshake", "energy drink", "drink mix"
    ],
    "Snacks": [
        "potato chips", "chips", "crisps", "namkeen", "mixture", "popcorn", "chocolate", "candy", "toffee",
        "wafer", "wafers", "snack", "snacks", "nuts", "peanut", "peanuts", "trail mix"
    ],
    "Frozen": [
        "frozen", "frozen food", "frozen peas", "frozen corn", "frozen chicken", "ice pop",
        "fries", "french fries", "nuggets"
    ],
    "Pantry": [
        "rice", "atta", "flour", "maida", "sugar", "salt", "dal", "lentil", "lentils",
        "toor dal", "moong dal", "urad dal", "chana", "beans dry", "pasta", "noodles",
        "oil", "cooking oil", "olive oil", "masala", "spice", "spices", "turmeric",
        "chilli powder", "cumin", "cereal", "oats", "cornflakes", "ketchup", "sauce",
        "pickle", "jam", "honey", "peanut butter", "canned", "can", "tin", "dry fruit"
    ]
}

CATEGORY_ALIASES = {
    "fruit": "Produce", "fruits": "Produce", "vegetable": "Produce", "vegetables": "Produce",
    "veggies": "Produce", "dairy and eggs": "Dairy", "eggs": "Dairy",
    "drink": "Beverages", "drinks": "Beverages", "beverage": "Beverages",
    "frozen foods": "Frozen", "dry goods": "Pantry", "staples": "Pantry",
    "groceries": "Pantry", "other": "Other"
}

# Approximate storage guidance. These are deliberately suggestions, not manufacturer expiry dates.
# Sources reviewed: USDA FoodKeeper/FoodSafety.gov and FDA food-date-labeling guidance.
# FoodKeeper notes that storage times are useful guidelines, not hard-and-fast rules.
SHELF_LIFE_DAYS = {
    "milk": (2, 3, "Conservative USEVA reminder for refrigerated milk; the package date and storage instructions take priority."),
    "curd": (3, 7, "Refrigerated yogurt/curd: approximate quality window; follow the package date."),
    "yogurt": (3, 7, "Refrigerated yogurt: approximate quality window; follow the package date."),
    "paneer": (3, 5, "Fresh paneer is perishable; keep refrigerated and follow package instructions."),
    "cheese": (14, 28, "Varies widely by cheese type and packaging; use package date when available."),
    "butter": (14, 30, "Approximate refrigerated quality window; package date takes priority."),
    "eggs": (21, 35, "USDA guidance for raw shell eggs refrigerated: 3–5 weeks."),
    "egg": (21, 35, "USDA guidance for raw shell eggs refrigerated: 3–5 weeks."),
    "chicken": (1, 2, "USDA guidance for fresh chicken refrigerated: 1–2 days."),
    "fish": (1, 2, "USDA guidance for fresh fish refrigerated: 1–2 days."),
    "prawn": (1, 2, "Fresh seafood is highly perishable; use a 1–2 day refrigerated estimate."),
    "prawns": (1, 2, "Fresh seafood is highly perishable; use a 1–2 day refrigerated estimate."),
    "shrimp": (1, 2, "Fresh seafood is highly perishable; use a 1–2 day refrigerated estimate."),
    "mutton": (1, 2, "Fresh ground/retail meat can have a short refrigerated window; follow package instructions."),
    "meat": (1, 2, "Fresh meat has a short refrigerated window; follow package instructions."),
    "bread": (5, 7, "Approximate quality window; mold/spoilage and package guidance take priority."),
    "banana": (3, 7, "Approximate quality window at home; ripeness and storage conditions vary."),
    "apple": (21, 42, "Approximate quality window; refrigeration can extend freshness."),
    "tomato": (3, 7, "Approximate freshness window; ripeness varies."),
    "potato": (14, 30, "Approximate pantry quality window; keep cool, dark and dry."),
    "onion": (14, 30, "Approximate pantry quality window; keep cool, dry and ventilated."),
    "spinach": (3, 7, "Approximate refrigerated freshness window."),
    "lettuce": (5, 10, "Approximate refrigerated freshness window."),
    "carrot": (14, 28, "Approximate refrigerated freshness window."),
    "frozen": (30, 90, "Conservative reminder window for quality; frozen food can last longer when continuously frozen. Check package guidance."),
}

def approximate_expiry(item_name, purchase=None):
    """Return a suggested expiry/use-by date and explanation, or None when a reliable estimate is not appropriate."""
    purchase = purchase or date.today()
    text = str(item_name or '').lower()
    # Prefer longer/more-specific phrases first.
    matches = []
    for key, value in SHELF_LIFE_DAYS.items():
        if re.search(r"(?<![a-z])" + re.escape(key) + r"(?![a-z])", text):
            matches.append((len(key), value))
    if not matches:
        return None
    _, (low, high, note) = sorted(matches, reverse=True)[0]
    suggested_days = round((low + high) / 2)
    return {
        "date": purchase + timedelta(days=suggested_days),
        "min_date": purchase + timedelta(days=low),
        "max_date": purchase + timedelta(days=high),
        "low_days": low, "high_days": high, "note": note
    }

def normalize_item_key(name):
    text = re.sub(r"\b(?:brand|size|pack|pcs?|pieces?|x|qty|quantity)\b", " ", str(name or '').lower())
    return re.sub(r"[^a-z0-9]+", "", text)

def probable_receipt_item(name, store_name=None):
    text = re.sub(r"\s+", " ", str(name or '').strip())
    if not text or len(text) < 2:
        return False
    blocked = r"receipt|invoice|bill no|invoice no|gstin|gst no|subtotal|grand total|net total|amount payable|tax|cgst|sgst|discount|cash|change|balance|payment|tender|thank you|customer|address|phone|tel|www\.|upi|card|round off"
    if re.search(blocked, text, re.I):
        return False
    if store_name and normalize_item_key(text) == normalize_item_key(store_name):
        return False
    if len(re.findall(r"[A-Za-z]", text)) < 2:
        return False
    return True

def merge_pantry_item(existing, quantity, price=0, unit=None):
    """Merge quantity into an existing pantry lot."""
    before = float(existing.quantity or 0)
    existing.quantity = before + float(quantity or 0)
    if price and price > 0:
        existing.price = float(price)
    if unit and (not existing.unit or existing.unit == 'unit'):
        existing.unit = str(unit)[:30]
    return before, existing.quantity

def find_active_pantry_match(name, category_name=None, purchase_date=None, expiry_date=None):
    """Match only the same item lot (purchase + expiry), preserving different freshness dates."""
    key = normalize_item_key(name)
    if not key:
        return None
    items = scoped(PantryItem).filter_by(status='active').all()
    candidates = [i for i in items if normalize_item_key(i.name) == key]
    if category_name and len(candidates) > 1:
        same = [i for i in candidates if i.category and i.category.name.lower() == category_name.lower()]
        if same:
            candidates = same
    for item in candidates:
        if item.purchase_date == purchase_date and item.expiry_date == expiry_date:
            return item
    if expiry_date is None:
        for item in candidates:
            if item.purchase_date == purchase_date and item.expiry_date is None:
                return item
    return None

def receipt_signature(store_name, receipt_date, total, items):
    normalized_items = []
    for item in items:
        normalized_items.append({
            "name": normalize_item_key(item.get("name")),
            "quantity": round(float(item.get("quantity") or 1), 3),
            "unit_price": round(float(item.get("unit_price") or 0), 2),
        })
    payload = {
        "store": normalize_item_key(store_name),
        "date": receipt_date.isoformat(),
        "total": round(float(total or 0), 2),
        "items": sorted(normalized_items, key=lambda x: (x["name"], x["quantity"], x["unit_price"])),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def category_choices(include_custom=True):
    """Return canonical categories plus user-created categories."""
    canonical = [name for name, _, _ in DEFAULT_CATEGORIES]
    if not include_custom:
        return canonical
    try:
        db_names = [c.name for c in Category.query.order_by(Category.name).all()]
        return list(dict.fromkeys(canonical + db_names))
    except Exception:
        return canonical

def ensure_category(name):
    """Return an existing category or create a user-defined category."""
    clean = re.sub(r"\s+", " ", str(name or "").strip())
    if not clean:
        clean = "Other"
    existing = Category.query.filter(db.func.lower(Category.name) == clean.lower()).first()
    if existing:
        return existing
    # User-created categories deliberately use a neutral icon/color.
    category = Category(name=clean, icon="🛒", color="#78909C")
    db.session.add(category)
    db.session.flush()
    return category

def normalize_category(value=None, item_name="", allow_custom=False):
    """Normalize a category while preserving an explicitly chosen custom category."""
    raw = re.sub(r"\s+", " ", str(value or "").strip())
    canonical = {name.lower(): name for name, _, _ in DEFAULT_CATEGORIES}
    if raw.lower() in canonical:
        return canonical[raw.lower()]
    if raw.lower() in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[raw.lower()]
    if allow_custom and raw and raw.lower() not in {"auto-detect", "auto", "none"}:
        return raw[:80]
    return infer_category(item_name)

def infer_category(item_name="", ai_hint=None):
    """Automatically classify an item from its name, using an AI hint only as fallback."""
    name = str(item_name or "").strip().lower()
    matches = []
    for category, words in CATEGORY_KEYWORDS.items():
        for word in words:
            if re.search(r"(?<![a-z])" + re.escape(word.lower()) + r"(?![a-z])", name):
                matches.append((len(word), category))
    if matches:
        return sorted(matches, reverse=True)[0][1]
    raw = str(ai_hint or "").strip().lower()
    canonical = {name.lower(): name for name, _, _ in DEFAULT_CATEGORIES}
    if raw in canonical:
        return canonical[raw]
    if raw in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[raw]
    return "Other"

@event.listens_for(Session, "before_flush")
def assign_user_id_before_flush(session_obj, flush_context, instances):
    uid = session.get("user_id")
    if not uid:
        return
    for obj in list(session_obj.new):
        if isinstance(obj, (Branch, PantryItem, Receipt, ShoppingItem, WasteLog)) and getattr(obj, "user_id", None) is None:
            obj.user_id = uid

def seed():
    if Category.query.count() == 0:
        for name, icon, color in DEFAULT_CATEGORIES:
            db.session.add(Category(name=name, icon=icon, color=color))
        db.session.commit()


ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def save_uploaded_image(upload, prefix):
    if not upload or not upload.filename:
        return None
    ext = Path(upload.filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Please upload a PNG, JPG, JPEG or WEBP image.")
    filename = secure_filename(upload.filename)
    filename = f"{prefix}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{filename}"
    upload.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename

def clean_receipt_item_name(name, store_name=None):
    name = re.sub(r"\s+", " ", str(name or "")).strip(" .:-|\"")
    if len(name) < 2 or len(name) > 100:
        return ""
    if re.fullmatch(r"[\W_]+", name):
        return ""
    if not probable_receipt_item(name, store_name):
        return ""
    return name

def parse_receipt_text(text):
    """Conservative receipt parser used only as a fallback when AI is unavailable."""
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
    store = "Scanned Receipt"
    for line in lines[:10]:
        if not re.search(r"(receipt|invoice|bill|tax|gst|total|cash|change|subtotal)", line, re.I) and len(line) <= 70:
            letters = re.findall(r"[A-Za-z]", line)
            if len(letters) >= 4:
                store = line
                break

    total = 0.0
    total_patterns = [
        r"(?:grand\s*total|net\s*total|amount\s*payable|total\s*(?:amount|due)?|tot)\D{0,20}(?:₹|rs\.?|inr)?\s*([0-9]+(?:[.,][0-9]{1,2})?)\s*$",
        r"(?:₹|rs\.?|inr)\s*([0-9]+(?:[.,][0-9]{1,2})?)\s*$"
    ]
    for line in reversed(lines):
        for pat in total_patterns:
            m = re.search(pat, line, re.I)
            if m:
                try:
                    total = float(m.group(1).replace(",", ""))
                    break
                except ValueError:
                    pass
        if total:
            break

    stop_words = r"subtotal|grand total|net total|amount payable|tax|gst|cgst|sgst|discount|cash|change|receipt|invoice|thank|balance|round off|payment|tender"
    items = []
    seen = set()
    # Accept both `Product 2 120.00` and `Product 120.00` layouts.
    price_re = re.compile(r"(?:₹|rs\.?|inr)?\s*([0-9]+(?:[.,][0-9]{1,2})?)\s*$", re.I)
    for line in lines:
        if re.search(rf"(?:{stop_words})", line, re.I):
            continue
        m = price_re.search(line)
        if not m:
            continue
        price = float(m.group(1).replace(",", ""))
        left = line[:m.start()].strip(" .:-")
        if not left or len(left) > 100:
            continue
        qty = 1.0
        # Only treat a trailing standalone number as quantity when it is clearly separate.
        qm = re.search(r"(?:^|\s)(\d+(?:\.\d+)?)\s*(?:x|×)?$", left, re.I)
        if qm:
            possible_name = left[:qm.start()].strip(" .:-")
            if possible_name and re.search(r"[A-Za-z]", possible_name):
                qty = float(qm.group(1))
                left = possible_name
        name = clean_receipt_item_name(left, store)
        if not name:
            continue
        key = normalize_item_key(name)
        if key in {"subtotal", "total", "tax"} or not key:
            continue
        existing = next((x for x in items if normalize_item_key(x["name"]) == key), None)
        if existing:
            existing["quantity"] += qty
            existing["unit_price"] = price or existing["unit_price"]
        else:
            seen.add(key)
            items.append({"name": name, "quantity": qty, "unit_price": price, "category": infer_category(name)})
    return {"store_name": store, "total": total, "items": items, "raw_text": text}

def local_receipt_ocr(path):
    """Multi-pass local OCR fallback. It is deliberately conservative to avoid fake line items."""
    if Image is None:
        return None, "Pillow is not installed."
    if pytesseract is None:
        return None, "pytesseract is not installed."
    try:
        tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            return None, "Tesseract OCR was not found. Install Tesseract OCR or set the correct tesseract.exe path in app.py."

        image = Image.open(path).convert("RGB")
        max_width = 2200
        if image.width < 1400:
            ratio = 1400 / image.width
            image = image.resize((1400, int(image.height * ratio)))
        elif image.width > max_width:
            ratio = max_width / image.width
            image = image.resize((max_width, int(image.height * ratio)))

        variants = [image]
        try:
            gray = image.convert("L")
            variants.append(gray.point(lambda p: 255 if p > 175 else 0))
        except Exception:
            pass

        candidates = []
        for variant in variants:
            for psm in (6, 11):
                text = pytesseract.image_to_string(variant, config=f"--psm {psm}")
                if not text.strip():
                    continue
                parsed = parse_receipt_text(text)
                parsed["raw_text"] = text
                candidates.append(parsed)
        if not candidates:
            return None, "Tesseract could not read any text from this image."

        # Prefer the pass that found the most plausible line items, then a total.
        best = max(candidates, key=lambda x: (len(x.get("items") or []), 1 if x.get("total") else 0, len(x.get("raw_text", ""))))
        return best, None
    except Exception as exc:
        return None, f"OCR failed: {exc}"

def gemini_image_json(path, prompt):
    
    api_key = os.getenv("GEMINI_API_KEY")

    print("====================================")
    print("GEMINI DEBUG")
    print("API KEY:", "SET" if api_key else "NOT SET")
    print("IMAGE:", path)
    print("IMAGE EXISTS:", os.path.exists(path))
    print("====================================")

    if not api_key:
        return None, "GEMINI_API_KEY is not configured."
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return None, (
            "GEMINI_API_KEY is not configured. "
            "Check your .env file."
        )

    if requests is None:
        return None, "Python requests package is not installed."

    try:
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"

        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        },
                        {
                            "inline_data": {
                                "mime_type": mime,
                                "data": data
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }

        url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/gemini-3.6-flash:generateContent"
            )

        response = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=90
        )

        # IMPORTANT:
        # Show Google's actual error instead of hiding it.
        if response.status_code != 200:
            try:
                error_data = response.json()
                message = error_data.get("error", {}).get(
                    "message",
                    response.text
                )
            except Exception:
                message = response.text

            return None, (
                f"Gemini API error {response.status_code}: "
                f"{message}"
            )

        body = response.json()

        candidates = body.get("candidates") or []

        if not candidates:
            return None, "Gemini returned no candidates."

        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        if not parts:
            return None, "Gemini returned no response content."

        text = ""

        for part in parts:
            if part.get("text"):
                text += part["text"]

        if not text.strip():
            return None, "Gemini returned an empty response."

        # Remove accidental markdown fences
        text = text.strip()

        if text.startswith("```"):
            text = re.sub(
                r"^```(?:json)?\s*",
                "",
                text,
                flags=re.IGNORECASE
            )
            text = re.sub(
                r"\s*```$",
                "",
                text
            )

        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, (
                f"Gemini returned invalid JSON: {exc}. "
                f"Response: {text[:500]}"
            )

        return result, None

    except requests.exceptions.Timeout:
        return None, "Gemini request timed out."

    except requests.exceptions.ConnectionError:
        return None, (
            "Could not connect to Gemini. "
            "Check your internet connection."
        )

    except Exception as exc:
        return None, f"Gemini request failed: {exc}"

def add_receipt_items_to_pantry(receipt, selected=None):
    selected = list(selected if selected is not None else receipt.items)
    cats = {c.name.lower(): c for c in Category.query.all()}
    added = 0; merged = []
    for ri in selected:
        ri.category = normalize_category(ri.category, ri.name, allow_custom=True)
        category = cats.get(ri.category.lower()) or ensure_category(ri.category)
        purchase = ri.purchase_date or receipt.receipt_date or date.today()
        expiry = ri.expiry_date
        match = find_active_pantry_match(ri.name, ri.category, purchase, expiry)
        if match:
            before, after = merge_pantry_item(match, ri.quantity or 1, ri.unit_price or 0, ri.unit or "unit")
            merged.append({"name": match.name, "before": before, "added": ri.quantity or 1, "after": after, "expiry_date": match.expiry_date.isoformat() if match.expiry_date else ""})
        else:
            db.session.add(PantryItem(name=ri.name, quantity=ri.quantity or 1, unit=ri.unit or "unit", price=ri.unit_price or 0, purchase_date=purchase, expiry_date=expiry, location=ri.location or "Pantry", notes=ri.notes or "", category=category, status="active", branch_id=current_branch_id()))
            added += 1
    db.session.commit()
    return added, merged

def get_current_branch():
    uid = session.get("user_id")
    if not uid:
        return None
    branch_id = session.get("branch_id")
    branch = Branch.query.filter_by(id=branch_id, user_id=uid).first() if branch_id else None
    if branch is None:
        branch = Branch.query.filter_by(user_id=uid).order_by(Branch.id.asc()).first()
        if branch:
            session["branch_id"] = branch.id
    return branch

def current_branch_id():
    branch = get_current_branch()
    return branch.id if branch else None

def scoped(model):
    """Return rows belonging to the authenticated user and active branch."""
    bid = current_branch_id()
    uid = session.get("user_id")
    if bid is None or uid is None:
        return model.query.filter(db.literal(False))
    return model.query.filter(model.user_id == uid, model.branch_id == bid)

@app.context_processor
def globals():
    branch = get_current_branch()
    branches = Branch.query.filter_by(user_id=session.get("user_id")).order_by(Branch.name.asc()).all() if session.get("user_id") else []
    return {"today": date.today(), "current_branch": branch, "branches": branches, "locations": LOCATION_CHOICES}

@app.route("/")
def dashboard():
    items = scoped(PantryItem).filter_by(status="active").order_by(PantryItem.expiry_date.asc()).all()
    expiry_soon = [i for i in items if i.expiry_date and 0 <= (i.expiry_date - date.today()).days <= 7]
    expired = [i for i in items if i.expiry_date and i.expiry_date < date.today()]
    total_value = sum((i.price or 0) * (i.quantity or 1) for i in items)
    month_start = date.today().replace(day=1)
    receipts = scoped(Receipt).filter(Receipt.receipt_date >= month_start).all()
    monthly_spend = sum(r.total or 0 for r in receipts)
    shopping_count = scoped(ShoppingItem).filter_by(checked=False).count()
    category_totals = {}
    for i in items:
        key = i.category.name if i.category else "Other"
        category_totals[key] = category_totals.get(key, 0) + (i.price or 0) * (i.quantity or 1)
    return render_template("dashboard.html",
        items=items, expiry_soon=expiry_soon, expired=expired,
        total_value=total_value, monthly_spend=monthly_spend,
        shopping_count=shopping_count, category_totals=category_totals)

@app.route("/pantry")
def pantry():
    q = request.args.get("q","").strip()
    category = request.args.get("category","")
    category_q = request.args.get("category_q","").strip()
    query = scoped(PantryItem).filter_by(status="active")
    if q: query = query.filter(PantryItem.name.ilike(f"%{q}%"))
    if category:
        query = query.join(Category).filter(Category.name == category)
    elif category_q:
        query = query.join(Category).filter(Category.name.ilike(f"%{category_q}%"))
    items = query.order_by(PantryItem.expiry_date.asc(), PantryItem.name.asc()).all()
    name_counts = {}
    for item in items:
        key = normalize_item_key(item.name)
        name_counts[key] = name_counts.get(key, 0) + 1
    lot_counts = {item.id: name_counts.get(normalize_item_key(item.name), 1) for item in items}
    return render_template("pantry.html", items=items, categories=Category.query.order_by(Category.name).all(), selected=category, category_q=category_q, q=q, lot_counts=lot_counts)

@app.route("/expiry")
def expiry():
    items = scoped(PantryItem).filter_by(status="active").all()
    expired = [i for i in items if i.expiry_date and i.expiry_date < date.today()]
    today_items = [i for i in items if i.expiry_date == date.today()]
    soon = [i for i in items if i.expiry_date and 0 < (i.expiry_date-date.today()).days <= 7]
    later = [i for i in items if i.expiry_date and 7 < (i.expiry_date-date.today()).days <= 30]
    return render_template("expiry.html", expired=expired, today_items=today_items, soon=soon, later=later)

@app.route("/shopping", methods=["GET","POST"])
def shopping():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if name:
            db.session.add(ShoppingItem(
                name=name, quantity=float(request.form.get("quantity") or 1),
                unit=request.form.get("unit") or "unit",
                priority=request.form.get("priority") or "normal", branch_id=current_branch_id()
            ))
            db.session.commit()
        return redirect(url_for("shopping"))
    items = scoped(ShoppingItem).order_by(ShoppingItem.checked.asc(), ShoppingItem.priority.desc(), ShoppingItem.created_at.desc()).all()
    return render_template("shopping.html", items=items)

@app.get("/shopping/export/txt")
def export_shopping_txt():
    items = scoped(ShoppingItem).filter_by(checked=False).order_by(ShoppingItem.priority.desc(), ShoppingItem.name.asc()).all()
    lines = ["USEVA 2.0 - SHOPPING LIST", "", f"Generated: {date.today().strftime('%d %b %Y')}", ""]
    lines.extend([f"- {item.name} — {item.quantity:g} {item.unit}" for item in items] or ["No unchecked items to buy."])
    return send_file(BytesIO(("\n".join(lines)+"\n").encode("utf-8")), mimetype="text/plain; charset=utf-8", as_attachment=True, download_name="useva_shopping_list.txt")

@app.get("/shopping/export/pdf")
def export_shopping_pdf():
    items = scoped(ShoppingItem).filter_by(checked=False).order_by(ShoppingItem.priority.desc(), ShoppingItem.name.asc()).all()
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        return jsonify(ok=False, error="PDF export needs reportlab. Run: pip install reportlab"), 500
    buffer=BytesIO(); pdf=canvas.Canvas(buffer,pagesize=A4); width,height=A4; y=height-55
    pdf.setFont("Helvetica-Bold",18); pdf.drawString(50,y,"USEVA 2.0 - Shopping List"); y-=24
    pdf.setFont("Helvetica",10); pdf.drawString(50,y,f"Unchecked items · {date.today().strftime('%d %b %Y')}"); y-=30
    if items:
        for i,item in enumerate(items,1):
            if y<55: pdf.showPage(); y=height-55; pdf.setFont("Helvetica",10)
            pdf.drawString(55,y,f"{i}. {item.name} — {item.quantity:g} {item.unit}")
            if item.priority=="high": pdf.drawRightString(width-55,y,"HIGH PRIORITY")
            y-=20
    else: pdf.drawString(55,y,"No unchecked items to buy.")
    pdf.save(); buffer.seek(0)
    return send_file(buffer,mimetype="application/pdf",as_attachment=True,download_name="useva_shopping_list.pdf")

@app.post("/shopping/<int:item_id>/toggle")
def toggle_shopping(item_id):
    item = scoped(ShoppingItem).filter_by(id=item_id).first_or_404()
    item.checked = not item.checked
    db.session.commit()
    return jsonify(ok=True, checked=item.checked)

@app.post("/shopping/<int:item_id>/delete")
def delete_shopping(item_id):
    item = scoped(ShoppingItem).filter_by(id=item_id).first_or_404()
    db.session.delete(item); db.session.commit()
    return jsonify(ok=True)

@app.route("/receipts", methods=["GET","POST"])
def receipts():
    if request.method == "POST":
        store = request.form.get("store_name") or "Manual Entry"
        total = float(request.form.get("total") or 0)
        receipt_date = datetime.strptime(request.form.get("receipt_date"), "%Y-%m-%d").date() if request.form.get("receipt_date") else date.today()
        r = Receipt(store_name=store, total=total, receipt_date=receipt_date, source="manual", branch_id=current_branch_id())
        db.session.add(r); db.session.commit()
        flash("Receipt added successfully.", "success")
        return redirect(url_for("receipts"))
    return render_template("receipts.html", receipts=scoped(Receipt).order_by(Receipt.receipt_date.desc()).all(), categories=category_choices())

@app.get("/api/categories")
def api_categories():
    return jsonify(ok=True, categories=category_choices())

@app.post("/api/suggest-category")
def suggest_category():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    suggested = normalize_category(None, name)
    return jsonify(ok=True, category=suggested, categories=category_choices())

@app.get("/api/receipt/<int:receipt_id>")
def receipt_details(receipt_id):
    receipt=scoped(Receipt).filter_by(id=receipt_id).first_or_404()
    return jsonify(ok=True,receipt={"id":receipt.id,"store_name":receipt.store_name,"receipt_date":receipt.receipt_date.isoformat() if receipt.receipt_date else "","total":receipt.total or 0,"source":receipt.source or "manual","image":url_for("static",filename=f"uploads/{receipt.image}") if receipt.image else "","items":[{"name":x.name,"quantity":x.quantity or 1,"unit":x.unit or "unit","unit_price":x.unit_price or 0,"category":x.category or "Other","purchase_date":x.purchase_date.isoformat() if x.purchase_date else "","expiry_date":x.expiry_date.isoformat() if x.expiry_date else ""} for x in receipt.items]})

@app.post("/api/estimate-expiry")
def estimate_expiry():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    raw_purchase = str(data.get("purchase_date") or "").strip()
    try:
        purchase = datetime.strptime(raw_purchase, "%Y-%m-%d").date() if raw_purchase else date.today()
    except ValueError:
        purchase = date.today()
    estimate = approximate_expiry(name, purchase)
    if not estimate:
        return jsonify(ok=True, available=False, message="No reliable generic estimate. Check the package/manufacturer date.")
    return jsonify(ok=True, available=True, expiry_date=estimate["date"].isoformat(), min_date=estimate["min_date"].isoformat(), max_date=estimate["max_date"].isoformat(), low_days=estimate["low_days"], high_days=estimate["high_days"], note=estimate["note"], source="USDA FoodKeeper / FoodSafety.gov guidance")

@app.post("/api/receipt-item/<int:item_id>")
def update_receipt_item(item_id):
    item = ReceiptItem.query.join(Receipt).filter(Receipt.user_id == session["user_id"], Receipt.branch_id == current_branch_id(), ReceiptItem.id == item_id).first_or_404()
    data = request.get_json(silent=True) or request.form
    name = clean_receipt_item_name(data.get("name") or item.name)
    if not name:
        return jsonify(ok=False, error="Item name is required and must be a real product name."), 400
    try:
        item.name = name
        item.quantity = float(data.get("quantity") if data.get("quantity") is not None else item.quantity or 1)
        item.unit_price = float(data.get("unit_price") if data.get("unit_price") is not None else item.unit_price or 0)
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Quantity and price must be valid numbers."), 400
    if item.quantity <= 0:
        return jsonify(ok=False, error="Quantity must be greater than 0."), 400
    if item.unit_price < 0:
        return jsonify(ok=False, error="Price cannot be negative."), 400
    item.unit = str(data.get("unit") or item.unit or "unit").strip()[:30]
    custom_category = str(data.get("custom_category") or "").strip()
    requested_category = custom_category if custom_category else data.get("category")
    item.category = normalize_category(requested_category, item.name, allow_custom=bool(custom_category))
    raw_purchase = str(data.get("purchase_date") or "").strip()
    raw_expiry = str(data.get("expiry_date") or "").strip()
    try:
        item.purchase_date = datetime.strptime(raw_purchase, "%Y-%m-%d").date() if raw_purchase else (item.purchase_date or item.receipt.receipt_date or date.today())
        item.expiry_date = datetime.strptime(raw_expiry, "%Y-%m-%d").date() if raw_expiry else None
    except ValueError:
        return jsonify(ok=False, error="Invalid purchase or expiry date."), 400
    item.location = str(data.get("location") or item.location or "Pantry").strip()[:80]
    if item.location not in LOCATION_CHOICES:
        item.location = "Other"
    item.notes = str(data.get("notes") or "").strip()
    db.session.commit()
    return jsonify(ok=True, item={"id": item.id, "name": item.name, "quantity": item.quantity, "unit": item.unit, "unit_price": item.unit_price, "category": item.category, "custom_category": custom_category, "purchase_date": item.purchase_date.isoformat() if item.purchase_date else "", "expiry_date": item.expiry_date.isoformat() if item.expiry_date else "", "location": item.location, "notes": item.notes})

@app.post("/api/receipt/<int:receipt_id>/add-to-pantry")
def receipt_to_pantry_selected(receipt_id):
    receipt = scoped(Receipt).filter_by(id=receipt_id).first_or_404()
    data = request.get_json(silent=True) or {}
    selected_ids = data.get("item_ids")
    if selected_ids is None:
        selected = receipt.items
    else:
        try:
            wanted = {int(x) for x in selected_ids}
        except (TypeError, ValueError):
            return jsonify(ok=False, error="Invalid receipt item selection."), 400
        selected = [x for x in receipt.items if x.id in wanted]
    added, merged = add_receipt_items_to_pantry(receipt, selected)
    return jsonify(ok=True, added=added, merged=merged, message=f"{added} new item(s) added and {len(merged)} duplicate(s) merged.")

@app.post("/api/scan-receipt")
def scan_receipt():
    upload=request.files.get("image")
    if not upload or not upload.filename: return jsonify(ok=False,error="Choose a receipt image first."),400
    force_duplicate=str(request.form.get("allow_duplicate") or "0")=="1"
    try:
        filename=save_uploaded_image(upload,"receipt"); path=os.path.join(app.config["UPLOAD_FOLDER"],filename); image_hash=file_sha256(path)
    except ValueError as exc: return jsonify(ok=False,error=str(exc)),400
    ai_prompt="""You are a receipt OCR engine. Read ONLY information that is visibly printed on this receipt image. Return ONLY valid JSON in this exact shape:
{"store_name":"string or empty","receipt_date":"YYYY-MM-DD or null","total":0,"items":[{"name":"exact printed product name","quantity":1,"unit_price":0,"category":"Produce|Dairy|Meat|Bakery|Beverages|Snacks|Frozen|Pantry|Other"}]}
Rules:
1. List every visible purchased line item, in the same order as printed.
2. Preserve the product/brand name; do not rename, summarize, or invent products.
3. Read the price belonging to that exact line. Never use subtotal, tax, discount, payment, or total as an item price.
4. If a quantity is visibly printed, use it; otherwise use 1. Do not guess quantities.
5. If a value is unreadable, use 0 for price and 1 for quantity rather than inventing it.
6. Ignore headers, GSTIN, subtotal, CGST, SGST, discounts, payment/tender, change and footer text.
7. The total must be the final payable total printed on the receipt, not subtotal or tax.
8. Category is only a suggestion; classify from the product name.
9. Do not create an item from random OCR-like fragments."""
    ai_result,ai_error=gemini_image_json(path,ai_prompt)
    result,error=(ai_result,None) if ai_result and isinstance(ai_result.get("items"),list) else local_receipt_ocr(path)
    if result is None:
        return jsonify(ok=False,error=error or "Could not read this receipt. Try a clearer photo or configure GEMINI_API_KEY.",image=url_for("static",filename=f"uploads/{filename}")),422
    receipt_date=date.today(); raw_date=result.get("receipt_date")
    if raw_date:
        try: receipt_date=datetime.strptime(str(raw_date),"%Y-%m-%d").date()
        except ValueError: pass
    store_name=result.get("store_name") or "Scanned Receipt"; total=float(result.get("total") or 0)
    consolidated={}
    for item in result.get("items") or []:
        name=clean_receipt_item_name(item.get("name"),store_name)
        if not name: continue
        try: quantity=float(item.get("quantity") or 1); unit_price=float(item.get("unit_price") or 0)
        except (TypeError,ValueError): quantity,unit_price=1,0
        if quantity<=0: quantity=1
        if unit_price<0: unit_price=0
        key=normalize_item_key(name)
        if not key: continue
        if key in consolidated:
            consolidated[key]["quantity"]+=quantity
            if unit_price>0: consolidated[key]["unit_price"]=unit_price
        else: consolidated[key]={"name":name,"quantity":quantity,"unit_price":unit_price,"category":infer_category(name,item.get("category"))}
    signature=receipt_signature(store_name,receipt_date,total,list(consolidated.values()))
    duplicate=scoped(Receipt).filter((Receipt.image_hash==image_hash)|(Receipt.receipt_signature==signature)).order_by(Receipt.created_at.desc()).first()
    if duplicate and not force_duplicate:
        try: os.remove(path)
        except OSError: pass
        return jsonify(ok=False,duplicate=True,message="This receipt appears to have already been uploaded.",existing={"id":duplicate.id,"store_name":duplicate.store_name,"receipt_date":duplicate.receipt_date.isoformat() if duplicate.receipt_date else "","total":duplicate.total or 0}),409
    receipt=Receipt(store_name=store_name,total=total,receipt_date=receipt_date,image=filename,image_hash=image_hash,receipt_signature=signature,source="scan",branch_id=current_branch_id())
    db.session.add(receipt); db.session.flush()
    for data in consolidated.values():
        estimate=approximate_expiry(data["name"],receipt_date)
        db.session.add(ReceiptItem(receipt_id=receipt.id,name=data["name"],quantity=data["quantity"],unit="unit",unit_price=data["unit_price"],category=data["category"],purchase_date=receipt_date,expiry_date=(estimate["date"] if estimate else None),location="Pantry",notes=""))
    db.session.commit()
    return jsonify(ok=True,receipt_id=receipt.id,store_name=receipt.store_name,total=receipt.total,item_count=len(receipt.items),items=[{"id":x.id,"name":x.name,"quantity":x.quantity,"unit":x.unit or "unit","unit_price":x.unit_price,"category":x.category,"purchase_date":x.purchase_date.isoformat() if x.purchase_date else receipt_date.isoformat(),"expiry_date":x.expiry_date.isoformat() if x.expiry_date else "","location":x.location or "Pantry","notes":x.notes or ""} for x in receipt.items],image=url_for("static",filename=f"uploads/{filename}"))

@app.route("/grocery-snap")
def grocery_snap_page():
    return render_template("grocery_snap.html", categories=category_choices())

@app.post("/api/grocery-snap")
def grocery_snap():
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify(ok=False, error="Choose a grocery photo first."), 400
    try:
        filename = save_uploaded_image(upload, "grocery")
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400

    prompt = """Identify visible grocery/food products in this photo. Return ONLY JSON:
{"items":[{"name":"common grocery name","quantity":1,"unit":"unit","category":"Produce|Dairy|Meat|Bakery|Beverages|Snacks|Frozen|Pantry|Other","confidence":0.0}]}
Only include items you can actually see. Do not infer hidden items. Quantity should be the visible count when clear, otherwise 1."""
    result, error = gemini_image_json(path, prompt)

    print("====================================")
    print("GEMINI RESULT:", result)
    print("GEMINI ERROR:", error)
    print("====================================")

    if not result:
        return jsonify(ok=False, error="Grocery Snap needs GEMINI_API_KEY to identify products from photos.",
                       image=url_for("static", filename=f"uploads/{filename}")), 422

    items = []
    for item in result.get("items") or []:
        name = str(item.get("name") or "").strip()
        if name:
            purchase = date.today()
            estimate = approximate_expiry(name, purchase)
            items.append({
                "name": name, "quantity": float(item.get("quantity") or 1),
                "unit": item.get("unit") or "unit",
                "category": infer_category(name, item.get("category")),
                "purchase_date": purchase.isoformat(),
                "expiry_date": estimate["date"].isoformat() if estimate else "",
                "confidence": round(float(item.get("confidence") or 0), 2)
            })
    return jsonify(ok=True, items=items, image=url_for("static", filename=f"uploads/{filename}"))

@app.post("/api/grocery-snap/add")
def grocery_snap_add():
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    added = 0
    merged = []
    for x in items:
        name = str(x.get("name") or "").strip()
        if not name: continue
        custom_category = str(x.get("custom_category") or "").strip()
        requested_category = custom_category if custom_category else x.get("category")
        category_name = normalize_category(requested_category, name, allow_custom=bool(custom_category))
        qty = float(x.get("quantity") or 1)
        unit = str(x.get("unit") or "unit").strip()[:30]
        purchase = datetime.strptime(x["purchase_date"], "%Y-%m-%d").date() if x.get("purchase_date") else date.today()
        expiry = datetime.strptime(x["expiry_date"], "%Y-%m-%d").date() if x.get("expiry_date") else None
        match = find_active_pantry_match(name, category_name, purchase, expiry)
        if match:
            before, after = merge_pantry_item(match, qty, 0, unit)
            merged.append({"name": match.name, "before": before, "added": qty, "after": after})
        else:
            db.session.add(PantryItem(
                name=name, quantity=qty, unit=unit, price=float(x.get("price") or 0),
                purchase_date=purchase, expiry_date=expiry,
                location=(x.get("location") if x.get("location") in LOCATION_CHOICES else "Pantry"), notes=x.get("notes") or "",
                category=ensure_category(category_name), status="active", branch_id=current_branch_id()
            ))
            added += 1
    db.session.commit()
    return jsonify(ok=True, added=added, merged=merged)

@app.post("/add-item")
def add_item():
    f = request.form
    custom_category = str(f.get("custom_category") or "").strip()
    requested_category = custom_category if custom_category else f.get("category")
    category_name = normalize_category(requested_category, f.get("name"), allow_custom=bool(custom_category))
    category = ensure_category(category_name)
    purchase = datetime.strptime(f["purchase_date"], "%Y-%m-%d").date() if f.get("purchase_date") else date.today()
    expiry = datetime.strptime(f["expiry_date"], "%Y-%m-%d").date() if f.get("expiry_date") else None
    expiry_suggestion = approximate_expiry(f.get("name"), purchase)
    if expiry is None and expiry_suggestion:
        expiry = expiry_suggestion["date"]
    name = str(f.get("name") or "").strip()
    qty = float(f.get("quantity") or 1)
    match = find_active_pantry_match(name, category_name, purchase, expiry)
    if match:
        before, after = merge_pantry_item(match, qty, float(f.get("price") or 0), f.get("unit") or "unit")
        db.session.commit()
        flash(f"{name} already existed ({before:g}). Added {qty:g}; new quantity is {after:g}.", "warning")
        return redirect(request.referrer or url_for("pantry"))
    item = PantryItem(
        name=name, quantity=qty, unit=f.get("unit") or "unit",
        price=float(f.get("price") or 0), purchase_date=purchase, expiry_date=expiry,
        location=(f.get("location") if f.get("location") in LOCATION_CHOICES else "Pantry"), notes=f.get("notes") or "", category=category, branch_id=current_branch_id()
    )
    upload = request.files.get("image")
    if upload and upload.filename:
        filename = secure_filename(upload.filename)
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
        upload.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        item.image = filename
    db.session.add(item); db.session.commit()
    flash(f"{item.name} added to your pantry.", "success")
    return redirect(request.referrer or url_for("pantry"))

@app.post("/api/item/<int:item_id>")
def update_pantry_item(item_id):
    item = scoped(PantryItem).filter_by(id=item_id).first_or_404()
    data = request.get_json(silent=True) or {}
    name = clean_receipt_item_name(data.get("name") or item.name)
    if not name:
        return jsonify(ok=False, error="Item name cannot be empty."), 400
    try:
        item.name = name
        item.quantity = float(data.get("quantity") if data.get("quantity") is not None else item.quantity or 1)
        item.unit = str(data.get("unit") or item.unit or "unit").strip()[:30]
        item.price = float(data.get("price") if data.get("price") is not None else item.price or 0)
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Quantity and price must be valid numbers."), 400
    for field in ("location", "notes"):
        if field in data:
            setattr(item, field, str(data.get(field) or "").strip())
    for field in ("purchase_date", "expiry_date"):
        if field in data:
            raw = data.get(field)
            if raw:
                try:
                    setattr(item, field, datetime.strptime(str(raw), "%Y-%m-%d").date())
                except ValueError:
                    return jsonify(ok=False, error=f"Invalid {field.replace('_',' ')}."), 400
            else:
                setattr(item, field, None)
    custom_category = str(data.get("custom_category") or "").strip()
    requested_category = custom_category if custom_category else data.get("category")
    category_name = normalize_category(requested_category, item.name, allow_custom=bool(custom_category))
    item.category = ensure_category(category_name)
    db.session.commit()
    return jsonify(ok=True, item={"id": item.id, "name": item.name, "quantity": item.quantity, "unit": item.unit, "price": item.price, "purchase_date": item.purchase_date.isoformat() if item.purchase_date else "", "expiry_date": item.expiry_date.isoformat() if item.expiry_date else "", "location": item.location, "notes": item.notes, "category": item.category.name})

@app.post("/item/<int:item_id>/consume")
def consume(item_id):
    item=scoped(PantryItem).filter_by(id=item_id).first_or_404(); data=request.get_json(silent=True) or {}
    try: quantity=float(data.get("quantity"))
    except (TypeError,ValueError): return jsonify(ok=False,error="Enter a valid quantity to consumed."),400
    available=float(item.quantity or 0)
    if quantity<=0 or quantity>available: return jsonify(ok=False,error=f"Quantity to consumed must be between 0 and {available:g} {item.unit}."),400
    item.quantity=available-quantity
    if item.quantity<=0.000001: item.quantity=0; item.status="consumed"
    db.session.commit(); return jsonify(ok=True,remaining=item.quantity,status=item.status)

@app.post("/item/<int:item_id>/waste")
def waste(item_id):
    item=scoped(PantryItem).filter_by(id=item_id).first_or_404(); data=request.get_json(silent=True) or {}
    try: quantity=float(data.get("quantity"))
    except (TypeError,ValueError): return jsonify(ok=False,error="Enter a valid quantity wasted."),400
    available=float(item.quantity or 0)
    if quantity<=0 or quantity>available: return jsonify(ok=False,error=f"Quantity wasted must be between 0 and {available:g} {item.unit}."),400
    db.session.add(WasteLog(item_name=item.name,quantity=quantity,reason="User marked waste",estimated_value=(item.price or 0)*quantity, branch_id=current_branch_id()))
    item.quantity=available-quantity
    if item.quantity<=0.000001: item.quantity=0; item.status="wasted"
    db.session.commit(); return jsonify(ok=True,remaining=item.quantity,status=item.status)

@app.route("/insights")
def insights():
    receipts = scoped(Receipt).order_by(Receipt.receipt_date.asc()).all()
    waste = scoped(WasteLog).order_by(WasteLog.logged_at.desc()).all()
    by_store = {}
    for r in receipts: by_store[r.store_name] = by_store.get(r.store_name, 0) + (r.total or 0)
    return render_template("insights.html", receipts=receipts, waste=waste, by_store=by_store)

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", branches=Branch.query.filter_by(user_id=session["user_id"]).order_by(Branch.name.asc()).all(), current_branch=get_current_branch())

@app.post("/api/branch/switch")
@login_required
def switch_branch():
    data = request.get_json(silent=True) or {}
    try:
        branch_id = int(data.get("branch_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Choose a valid branch."), 400
    branch = Branch.query.filter_by(id=branch_id, user_id=session["user_id"]).first()
    if not branch:
        return jsonify(ok=False, error="Branch not found for this account."), 404
    session["branch_id"] = branch.id
    return jsonify(ok=True, branch={"id": branch.id, "name": branch.name})

@app.get("/api/branches")
@login_required
def list_branches():
    branch = get_current_branch()
    branches = Branch.query.filter_by(user_id=session["user_id"]).order_by(Branch.name.asc()).all()
    return jsonify(ok=True, current_branch_id=(branch.id if branch else None), branches=[{"id": b.id, "name": b.name} for b in branches])

@app.post("/api/branch/create")
@login_required
def create_branch():
    data = request.get_json(silent=True) or {}
    name = re.sub(r"\s+", " ", str(data.get("name") or "").strip())[:100]
    if len(name) < 2:
        return jsonify(ok=False, error="Enter a branch name."), 400
    if Branch.query.filter(Branch.user_id == session["user_id"], db.func.lower(Branch.name) == name.lower()).first():
        return jsonify(ok=False, error="That branch already exists in your account."), 409
    branch = Branch(user_id=session["user_id"], name=name)
    db.session.add(branch); db.session.commit()
    session["branch_id"] = branch.id
    return jsonify(ok=True, branch={"id": branch.id, "name": branch.name})

def clear_branch_data(branch_id):
    receipt_ids = [r.id for r in Receipt.query.filter_by(branch_id=branch_id).all()]
    if receipt_ids:
        ReceiptItem.query.filter(ReceiptItem.receipt_id.in_(receipt_ids)).delete(synchronize_session=False)
    Receipt.query.filter_by(branch_id=branch_id).delete(synchronize_session=False)
    PantryItem.query.filter_by(branch_id=branch_id).delete(synchronize_session=False)
    ShoppingItem.query.filter_by(branch_id=branch_id).delete(synchronize_session=False)
    WasteLog.query.filter_by(branch_id=branch_id).delete(synchronize_session=False)

@app.post("/api/clear/current")
def clear_current_branch():
    branch = get_current_branch()
    if not branch:
        return jsonify(ok=False, error="No active branch."), 400
    clear_branch_data(branch.id)
    db.session.commit()
    return jsonify(ok=True, message=f"All inventory data in {branch.name} was cleared.")

@app.post("/api/clear/all")
def clear_all_inventory():
    uid = session["user_id"]
    receipt_ids = [r.id for r in Receipt.query.filter_by(user_id=uid).all()]
    if receipt_ids:
        ReceiptItem.query.filter(ReceiptItem.receipt_id.in_(receipt_ids)).delete(synchronize_session=False)
    Receipt.query.filter_by(user_id=uid).delete(synchronize_session=False)
    PantryItem.query.filter_by(user_id=uid).delete(synchronize_session=False)
    ShoppingItem.query.filter_by(user_id=uid).delete(synchronize_session=False)
    WasteLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
    db.session.commit()
    return jsonify(ok=True, message="All your inventory data across every branch was cleared.")

@app.post("/api/seed-demo")
def seed_demo():
    cats = {c.name:c for c in Category.query.all()}
    if scoped(PantryItem).count() == 0:
        demo = [
            ("Milk",1,"L",62,"Dairy",2),("Tomatoes",6,"pcs",90,"Produce",3),
            ("Spinach",1,"bunch",45,"Produce",4),("Bread",1,"loaf",55,"Bakery",6),
            ("Chicken Breast",500,"g",280,"Meat",8),("Yogurt",4,"cups",120,"Dairy",5)
        ]
        for name, qty, unit, price, cat, days in demo:
            db.session.add(PantryItem(name=name,quantity=qty,unit=unit,price=price,
                purchase_date=date.today(),expiry_date=date.today()+timedelta(days=days),
                location="Fridge",category=cats.get(cat), branch_id=current_branch_id()))
        db.session.add_all([
            Receipt(store_name="FreshMart", receipt_date=date.today(), total=652, source="manual", branch_id=current_branch_id()),
            Receipt(store_name="Daily Needs", receipt_date=date.today()-timedelta(days=5), total=488, source="manual", branch_id=current_branch_id())
        ])
        db.session.commit()
    return jsonify(ok=True)

def migrate_receipt_item_columns():
    """Add new review fields to older SQLite databases without deleting user data."""
    inspector = sa_inspect(db.engine)
    tables = inspector.get_table_names()
    if "receipt_item" not in tables:
        return
    columns = {c["name"] for c in inspector.get_columns("receipt_item")}
    additions = {
        "unit": "VARCHAR(30)",
        "purchase_date": "DATE",
        "expiry_date": "DATE",
        "location": "VARCHAR(80)",
        "notes": "TEXT"
    }
    for name, sql_type in additions.items():
        if name not in columns:
            db.session.execute(sa_text(f"ALTER TABLE receipt_item ADD COLUMN {name} {sql_type}"))
    db.session.commit()

def migrate_receipt_columns():
    inspector=sa_inspect(db.engine); tables=inspector.get_table_names()
    if "receipt" not in tables: return
    columns={c["name"] for c in inspector.get_columns("receipt")}
    for name,sql_type in {"image_hash":"VARCHAR(64)","receipt_signature":"VARCHAR(64)"}.items():
        if name not in columns: db.session.execute(sa_text(f"ALTER TABLE receipt ADD COLUMN {name} {sql_type}"))
    db.session.commit()
    # Backfill signatures/hashes for existing scanned receipts when possible.
    for receipt in Receipt.query.filter(Receipt.source == "scan").all():
        changed=False
        if receipt.image and not receipt.image_hash:
            image_path=Path(app.config["UPLOAD_FOLDER"])/receipt.image
            if image_path.exists():
                receipt.image_hash=file_sha256(str(image_path)); changed=True
        if not receipt.receipt_signature:
            items=[{"name":x.name,"quantity":x.quantity,"unit_price":x.unit_price} for x in receipt.items]
            receipt.receipt_signature=receipt_signature(receipt.store_name, receipt.receipt_date or date.today(), receipt.total or 0, items); changed=True
        if changed: db.session.add(receipt)
    db.session.commit()



def migrate_user_columns():
    inspector = sa_inspect(db.engine)
    tables = inspector.get_table_names()
    # User ownership columns are nullable so existing databases remain readable.
    for table in ("branch", "pantry_item", "receipt", "shopping_item", "waste_log"):
        if table not in tables:
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if "user_id" not in columns:
            db.session.execute(sa_text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))
    db.session.commit()

def migrate_branch_name_constraint():
    """Remove the old global UNIQUE(name) constraint so different users can
    have branches with the same name (e.g. everyone can have a Home branch)."""
    inspector = sa_inspect(db.engine)
    if "branch" not in inspector.get_table_names():
        return
    # Fresh USEVA 2.0 schemas already have no UNIQUE constraint on branch.name.
    # SQLite exposes the constraint through the CREATE TABLE SQL.
    row = db.session.execute(sa_text("SELECT sql FROM sqlite_master WHERE type='table' AND name='branch'")).fetchone()
    sql = (row[0] or "") if row else ""
    if "UNIQUE (name)" not in sql.upper() and "UNIQUE(name)" not in sql.upper():
        return
    db.session.execute(sa_text("PRAGMA foreign_keys=OFF"))
    db.session.execute(sa_text("""
        CREATE TABLE branch_new (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            name VARCHAR(100) NOT NULL,
            created_at DATETIME
        )
    """))
    db.session.execute(sa_text("INSERT INTO branch_new (id,user_id,name,created_at) SELECT id,user_id,name,created_at FROM branch"))
    db.session.execute(sa_text("DROP TABLE branch"))
    db.session.execute(sa_text("ALTER TABLE branch_new RENAME TO branch"))
    db.session.execute(sa_text("PRAGMA foreign_keys=ON"))
    db.session.commit()

def migrate_branch_columns():
    inspector = sa_inspect(db.engine)
    tables = inspector.get_table_names()
    for table in ("pantry_item", "receipt", "shopping_item", "waste_log"):
        if table not in tables:
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if "branch_id" not in columns:
            db.session.execute(sa_text(f"ALTER TABLE {table} ADD COLUMN branch_id INTEGER"))
    db.session.commit()
    default_branch = Branch.query.order_by(Branch.id.asc()).first()
    if not default_branch:
        default_branch = Branch(name="Home")
        db.session.add(default_branch); db.session.commit()
    for model in (PantryItem, Receipt, ShoppingItem, WasteLog):
        model.query.filter(model.branch_id.is_(None)).update({model.branch_id: default_branch.id}, synchronize_session=False)
    db.session.commit()

with app.app_context():
    init_auth_db()
    init_activity_db()
    db.create_all()
    migrate_user_columns()
    migrate_branch_name_constraint()
    migrate_branch_columns()
    migrate_receipt_item_columns()
    migrate_receipt_columns()
    seed()
    if not Branch.query.first():
        db.session.add(Branch(name="Home")); db.session.commit()

if __name__ == "__main__":
    app.run(debug=True)
