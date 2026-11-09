import os
import sqlite3
from datetime import date
from functools import wraps
from io import BytesIO

from flask import Flask, request, redirect, url_for, session, flash, render_template_string, send_file
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("COLLEGE_SECRET_KEY", "change-this-secret-before-real-use")
DB_PATH = os.environ.get("COLLEGE_DB", "college.db")

# First-run login: admin / admin123
# Change the password before storing real college records.

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_type TEXT NOT NULL CHECK(person_type IN ('Teacher','Student','Peon','Watchman')),
            full_name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            class_name TEXT DEFAULT '',
            monthly_fee REAL DEFAULT 0,
            monthly_salary REAL DEFAULT 0,
            joined_on TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS fee_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
            month TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            paid_on TEXT NOT NULL,
            note TEXT DEFAULT '',
            UNIQUE(student_id, month)
        );
        CREATE TABLE IF NOT EXISTS salary_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
            month TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            paid_on TEXT NOT NULL,
            note TEXT DEFAULT '',
            UNIQUE(staff_id, month)
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
            day TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Present','Absent','Leave')),
            note TEXT DEFAULT '',
            UNIQUE(person_id, day)
        );
        """)
        user = con.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if not user:
            con.execute("INSERT INTO users(username,password_hash) VALUES (?,?)",
                        ("admin", generate_password_hash("admin123")))

init_db()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

STYLE = """
:root{--navy:#12304a;--blue:#176b87;--bg:#f3f6f9;--ink:#172b3a;--muted:#627381;--line:#dce4ea}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:Arial,sans-serif;color:var(--ink)}
header{background:var(--navy);color:#fff;padding:16px 22px;display:flex;gap:14px;justify-content:space-between;align-items:center;flex-wrap:wrap}
header strong{font-size:20px}header a{color:#fff;text-decoration:none;margin-left:12px}
main{max-width:1180px;margin:22px auto;padding:0 14px}.nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
.nav a,.btn{background:var(--blue);color:white;text-decoration:none;border:0;border-radius:7px;padding:10px 13px;display:inline-block;cursor:pointer;font-size:14px}
.nav a{background:#fff;color:var(--navy);border:1px solid var(--line)}.nav a:hover{background:#e7f2f6}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:17px;margin-bottom:16px;box-shadow:0 2px 7px #15364b0a}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.stat{font-size:25px;font-weight:bold;margin-top:7px}.muted{color:var(--muted);font-size:13px}
h1{font-size:25px;margin:8px 0 16px}h2{font-size:18px;margin:0 0 13px}
label{display:block;font-size:13px;font-weight:bold;margin:10px 0 5px}
input,select,textarea{width:100%;padding:10px;border:1px solid #cbd7df;border-radius:7px;background:white;font:inherit}
textarea{min-height:65px}form .btn{margin-top:13px}
.formgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px 13px}
table{border-collapse:collapse;width:100%;background:#fff}th,td{padding:10px 9px;text-align:left;border-bottom:1px solid var(--line);font-size:14px}th{background:#eef4f7}
.tablewrap{overflow-x:auto}.flash{padding:11px;border-radius:7px;background:#fff3cd;margin-bottom:12px}
.smallbtn{padding:6px 9px;font-size:12px}.danger{background:#9c2f36}.right{float:right}
@media(max-width:600px){header{align-items:flex-start}header a{margin:5px 8px 0 0}h1{font-size:22px}th,td{padding:8px 6px;font-size:12px}}
"""

BASE = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} - College Management</title><style>""" + STYLE + """</style></head><body>
<header><strong>College Management System</strong><div>{% if session.get('user_id') %}
<a href="{{ url_for('index') }}">Dashboard</a><a href="{{ url_for('people') }}">Records</a>
<a href="{{ url_for('fees') }}">Fees</a><a href="{{ url_for('salaries') }}">Salaries</a>
<a href="{{ url_for('attendance_page') }}">Attendance</a><a href="{{ url_for('reports') }}">Reports</a>
<a href="{{ url_for('logout') }}">Logout</a>{% endif %}</div></header>
<main>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="flash">{{ m }}</div>{% endfor %}{% endwith %}
""" + "{{ body|safe }}" + """</main></body></html>
"""

def page(title, body, **context):
    return render_template_string(BASE, title=title, body=render_template_string(body, **context))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))
        flash("Username ya password ghalat hai.")
    body = """
    <div class="card" style="max-width:430px;margin:40px auto"><h1>Admin Login</h1>
    <p class="muted">Demo login: admin / admin123</p><form method="post">
    <label>Username</label><input name="username" required>
    <label>Password</label><input type="password" name="password" required>
    <button class="btn">Login</button></form></div>"""
    return page("Login", body)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    with db() as con:
        counts = {r["person_type"]: r["n"] for r in con.execute(
            "SELECT person_type,COUNT(*) n FROM people GROUP BY person_type")}
        fee_month = date.today().strftime("%Y-%m")
        fees_paid = con.execute("SELECT COALESCE(SUM(amount),0) n FROM fee_payments WHERE month=?", (fee_month,)).fetchone()["n"]
        salary_paid = con.execute("SELECT COALESCE(SUM(amount),0) n FROM salary_payments WHERE month=?", (fee_month,)).fetchone()["n"]
        attend_today = con.execute("SELECT COUNT(*) n FROM attendance WHERE day=? AND status='Present'", (date.today().isoformat(),)).fetchone()["n"]
    body = """
    <h1>Dashboard</h1><div class="grid">
    {% for label,value in [('Teachers',counts.get('Teacher',0)),('Students',counts.get('Student',0)),('Peons',counts.get('Peon',0)),('Watchmen',counts.get('Watchman',0))] %}
    <div class="card"><div class="muted">{{ label }}</div><div class="stat">{{ value }}</div></div>{% endfor %}
    <div class="card"><div class="muted">Is mahine fees received</div><div class="stat">Rs {{ '%.2f'|format(fees_paid) }}</div></div>
    <div class="card"><div class="muted">Is mahine salary paid</div><div class="stat">Rs {{ '%.2f'|format(salary_paid) }}</div></div>
    <div class="card"><div class="muted">Aaj present</div><div class="stat">{{ attend_today }}</div></div></div>
    <div class="card"><h2>Shuru karne ka tareeqa</h2><p>Records mein teachers, students, peons aur watchman add karein. Phir Fees, Salaries aur Attendance ke pages use karein.</p>
    <p><b>Important:</b> Real data se pehle admin password change karein aur database backup rakhein.</p></div>"""
    return page("Dashboard", body, counts=counts, fees_paid=fees_paid, salary_paid=salary_paid, attend_today=attend_today)

@app.route("/people", methods=["GET","POST"])
@login_required
def people():
    if request.method == "POST":
        typ = request.form.get("person_type")
        name = request.form.get("full_name","").strip()
        if typ not in ("Teacher","Student","Peon","Watchman") or not name:
            flash("Type aur naam zaroori hain.")
        else:
            with db() as con:
                con.execute("""INSERT INTO people(person_type,full_name,phone,class_name,monthly_fee,monthly_salary,joined_on,notes)
                VALUES(?,?,?,?,?,?,?,?)""", (typ,name,request.form.get("phone","").strip(),
                request.form.get("class_name","").strip(), safe_float(request.form.get("monthly_fee")),
                safe_float(request.form.get("monthly_salary")),request.form.get("joined_on",""),
                request.form.get("notes","").strip()))
            flash("Record save ho gaya.")
        return redirect(url_for("people"))
    q = request.args.get("q","").strip()
    with db() as con:
        rows = con.execute("""SELECT * FROM people WHERE full_name LIKE ? OR person_type LIKE ? OR phone LIKE ?
        ORDER BY person_type,full_name""", (f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    body = """
    <h1>People Records</h1><div class="card"><h2>Naya record add karein</h2><form method="post"><div class="formgrid">
    <div><label>Type</label><select name="person_type" required><option>Teacher</option><option>Student</option><option>Peon</option><option>Watchman</option></select></div>
    <div><label>Full name</label><input name="full_name" required></div><div><label>Phone</label><input name="phone"></div>
    <div><label>Class / Section (students)</label><input name="class_name"></div><div><label>Monthly fee (students)</label><input type="number" min="0" step="0.01" name="monthly_fee" value="0"></div>
    <div><label>Monthly salary (staff)</label><input type="number" min="0" step="0.01" name="monthly_salary" value="0"></div>
    <div><label>Joining / admission date</label><input type="date" name="joined_on"></div><div><label>Notes</label><input name="notes"></div></div><button class="btn">Save record</button></form></div>
    <div class="card"><form method="get"><label>Search records</label><input name="q" value="{{ q }}" placeholder="Name, type, phone"><button class="btn">Search</button></form>
    <div class="tablewrap"><table><tr><th>ID</th><th>Type</th><th>Name</th><th>Phone</th><th>Class</th><th>Monthly fee</th><th>Monthly salary</th><th>Action</th></tr>
    {% for p in rows %}<tr><td>{{p.id}}</td><td>{{p.person_type}}</td><td>{{p.full_name}}</td><td>{{p.phone}}</td><td>{{p.class_name}}</td>
    <td>{{ '%.2f'|format(p.monthly_fee) }}</td><td>{{ '%.2f'|format(p.monthly_salary) }}</td><td>
    <form method="post" action="{{url_for('delete_person',pid=p.id)}}" onsubmit="return confirm('Is record ko delete karna hai?')"><button class="btn danger smallbtn">Delete</button></form></td></tr>{% endfor %}
    </table></div></div>"""
    return page("Records", body, rows=rows, q=q)

def safe_float(value):
    try:
        number = float(value or 0)
        return number if number >= 0 else 0
    except (ValueError, TypeError):
        return 0

@app.route("/people/<int:pid>/delete", methods=["POST"])
@login_required
def delete_person(pid):
    with db() as con:
        con.execute("DELETE FROM people WHERE id=?", (pid,))
    flash("Record aur us se related payments/attendance delete ho gaye.")
    return redirect(url_for("people"))

@app.route("/fees", methods=["GET","POST"])
@login_required
def fees():
    if request.method == "POST":
        sid = request.form.get("student_id", type=int)
        month = request.form.get("month","")
        amount = safe_float(request.form.get("amount"))
        paid_on = request.form.get("paid_on") or date.today().isoformat()
        note = request.form.get("note","").strip()
        with db() as con:
            student = con.execute("SELECT id FROM people WHERE id=? AND person_type='Student'", (sid,)).fetchone()
            if not student or len(month) != 7:
                flash("Student aur month sahi select karein.")
            else:
                try:
                    con.execute("INSERT INTO fee_payments(student_id,month,amount,paid_on,note) VALUES(?,?,?,?,?)",
                                (sid,month,amount,paid_on,note))
                    flash("Fee payment save ho gayi.")
                except sqlite3.IntegrityError:
                    flash("Is student ki is month ki payment pehle se recorded hai. Duplicate se bachne ke liye edit feature is version mein nahi hai.")
        return redirect(url_for("fees"))
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    with db() as con:
        students = con.execute("SELECT * FROM people WHERE person_type='Student' ORDER BY full_name").fetchall()
        rows = con.execute("""SELECT f.*,p.full_name,p.monthly_fee FROM fee_payments f JOIN people p ON p.id=f.student_id
        WHERE f.month=? ORDER BY p.full_name""", (month,)).fetchall()
        total = sum(r["amount"] for r in rows)
        payment_by_student = {r["student_id"]: r["amount"] for r in rows}
        dues = [{"name": st["full_name"], "monthly_fee": st["monthly_fee"],
                 "paid": payment_by_student.get(st["id"], 0),
                 "due": max(0, st["monthly_fee"] - payment_by_student.get(st["id"], 0))}
                for st in students]
    body = """
    <h1>Student Fees</h1><div class="card"><h2>Fee receive karein</h2>
    {% if not students %}<p>Pehle Records page par students add karein.</p>{% else %}
    <form method="post"><div class="formgrid"><div><label>Student</label><select name="student_id" required>{% for s in students %}<option value="{{s.id}}">{{s.full_name}} — monthly fee Rs {{'%.2f'|format(s.monthly_fee)}}</option>{% endfor %}</select></div>
    <div><label>Month</label><input type="month" name="month" value="{{month}}" required></div><div><label>Amount received (Rs)</label><input type="number" name="amount" min="0" step="0.01" required></div>
    <div><label>Payment date</label><input type="date" name="paid_on" value="{{today}}" required></div><div><label>Note / receipt no.</label><input name="note"></div></div><button class="btn">Save fee</button></form>{% endif %}</div>
    <div class="card"><form method="get"><label>Report month</label><input type="month" name="month" value="{{month}}"><button class="btn">Show</button></form>
    <p><b>Received total: Rs {{'%.2f'|format(total)}}</b></p><h2>Monthly fee due status</h2>
    <div class="tablewrap"><table><tr><th>Student</th><th>Monthly fee</th><th>Received</th><th>Remaining due</th></tr>
    {% for d in dues %}<tr><td>{{d.name}}</td><td>{{'%.2f'|format(d.monthly_fee)}}</td><td>{{'%.2f'|format(d.paid)}}</td><td>{{'%.2f'|format(d.due)}}</td></tr>{% endfor %}</table></div>
    <h2 style="margin-top:20px">Payment details</h2><div class="tablewrap"><table><tr><th>Student</th><th>Month</th><th>Received</th><th>Paid on</th><th>Note</th></tr>
    {% for r in rows %}<tr><td>{{r.full_name}}</td><td>{{r.month}}</td><td>{{'%.2f'|format(r.amount)}}</td><td>{{r.paid_on}}</td><td>{{r.note}}</td></tr>{% endfor %}</table></div></div>"""
    return page("Fees", body, students=students, rows=rows, dues=dues, month=month, today=date.today().isoformat(), total=total)

@app.route("/salaries", methods=["GET","POST"])
@login_required
def salaries():
    if request.method == "POST":
        staff_id = request.form.get("staff_id", type=int)
        month = request.form.get("month","")
        amount = safe_float(request.form.get("amount"))
        paid_on = request.form.get("paid_on") or date.today().isoformat()
        note = request.form.get("note","").strip()
        with db() as con:
            staff = con.execute("SELECT id FROM people WHERE id=? AND person_type IN ('Teacher','Peon','Watchman')", (staff_id,)).fetchone()
            if not staff or len(month) != 7:
                flash("Staff aur month sahi select karein.")
            else:
                try:
                    con.execute("INSERT INTO salary_payments(staff_id,month,amount,paid_on,note) VALUES(?,?,?,?,?)",
                                (staff_id,month,amount,paid_on,note))
                    flash("Salary payment save ho gayi.")
                except sqlite3.IntegrityError:
                    flash("Is staff ki is month ki salary pehle se recorded hai.")
        return redirect(url_for("salaries"))
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    with db() as con:
        staff = con.execute("SELECT * FROM people WHERE person_type IN ('Teacher','Peon','Watchman') ORDER BY full_name").fetchall()
        rows = con.execute("""SELECT s.*,p.full_name,p.person_type,p.monthly_salary FROM salary_payments s JOIN people p ON p.id=s.staff_id
        WHERE s.month=? ORDER BY p.full_name""", (month,)).fetchall()
        total = sum(r["amount"] for r in rows)
        payment_by_staff = {r["staff_id"]: r["amount"] for r in rows}
        salary_dues = [{"name": st["full_name"], "role": st["person_type"], "salary": st["monthly_salary"],
                        "paid": payment_by_staff.get(st["id"], 0),
                        "due": max(0, st["monthly_salary"] - payment_by_staff.get(st["id"], 0))}
                       for st in staff]
    body = """
    <h1>Staff Salaries</h1><div class="card"><h2>Salary payment record karein</h2>
    {% if not staff %}<p>Pehle Records page par staff add karein.</p>{% else %}
    <form method="post"><div class="formgrid"><div><label>Staff member</label><select name="staff_id" required>{% for s in staff %}<option value="{{s.id}}">{{s.full_name}} ({{s.person_type}}) — Rs {{'%.2f'|format(s.monthly_salary)}}</option>{% endfor %}</select></div>
    <div><label>Month</label><input type="month" name="month" value="{{month}}" required></div><div><label>Amount paid (Rs)</label><input type="number" name="amount" min="0" step="0.01" required></div>
    <div><label>Payment date</label><input type="date" name="paid_on" value="{{today}}" required></div><div><label>Note / transaction ID</label><input name="note"></div></div><button class="btn">Save salary</button></form>{% endif %}</div>
    <div class="card"><form method="get"><label>Report month</label><input type="month" name="month" value="{{month}}"><button class="btn">Show</button></form>
    <p><b>Total salary paid: Rs {{'%.2f'|format(total)}}</b></p><h2>Monthly salary status</h2>
    <div class="tablewrap"><table><tr><th>Staff</th><th>Role</th><th>Monthly salary</th><th>Paid</th><th>Remaining</th></tr>
    {% for d in salary_dues %}<tr><td>{{d.name}}</td><td>{{d.role}}</td><td>{{'%.2f'|format(d.salary)}}</td><td>{{'%.2f'|format(d.paid)}}</td><td>{{'%.2f'|format(d.due)}}</td></tr>{% endfor %}</table></div>
    <h2 style="margin-top:20px">Payment details</h2><div class="tablewrap"><table><tr><th>Staff</th><th>Role</th><th>Month</th><th>Paid</th><th>Paid on</th><th>Note</th></tr>
    {% for r in rows %}<tr><td>{{r.full_name}}</td><td>{{r.person_type}}</td><td>{{r.month}}</td><td>{{'%.2f'|format(r.amount)}}</td><td>{{r.paid_on}}</td><td>{{r.note}}</td></tr>{% endfor %}</table></div></div>"""
    return page("Salaries", body, staff=staff, rows=rows, salary_dues=salary_dues, month=month, today=date.today().isoformat(), total=total)

@app.route("/attendance", methods=["GET","POST"])
@login_required
def attendance_page():
    day = request.args.get("day") or date.today().isoformat()
    if request.method == "POST":
        day = request.form.get("day") or date.today().isoformat()
        pid = request.form.get("person_id", type=int)
        status = request.form.get("status")
        note = request.form.get("note","").strip()
        if status not in ("Present","Absent","Leave"):
            flash("Attendance status sahi nahi.")
        else:
            with db() as con:
                try:
                    con.execute("INSERT INTO attendance(person_id,day,status,note) VALUES(?,?,?,?)",(pid,day,status,note))
                    flash("Attendance save ho gayi.")
                except sqlite3.IntegrityError:
                    flash("Is person ki attendance is date par pehle se maujood hai.")
        return redirect(url_for("attendance_page", day=day))
    with db() as con:
        people_rows = con.execute("SELECT * FROM people ORDER BY person_type,full_name").fetchall()
        rows = con.execute("""SELECT a.*,p.full_name,p.person_type FROM attendance a JOIN people p ON p.id=a.person_id
        WHERE a.day=? ORDER BY p.person_type,p.full_name""", (day,)).fetchall()
    body = """
    <h1>Attendance</h1><div class="card"><h2>Attendance mark karein</h2>
    {% if not people_rows %}<p>Pehle records add karein.</p>{% else %}<form method="post"><div class="formgrid">
    <div><label>Person</label><select name="person_id" required>{% for p in people_rows %}<option value="{{p.id}}">{{p.full_name}} ({{p.person_type}})</option>{% endfor %}</select></div>
    <div><label>Date</label><input type="date" name="day" value="{{day}}" required></div>
    <div><label>Status</label><select name="status"><option>Present</option><option>Absent</option><option>Leave</option></select></div>
    <div><label>Note</label><input name="note"></div></div><button class="btn">Save attendance</button></form>{% endif %}</div>
    <div class="card"><form method="get"><label>Attendance date</label><input type="date" name="day" value="{{day}}"><button class="btn">Show</button></form>
    <div class="tablewrap"><table><tr><th>Name</th><th>Type</th><th>Date</th><th>Status</th><th>Note</th></tr>
    {% for r in rows %}<tr><td>{{r.full_name}}</td><td>{{r.person_type}}</td><td>{{r.day}}</td><td>{{r.status}}</td><td>{{r.note}}</td></tr>{% endfor %}</table></div></div>"""
    return page("Attendance", body, people_rows=people_rows, rows=rows, day=day)

@app.route("/reports")
@login_required
def reports():
    year = request.args.get("year", str(date.today().year))
    with db() as con:
        fee_rows = con.execute("SELECT month, SUM(amount) total FROM fee_payments WHERE month LIKE ? GROUP BY month ORDER BY month", (year+"-%",)).fetchall()
        salary_rows = con.execute("SELECT month, SUM(amount) total FROM salary_payments WHERE month LIKE ? GROUP BY month ORDER BY month", (year+"-%",)).fetchall()
        att_rows = con.execute("""SELECT substr(day,1,7) month,status,COUNT(*) n FROM attendance WHERE day LIKE ?
        GROUP BY substr(day,1,7),status ORDER BY month""", (year+"-%",)).fetchall()
    fees_by = {r["month"]: r["total"] for r in fee_rows}
    salaries_by = {r["month"]: r["total"] for r in salary_rows}
    months = sorted(set(fees_by) | set(salaries_by))
    body = """
    <h1>Monthly / Yearly Reports</h1><div class="card"><form method="get"><label>Year</label><input name="year" type="number" min="2000" max="2100" value="{{year}}" required><button class="btn">Show report</button></form>
    <p>Yeh report recorded payments ka total dikhati hai. Jo payment enter nahi hui, woh total mein shamil nahi hogi.</p>
    <p><a class="btn" href="{{url_for('report_pdf',year=year)}}">Download PDF report</a></p>
    <div class="tablewrap"><table><tr><th>Month</th><th>Fees received (Rs)</th><th>Salary paid (Rs)</th><th>Difference (Rs)</th></tr>
    {% for m in all_months %}<tr><td>{{m}}</td><td>{{'%.2f'|format(fees_by.get(m,0))}}</td><td>{{'%.2f'|format(salaries_by.get(m,0))}}</td><td>{{'%.2f'|format(fees_by.get(m,0)-salaries_by.get(m,0))}}</td></tr>{% endfor %}
    <tr><th>Total</th><th>{{'%.2f'|format(fees_by.values()|sum)}}</th><th>{{'%.2f'|format(salaries_by.values()|sum)}}</th><th>{{'%.2f'|format(fees_by.values()|sum-salaries_by.values()|sum)}}</th></tr></table></div>
    <h2 style="margin-top:20px">Attendance summary</h2><div class="tablewrap"><table><tr><th>Month</th><th>Status</th><th>Count</th></tr>{% for r in att_rows %}<tr><td>{{r.month}}</td><td>{{r.status}}</td><td>{{r.n}}</td></tr>{% endfor %}</table></div></div>"""
    all_months = sorted(set(fees_by) | set(salaries_by))
    return page("Reports", body, year=year, fees_by=fees_by, salaries_by=salaries_by, all_months=all_months, att_rows=att_rows)

@app.route("/reports.pdf")
@login_required
def report_pdf():
    year = request.args.get("year", str(date.today().year))
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        flash("PDF ke liye pehle requirements.txt install karein: python -m pip install -r requirements.txt")
        return redirect(url_for("reports", year=year))
    with db() as con:
        fee_rows = con.execute("SELECT month,SUM(amount) total FROM fee_payments WHERE month LIKE ? GROUP BY month ORDER BY month",(year+"-%",)).fetchall()
        sal_rows = con.execute("SELECT month,SUM(amount) total FROM salary_payments WHERE month LIKE ? GROUP BY month ORDER BY month",(year+"-%",)).fetchall()
    fees_by = {r["month"]: r["total"] for r in fee_rows}
    sal_by = {r["month"]: r["total"] for r in sal_rows}
    months = sorted(set(fees_by)|set(sal_by))
    buff = BytesIO()
    c = canvas.Canvas(buff, pagesize=A4)
    width, height = A4
    y = height - 55
    c.setFont("Helvetica-Bold", 16); c.drawString(45,y, f"College Management Report - {year}"); y -= 32
    c.setFont("Helvetica-Bold", 10)
    c.drawString(45,y,"Month"); c.drawString(170,y,"Fees received (Rs)"); c.drawString(320,y,"Salary paid (Rs)"); c.drawString(455,y,"Difference"); y -= 18
    c.setFont("Helvetica", 10)
    total_fee = total_sal = 0
    for m in months:
        f = fees_by.get(m,0); s = sal_by.get(m,0)
        total_fee += f; total_sal += s
        c.drawString(45,y,m); c.drawRightString(285,y,f"{f:.2f}"); c.drawRightString(420,y,f"{s:.2f}"); c.drawRightString(545,y,f"{f-s:.2f}")
        y -= 17
        if y < 70:
            c.showPage(); y = height - 55; c.setFont("Helvetica",10)
    y -= 10; c.setFont("Helvetica-Bold",10)
    c.drawString(45,y,"TOTAL"); c.drawRightString(285,y,f"{total_fee:.2f}"); c.drawRightString(420,y,f"{total_sal:.2f}"); c.drawRightString(545,y,f"{total_fee-total_sal:.2f}")
    c.setFont("Helvetica",8); c.drawString(45,35,"Report includes recorded payments only.")
    c.save(); buff.seek(0)
    return send_file(buff, mimetype="application/pdf", as_attachment=True, download_name=f"college_report_{year}.pdf")

@app.route("/change-password", methods=["GET","POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form.get("old_password","")
        new = request.form.get("new_password","")
        if len(new) < 8:
            flash("Naya password kam az kam 8 characters ka ho.")
        else:
            with db() as con:
                user = con.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
                if user and check_password_hash(user["password_hash"], old):
                    con.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new),user["id"]))
                    flash("Password update ho gaya.")
                    return redirect(url_for("index"))
                flash("Purana password ghalat hai.")
    body = """<div class="card" style="max-width:520px"><h1>Change Admin Password</h1><form method="post">
    <label>Current password</label><input type="password" name="old_password" required>
    <label>New password (at least 8 characters)</label><input type="password" name="new_password" minlength="8" required>
    <button class="btn">Update password</button></form></div>"""
    return page("Change Password", body)

# Add the password page to the navigation by opening /change-password after login.
init_db()
if __name__ == "__main__":
    app.run(debug=True)