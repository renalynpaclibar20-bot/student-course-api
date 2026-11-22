import os
import sqlite3
from flask import Flask, g, jsonify, render_template, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campus.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS students(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE, program TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS courses(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL, department TEXT NOT NULL, capacity INTEGER NOT NULL DEFAULT 35);
CREATE TABLE IF NOT EXISTS enrollments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  semester TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(student_id, course_id, semester));
CREATE TABLE IF NOT EXISTS announcements(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""

STUDENTS = [("Ana Reyes", "ana@campus.edu", "BSIT"), ("Ben Cruz", "ben@campus.edu", "BSCS"),
            ("Carla Santos", "carla@campus.edu", "BSIS"), ("Dan Lim", "dan@campus.edu", "BSIT"),
            ("Ella Tan", "ella@campus.edu", "BSCS"), ("Faye Ramos", "faye@campus.edu", "BSIS"),
            ("Gio Diaz", "gio@campus.edu", "BSIT"), ("Hana Uy", "hana@campus.edu", "BSCS")]
COURSES = [("IT101", "Intro to Computing", "Information Technology"),
           ("IT201", "Web Development", "Information Technology"),
           ("CS101", "Programming Fundamentals", "Computer Science"),
           ("CS220", "Data Structures", "Computer Science"),
           ("IS110", "Systems Analysis", "Information Systems"),
           ("IS240", "Database Management", "Information Systems"),
           ("GE101", "Communication Skills", "General Education"),
           ("GE105", "Mathematics for Computing", "General Education")]


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    if not conn.execute("SELECT 1 FROM students").fetchone():
        conn.executemany("INSERT INTO students(name,email,program) VALUES(?,?,?)", STUDENTS)
        conn.executemany("INSERT INTO courses(code,title,department) VALUES(?,?,?)", COURSES)
        conn.executemany("INSERT INTO enrollments(student_id,course_id,semester) VALUES(?,?,?)",
                         [(1, 1, "Second Semester"), (2, 3, "Second Semester"), (3, 5, "Second Semester")])
        conn.execute("INSERT INTO announcements(title,body) VALUES(?,?)",
                     ("Enrollment is open", "Second semester enrollment runs until the end of the month."))
    conn.commit()
    conn.close()


def rows(sql, args=()):
    return [dict(r) for r in db().execute(sql, args).fetchall()]


def body(*required):
    data = request.get_json(silent=True) or {}
    missing = [k for k in required if not str(data.get(k, "")).strip()]
    if missing:
        return None, (jsonify(error="Missing: " + ", ".join(missing)), 400)
    return data, None


# ---------- Pages ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/students")
def students_page():
    return render_template("students.html")


@app.route("/courses")
def courses_page():
    return render_template("courses.html")


@app.route("/enrollment")
def enrollment_page():
    return render_template("enrollment.html")


@app.route("/announcements")
def announcements_page():
    return render_template("announcement.html")


# ---------- API ----------
@app.get("/api/stats")
def stats():
    q = lambda s: db().execute(s).fetchone()[0]
    return jsonify(
        students=q("SELECT COUNT(*) FROM students"),
        programs=q("SELECT COUNT(DISTINCT program) FROM students"),
        courses=q("SELECT COUNT(*) FROM courses"),
        departments=q("SELECT COUNT(DISTINCT department) FROM courses"),
        capacity=q("SELECT COALESCE(CAST(AVG(capacity) AS INT),0) FROM courses"),
        enrollments=q("SELECT COUNT(*) FROM enrollments"),
        available=q("""SELECT COUNT(*) FROM courses c WHERE
                       (SELECT COUNT(*) FROM enrollments e WHERE e.course_id=c.id) < c.capacity"""),
    )


def delete(table, item_id):
    db().execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
    db().commit()
    return jsonify(ok=True)


@app.get("/api/students")
def list_students():
    return jsonify(rows("SELECT * FROM students ORDER BY name"))


@app.post("/api/students")
def add_student():
    data, err = body("name", "email", "program")
    if err:
        return err
    try:
        db().execute("INSERT INTO students(name,email,program) VALUES(?,?,?)",
                     (data["name"].strip(), data["email"].strip(), data["program"].strip()))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That email is already registered."), 409
    return jsonify(ok=True), 201


@app.delete("/api/students/<int:item_id>")
def del_student(item_id):
    return delete("students", item_id)


@app.get("/api/courses")
def list_courses():
    return jsonify(rows("""SELECT c.*, (SELECT COUNT(*) FROM enrollments e WHERE e.course_id=c.id) AS enrolled
                           FROM courses c ORDER BY code"""))


@app.post("/api/courses")
def add_course():
    data, err = body("code", "title", "department")
    if err:
        return err
    try:
        db().execute("INSERT INTO courses(code,title,department,capacity) VALUES(?,?,?,?)",
                     (data["code"].strip(), data["title"].strip(), data["department"].strip(),
                      int(data.get("capacity") or 35)))
        db().commit()
    except (sqlite3.IntegrityError, ValueError):
        return jsonify(error="Course code must be unique and capacity a number."), 409
    return jsonify(ok=True), 201


@app.delete("/api/courses/<int:item_id>")
def del_course(item_id):
    return delete("courses", item_id)


@app.get("/api/enrollments")
def list_enrollments():
    return jsonify(rows("""SELECT e.id, s.name AS student, c.code || ' - ' || c.title AS course,
                           e.semester, e.created_at FROM enrollments e
                           JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id
                           ORDER BY e.id DESC"""))


@app.post("/api/enrollments")
def add_enrollment():
    data, err = body("student_id", "course_id", "semester")
    if err:
        return err
    course = db().execute("""SELECT capacity, (SELECT COUNT(*) FROM enrollments WHERE course_id=?) AS n
                             FROM courses WHERE id=?""", (data["course_id"], data["course_id"])).fetchone()
    if not course:
        return jsonify(error="Course not found."), 404
    if course["n"] >= course["capacity"]:
        return jsonify(error="This course is full."), 409
    try:
        db().execute("INSERT INTO enrollments(student_id,course_id,semester) VALUES(?,?,?)",
                     (data["student_id"], data["course_id"], data["semester"]))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Student is already enrolled in this course."), 409
    return jsonify(ok=True), 201


@app.delete("/api/enrollments/<int:item_id>")
def del_enrollment(item_id):
    return delete("enrollments", item_id)


@app.get("/api/announcements")
def list_announcements():
    return jsonify(rows("SELECT * FROM announcements ORDER BY id DESC"))


@app.post("/api/announcements")
def add_announcement():
    data, err = body("title", "body")
    if err:
        return err
    db().execute("INSERT INTO announcements(title,body) VALUES(?,?)", (data["title"].strip(), data["body"].strip()))
    db().commit()
    return jsonify(ok=True), 201


@app.delete("/api/announcements/<int:item_id>")
def del_announcement(item_id):
    return delete("announcements", item_id)


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
