import math
import os
from datetime import date, datetime
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import (
    Flask, flash, g, redirect, render_template, request, session
)
from flask_session import Session
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000")

if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be set in .env")
supabase=create_client(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY
)

app = Flask(
    __name__,
    template_folder=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "templates"
    )
)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY must be set in .env")

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)

@app.route("/health")
def health():
    return{"status": "ok"},200

# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def new_client():
    """A fresh Supabase client. Never share one client between users,
    because set_session() stores that user's tokens on the client."""
    return create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)


def get_user_client():
    """Return a Supabase client authenticated as the logged-in user,
    or None if there is no valid session."""
    if "user_id" not in session or "access_token" not in session:
        return None

    client = new_client()
    try:
        auth = client.auth.set_session(
            session["access_token"],
            session["refresh_token"]
        )
    except Exception as e:
        print("Session error:", e)
        session.clear()
        return None

    # set_session refreshes expired tokens, so keep the new ones
    if auth and auth.session:
        session["access_token"] = auth.session.access_token
        session["refresh_token"] = auth.session.refresh_token

    return client


def login_required(view):
    """For pages: redirect to /login when not signed in."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        g.db = get_user_client()
        if g.db is None:
            return redirect("/login")
        return view(*args, **kwargs)
    return wrapped


def api_login_required(view):
    """For JSON API routes: return 401 when not signed in."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        g.db = get_user_client()
        if g.db is None:
            return {"error": "Unauthorized"}, 401
        return view(*args, **kwargs)
    return wrapped


def parse_date(value):
    """Accept dd-mm-yyyy or yyyy-mm-dd. Return a date or None."""
    value = (value or "").strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def clean_expense(data):
    """Validate expense input (form or JSON).
    Returns (clean_dict, error_message)."""
    amount_text = str(data.get("amount", "")).strip()
    category = str(data.get("category", "")).strip()
    description = str(data.get("description", "")).strip()
    date_text = str(data.get("date", "")).strip()

    if not amount_text or not category or not description or not date_text:
        return None, "All fields are required."

    try:
        amount = float(amount_text)
    except ValueError:
        return None, "Amount must be a valid number."

    if not math.isfinite(amount):
        return None, "Amount must be a valid number."

    if amount <= 0:
        return None, "Amount must be greater than 0."

    parsed = parse_date(date_text)
    if parsed is None:
        return None, "Date must be in dd-mm-yyyy format."

    return {
        "amount": amount,
        "category": category,
        "description": description,
        "date": parsed.isoformat(),  # Supabase stores yyyy-mm-dd
    }, None


def load_expenses():
    response = (
        g.db
        .table("expenses")
        .select("*")
        .eq("user_id", session["user_id"])
        .order("date", desc=True)
        .execute()
    )
    return response.data or []


# ----------------------------------------------------------
# Auth
# ----------------------------------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.")
            return render_template("signup.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.")
            return render_template("signup.html")

        try:
            response = new_client().auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {"name": name}  # was "date": the name was never saved
                }
            })
        except Exception as e:
            print("Signup error:", e)
            flash("Sign up failed. Try a different email or password.")
            return render_template("signup.html")

        if response.user:
            flash("Account created successfully. Please log in.")
            return redirect("/login")

        flash("Sign up failed.")
        return render_template("signup.html")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        try:
            response = new_client().auth.sign_in_with_password({
                "email": email,
                "password": password
            })
        except Exception as e:
            # Supabase raises on wrong credentials instead of returning None
            print("Login error:", e)
            flash("Login failed. Check your email and password.")
            return render_template("login.html")

        if response.user:
            session["user_id"] = response.user.id
            session["user_name"] = response.user.user_metadata.get("name", "User")
            session["access_token"] = response.session.access_token
            session["refresh_token"] = response.session.refresh_token

            flash("Login successful! Welcome back 👋", "success")

            return redirect("/")

       
        flash("Invalid email or password.", "error")
        return redirect("/login")

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        try:
            new_client().auth.reset_password_for_email(
                email,
                {"redirect_to": f"{APP_BASE_URL}/reset-password"}
            )
        except Exception as e:
            print("Forgot password error:", e)

        # Same message either way, so emails can't be probed
        return "If that email exists, a password reset link has been sent."

    return render_template("forgot_password.html")


@app.route("/reset-password")
def reset_password():
    return render_template("reset_password.html")


@app.route("/api/reset-password", methods=["POST"])
def api_reset_password():
    data = request.get_json(silent=True) or {}

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    password = data.get("password")

    if not access_token or not refresh_token:
        return {"error": "Invalid reset session"}, 400

    if not password or len(password) < 6:
        return {"error": "Password must be at least 6 characters"}, 400

    try:
        client = new_client()
        client.auth.set_session(access_token, refresh_token)
        response = client.auth.update_user({"password": password})

        if not response.user:
            return {"error": "Password update failed"}, 400

        return {"message": "Password changed successfully"}

    except Exception as e:
        print("Password reset error:", e)
        return {"error": "Password reset failed"}, 400

@app.route("/logout")
def logout():

    session.clear()

    flash("Logged out successfully. See you again! 👋", "success")

    return redirect("/login")

# ----------------------------------------------------------
# Pages
# ----------------------------------------------------------
@app.route("/")
@login_required
def home():
    expenses = load_expenses()

    # Search
    search = request.args.get("search", "").strip().lower()
    if search:
        expenses = [
            e for e in expenses
            if search in (e.get("description") or "").lower()
        ]

    # Category filter
    category_filter = request.args.get("category", "").strip().lower()
    if category_filter:
        expenses = [
            e for e in expenses
            if (e.get("category") or "").lower() == category_filter
        ]

    # Date filter (accepts dd-mm-yyyy or yyyy-mm-dd)
    date_filter = request.args.get("date", "").strip()
    if date_filter:
        parsed = parse_date(date_filter)
        if parsed is None:
            flash("Date filter must be in dd-mm-yyyy format.")
        else:
            iso = parsed.isoformat()
            expenses = [e for e in expenses if e["date"] == iso]

    # Sorting (dates are stored as yyyy-mm-dd)
    sort = request.args.get("sort", "")
    if sort == "amount_asc":
        expenses.sort(key=lambda e: float(e["amount"]))
    elif sort == "amount_desc":
        expenses.sort(key=lambda e: float(e["amount"]), reverse=True)
    elif sort == "date_asc":
        expenses.sort(key=lambda e: e["date"])
    elif sort == "date_desc":
        expenses.sort(key=lambda e: e["date"], reverse=True)

    # dd-mm-yyyy copy for display; "date" stays ISO for edit forms
    for e in expenses:
        parsed = parse_date(e["date"])
        e["display_date"] = parsed.strftime("%d-%m-%Y") if parsed else e["date"]

    total = sum(float(e["amount"]) for e in expenses)
    highest = max((float(e["amount"]) for e in expenses), default=0)
    average = total / len(expenses) if expenses else 0

    category_totals = {}
    for e in expenses:
        name = e["category"]
        category_totals[name] = category_totals.get(name, 0) + float(e["amount"])

    return render_template(
        "index.html",
        expenses=expenses,
        total=total,
        highest=highest,
        average=average,
        category_totals=category_totals
    )


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_expense():

    if request.method == "POST":

        amount = request.form["amount"]
        category = request.form["category"]
        description = request.form["description"]
        date = request.form["date"]

        expense = {
            "user_id": session["user_id"],
            "amount": float(amount),
            "category": category,
            "description": description,
            "date": date
        }
        supabase.auth.set_session(
            session["access_token"],
            session["refresh_token"]
        )

        response = (
           supabase
            .table("expenses")
            .insert(expense)
            .execute()
        )

        if response.data:
            flash("Expense added successfully! 💰", "success")
            return redirect("/")

        flash("Failed to add expense.", "error")

    return render_template("add_expense.html")


@app.route("/delete/<expense_id>", methods=["GET", "POST"])
@login_required
def delete_expense(expense_id):
    try:
        (
            g.db
            .table("expenses")
            .delete()
            .eq("id", expense_id)
            .eq("user_id", session["user_id"])
            .execute()
        )
    except Exception as e:
        print("Delete expense error:", e)
        flash("Could not delete the expense.")
        return redirect("/")

    flash("Expense deleted successfully! 🗑️", "success")

    return redirect("/")


@app.route("/edit/<expense_id>", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    try:
        response = (
            g.db
            .table("expenses")
            .select("*")
            .eq("id", expense_id)
            .eq("user_id", session["user_id"])
            .execute()
        )
    except Exception as e:
        print("Edit lookup error:", e)
        flash("Expense not found.")
        return redirect("/")

    if not response.data:
        flash("Expense not found.")
        return redirect("/")

    expense = response.data[0]

    if request.method == "POST":
        updated, error = clean_expense(request.form)
        if error:
            flash(error)
            return redirect(f"/edit/{expense_id}")

        try:
            (
                g.db
                .table("expenses")
                .update(updated)
                .eq("id", expense_id)
                .eq("user_id", session["user_id"])
                .execute()
            )
        except Exception as e:
            print("Edit update error:", e)
            flash("Could not update the expense.")
            return redirect(f"/edit/{expense_id}")

        flash("Expense updated successfully! ✏️", "success")

        return redirect("/")

    return render_template("edit.html", expense=expense)


# ----------------------------------------------------------
# JSON API
# ----------------------------------------------------------
@app.route("/api/expenses/summary", methods=["GET"])
@api_login_required
def api_expense_summary():
    expenses = load_expenses()

    if not expenses:
        return {
            "total_spending": 0,
            "this_month_spending": 0,
            "average_expense": 0,
            "highest_expense": 0,
            "number_of_expenses": 0,
            "categories": {}
        }

    today = date.today()
    total_spending = 0.0
    this_month_spending = 0.0
    highest_expense = 0.0
    category_totals = {}

    for e in expenses:
        amount = float(e["amount"])
        total_spending += amount
        highest_expense = max(highest_expense, amount)

        d = date.fromisoformat(e["date"])
        if d.month == today.month and d.year == today.year:
            this_month_spending += amount

        category_totals[e["category"]] = category_totals.get(e["category"], 0) + amount

    return {
        "total_spending": round(total_spending, 2),
        "this_month_spending": round(this_month_spending, 2),
        "average_expense": round(total_spending / len(expenses), 2),
        "highest_expense": highest_expense,
        "number_of_expenses": len(expenses),
        "categories": category_totals
    }


@app.route("/api/expenses", methods=["GET"])
@api_login_required
def api_get_expenses():
    return {"expenses": load_expenses()}


@app.route("/api/expenses", methods=["POST"])
@api_login_required
def api_create_expense():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be JSON"}, 400

    expense, error = clean_expense(data)
    if error:
        return {"error": error}, 400

    expense["user_id"] = session["user_id"]

    try:
        response = g.db.table("expenses").insert(expense).execute()
    except Exception as e:
        print("API create error:", e)
        return {"error": "Could not create expense"}, 500

    return {
        "message": "Expense created successfully",
        "expense": response.data
    }, 201


@app.route("/api/expenses/<expense_id>", methods=["GET"])
@api_login_required
def api_get_expense(expense_id):
    response = (
        g.db
        .table("expenses")
        .select("*")
        .eq("id", expense_id)
        .eq("user_id", session["user_id"])
        .execute()
    )

    if not response.data:
        return {"error": "Expense not found"}, 404

    return {"expense": response.data[0]}


@app.route("/api/expenses/<expense_id>", methods=["PUT"])
@api_login_required
def api_update_expense(expense_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be JSON"}, 400

    expense, error = clean_expense(data)
    if error:
        return {"error": error}, 400

    response = (
        g.db
        .table("expenses")
        .update(expense)
        .eq("id", expense_id)
        .eq("user_id", session["user_id"])
        .execute()
    )

    if not response.data:
        return {"error": "Expense not found"}, 404

    return {
        "message": "Expense updated successfully",
        "expense": response.data[0]
    }


@app.route("/api/expenses/<expense_id>", methods=["DELETE"])
@api_login_required
def api_delete_expense(expense_id):
    response = (
        g.db
        .table("expenses")
        .delete()
        .eq("id", expense_id)
        .eq("user_id", session["user_id"])
        .execute()
    )

    if not response.data:
        return {"error": "Expense not found"}, 404

    return {"message": "Expense deleted successfully"}




@app.route("/api/currency")
def currency():
    currency_code = request.args.get("currency", "USD").upper()

    allowed_currencies = {
        "INR", "USD", "EUR", "GBP", "AED",
        "CAD", "AUD", "JPY", "SGD"
    }

    if currency_code not in allowed_currencies:
        return {"error": "Unsupported currency"}, 400

    if currency_code == "INR":
        return {
            "amount": 1,
            "base": "INR",
            "rates": {"INR": 1}
        }

    try:
        # Get the INR-to-target rate using Frankfurter v2.
        response = requests.get(
            "https://api.frankfurter.dev/v2/rates",
            params={
                "base": "INR",
                "quotes": currency_code
            },
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        # V2 returns a list of rate records.
        rate_record = next(
            (
                item for item in data
                if item.get("quote") == currency_code
            ),
            None
        )

        if not rate_record:
            return {"error": "Exchange rate unavailable"}, 502

        return {
            "amount": 1,
            "base": "INR",
            "date": rate_record["date"],
            "rates": {
                currency_code: rate_record["rate"]
            }
        }

    except (requests.RequestException, ValueError, KeyError) as error:
        app.logger.error("Currency API error: %s", error)
        return {"error": "Unable to fetch exchange rate"}, 502
if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1")
