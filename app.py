from flask import Flask, request, render_template, redirect, url_for
import sqlite3, os, secrets, datetime

APP_DB = "site.db"
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", "dev-secret-key")

def get_conn():
    conn = sqlite3.connect(APP_DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # users: id, username, password, flag
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        flag TEXT
    )''')

    # submissions: id, submitter, submitted_flag, matched_user, correct (0/1), ts
    c.execute('''
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submitter TEXT,
        submitted_flag TEXT,
        matched_user TEXT,
        correct INTEGER,
        ts TEXT
    )''')

    # Add demo students with unique flags (will not overwrite existing users)
    for i in range(1, 11):
        username = f"student{i}"
        password = "student123"
        # unique flag per student
        flag = f"FLAG{{{username}_{secrets.token_hex(6)}}}"
        # insert only if not exists
        try:
            c.execute("INSERT INTO users (username, password, flag) VALUES (?, ?, ?)",
                      (username, password, flag))
        except sqlite3.IntegrityError:
            pass

    # Add an 'admin' user (higher-value flag), for challenge
    try:
        c.execute("INSERT INTO users (username, password, flag) VALUES (?, ?, ?)",
                  ("admin", "admin123", f"FLAG{{admin_{secrets.token_hex(8)}}}"))
    except sqlite3.IntegrityError:
        pass

    conn.commit()
    conn.close()

@app.route("/", methods=["GET", "POST"])
def index():
    """
    Vulnerable login demonstration.
    Intentionally vulnerable query for educational SQLi testing.
    """
    result = None
    query_shown = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        # INTENTIONALLY VULNERABLE: string formatting into SQL
        query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
        query_shown = query  # show query for teaching
        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute(query)  # vulnerable
            user = c.fetchone()
            if user:
                result = {
                    "ok": True,
                    "username": user["username"],
                    "flag": user["flag"]
                }
            else:
                result = {"ok": False, "msg": "Invalid credentials."}
        except Exception as e:
            result = {"ok": False, "msg": f"SQL error: {e}"}
        conn.close()

    return render_template("index.html", result=result, query_shown=query_shown)

@app.route("/submit", methods=["GET", "POST"])
def submit_flag():
    """
    Submit a flag. This endpoint checks the submitted flag against the DB (safe parameterized check)
    and records the submission.
    """
    message = None
    if request.method == "POST":
        submitter = request.form.get("submitter", "anonymous").strip()
        submitted_flag = request.form.get("flag", "").strip()

        conn = get_conn()
        c = conn.cursor()
        # parameterized query to find if the flag exists and which user it belongs to
        c.execute("SELECT username FROM users WHERE flag = ?", (submitted_flag,))
        row = c.fetchone()
        if row:
            matched_user = row["username"]
            correct = 1
            message = f"Correct! That flag belongs to {matched_user}."
        else:
            matched_user = None
            correct = 0
            message = "Incorrect flag."

        ts = datetime.datetime.utcnow().isoformat() + "Z"
        c.execute("INSERT INTO submissions (submitter, submitted_flag, matched_user, correct, ts) VALUES (?, ?, ?, ?, ?)",
                  (submitter, submitted_flag, matched_user, correct, ts))
        conn.commit()
        conn.close()
        return render_template("submit.html", message=message, posted=True)

    return render_template("submit.html", message=message, posted=False)

@app.route("/leaderboard")
def leaderboard():
    """
    Show recent submissions and a simple scoreboard (count of correct submissions per submitter).
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT submitter, submitted_flag, matched_user, correct, ts FROM submissions ORDER BY id DESC LIMIT 100")
    rows = c.fetchall()

    # scoreboard
    c.execute("SELECT submitter, SUM(correct) as points, COUNT(*) as attempts FROM submissions GROUP BY submitter ORDER BY points DESC, attempts ASC")
    scores = c.fetchall()
    conn.close()
    return render_template("leaderboard.html", rows=rows, scores=scores)

if __name__ == "__main__":
    if not os.path.exists(APP_DB):
        init_db()
    app.run(host="0.0.0.0", port=12345, debug=True)
