from flask import Flask, Response, abort, render_template, redirect, request, session, send_file, send_from_directory
import sqlite3, datetime
from io import BytesIO
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

app = Flask(__name__, template_folder=".", static_folder=None)
app.secret_key = "bcs_secret"


@app.route("/<filename>")
def serve_file(filename):
    direct_file = APP_DIR / filename
    if direct_file.is_file():
        return send_from_directory(APP_DIR, filename)
    return abort(404)


def pdf_dependency_error(exc):
    return (
        "PDF generation is unavailable on this system because ReportLab/Pillow native DLLs are blocked by policy. "
        f"Details: {exc}",
        503,
    )



# ---------------- DATABASE ----------------
def db():
    return sqlite3.connect("database.db")


# ---------------- AUTH CHECK ----------------
def role_required(role):
    return session.get("role") == role


# ---------------- HOME ----------------
@app.route("/")
def index():
    return render_template("index.html")


# ================= STUDENT =================

@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        roll = request.form.get("roll", "").strip()
        semester = request.form.get("semester", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not name or not roll or not semester or not username or not password:
            return "All fields are required"

        try:
            with db() as con:
                cur = con.cursor()

                cur.execute(
                    "INSERT INTO students (name, roll_no, semester, username,password) VALUES (?,?,?,?,?)",
                    (name, roll, semester, username, password)
                )

                cur.execute(
                    "INSERT INTO users (username, password, role) VALUES (?,?,?)",
                    (username, password, "student")
                )

                con.commit()

            return redirect("/student/login")

        except sqlite3.IntegrityError:
            return "Username or roll number already exists"

    return render_template("student_register.html")


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        con = db()
        cur = con.cursor()

        cur.execute(
            "SELECT * FROM users WHERE username=? AND password=? AND role='student'",
            (request.form["username"], request.form["password"])
        )

        user = cur.fetchone()
        con.close()

        if user:
            session["user"] = request.form["username"]
            session["role"] = "student"
            return redirect("/student/dashboard")

        return "Invalid Student Login"

    return render_template("student_login.html")


@app.route("/student/dashboard")
def student_dashboard():
    if "role" not in session or session["role"] != "student":
        return redirect("/student/login")

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT name, roll_no, semester, username
        FROM students
        WHERE username=?
    """, (session["user"],))
    student = cur.fetchone()
    con.close()

    if not student:
        return "Student data not found"

    return render_template("student_dashboard.html", student=student)

# ================= TEACHER =================

@app.route("/teacher/register", methods=["GET", "POST"])
def teacher_register():
    if request.method == "POST":
        try:
            with db() as con:
                cur = con.cursor()

                cur.execute(
                    "INSERT INTO teachers (name, subject, username) VALUES (?,?,?)",
                    (
                        request.form["name"],
                        request.form["subject"],
                        request.form["username"]
                    )
                )

                cur.execute(
                    "INSERT INTO users (username, password, role) VALUES (?,?,?)",
                    (
                        request.form["username"],
                        request.form["password"],
                        "teacher"
                    )
                )

                con.commit()

            return redirect("/teacher/login")

        except sqlite3.IntegrityError:
            return "Username already exists"

        except Exception as e:
            return f"Error: {e}"

    return render_template("teacher_register.html")
@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
    if request.method == "POST":
        con = db()
        cur = con.cursor()

        cur.execute(
            "SELECT * FROM users WHERE username=? AND password=? AND role='teacher'",
            (request.form["username"], request.form["password"])
        )

        user = cur.fetchone()
        con.close()

        if user:
            session["user"] = request.form["username"]
            session["role"] = "teacher"
            return redirect("/teacher/dashboard")

        return "Invalid Teacher Login"

    return render_template("teacher_login.html")


@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "role" not in session or session["role"] != "teacher":
        return redirect("/teacher/login")

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT name, subject, username
        FROM teachers
        WHERE username=?
    """, (session["user"],))
    teacher = cur.fetchone()
    con.close()

    if not teacher:
        return "Teacher data not found"

    return render_template("teacher_dashboard.html", teacher=teacher)


def build_teacher_analysis_data(cur):
    cur.execute("""
        SELECT s.roll_no, s.name, s.semester,
               COALESCE(SUM(m.marks), 0) AS total_obtained,
               COALESCE(SUM(m.max_marks), 0) AS total_max
        FROM students s
        LEFT JOIN marks m ON s.roll_no = m.roll_no
        GROUP BY s.roll_no, s.name, s.semester
        ORDER BY s.roll_no
    """)
    student_rows = cur.fetchall()

    cur.execute("""
        SELECT roll_no, COUNT(*) AS total_lectures,
               SUM(CASE WHEN LOWER(status) = 'present' THEN 1 ELSE 0 END) AS present_lectures
        FROM attendance
        GROUP BY roll_no
    """)
    attendance_map = {
        roll: {
            "total": total_lectures or 0,
            "present": present_lectures or 0,
        }
        for roll, total_lectures, present_lectures in cur.fetchall()
    }

    students = []
    total_percentage_sum = 0
    total_students_with_marks = 0
    pass_count = 0

    for roll, name, semester, total_obtained, total_max in student_rows:
        percentage = round((total_obtained / total_max) * 100, 2) if total_max else 0
        attendance_info = attendance_map.get(roll, {"total": 0, "present": 0})
        attendance_rate = round((attendance_info["present"] / attendance_info["total"]) * 100, 2) if attendance_info["total"] else 0
        grade = get_letter_grade(percentage)
        status = "Pass" if percentage >= 50 else "Fail"
        if total_max:
            total_percentage_sum += percentage
            total_students_with_marks += 1
        if status == "Pass":
            pass_count += 1

        students.append({
            "roll": roll,
            "name": name,
            "semester": semester,
            "obtained": total_obtained,
            "max": total_max,
            "percentage": percentage,
            "attendance_rate": attendance_rate,
            "grade": grade,
            "status": status,
        })

    students_sorted = sorted(students, key=lambda item: item["percentage"], reverse=True)
    top_students = students_sorted[:10]

    cur.execute("""
        SELECT subject, SUM(marks) * 100.0 / SUM(max_marks) AS percentage
        FROM marks
        GROUP BY subject
        ORDER BY subject
    """)
    subject_rows = [
        {"subject": subject, "percentage": round(percentage, 2) if percentage is not None else 0}
        for subject, percentage in cur.fetchall()
    ]

    cur.execute("""
        SELECT subject,
               COUNT(*) AS total,
               SUM(CASE WHEN LOWER(status) = 'present' THEN 1 ELSE 0 END) AS present
        FROM attendance
        GROUP BY subject
        ORDER BY subject
    """)
    attendance_subject_rows = [
        {
            "subject": subject,
            "percentage": round((present / total) * 100, 2) if total else 0,
        }
        for subject, total, present in cur.fetchall()
    ]

    overall_average = round((total_percentage_sum / total_students_with_marks), 2) if total_students_with_marks else 0
    pass_rate = round((pass_count / len(students)) * 100, 2) if students else 0

    return {
        "students": students_sorted,
        "top_students": top_students,
        "subject_rows": subject_rows,
        "attendance_subject_rows": attendance_subject_rows,
        "total_students": len(students),
        "students_with_marks": total_students_with_marks,
        "overall_average": overall_average,
        "pass_count": pass_count,
        "fail_count": len(students) - pass_count,
        "pass_rate": pass_rate,
        "student_labels": [item["roll"] for item in top_students],
        "student_percentages": [item["percentage"] for item in top_students],
        "subject_labels": [item["subject"] for item in subject_rows],
        "subject_percentages": [item["percentage"] for item in subject_rows],
        "attendance_subject_labels": [item["subject"] for item in attendance_subject_rows],
        "attendance_subject_percentages": [item["percentage"] for item in attendance_subject_rows],
    }


@app.route("/teacher/analysis")
def teacher_analysis():
    if not role_required("teacher"):
        return redirect("/teacher/login")

    con = db()
    cur = con.cursor()
    analysis = build_teacher_analysis_data(cur)
    con.close()

    return render_template("teacher_analysis.html", analysis=analysis)

# ================= ATTENDANCE =================

@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    if "role" not in session or session["role"] != "teacher":
        return redirect("/teacher/login")

    con = db()
    cur = con.cursor()

    # Get teacher's subject
    cur.execute("SELECT subject FROM teachers WHERE username=?", (session["user"],))
    teacher_row = cur.fetchone()
    if not teacher_row:
        con.close()
        return "Teacher profile not found"
    teacher_subject = teacher_row[0]

    if request.method == "POST":
        lecture = request.form["lecture"]
        date = datetime.date.today().isoformat()

        for roll, status in zip(request.form.getlist("roll"), request.form.getlist("status")):
            cur.execute("""
                INSERT INTO attendance 
                (roll_no, subject, lecture_no, status, date)
                VALUES (?,?,?,?,?)
            """, (roll, teacher_subject, lecture, status, date))
        con.commit()

    # Fetch all students (no subject filter)
    cur.execute("SELECT roll_no, name FROM students ORDER BY roll_no")
    students = cur.fetchall()

    # Fetch attendance records for this teacher's subject
    cur.execute("""
        SELECT roll_no, subject, lecture_no, status, date
        FROM attendance WHERE subject=? ORDER BY date DESC
    """, (teacher_subject,))
    data = cur.fetchall()

    # Lecture-wise counts for this teacher's subject
    cur.execute("""
        SELECT lecture_no, status, COUNT(*) 
        FROM attendance 
        WHERE subject=? 
        GROUP BY lecture_no, status
        ORDER BY lecture_no
    """, (teacher_subject,))
    counts_raw = cur.fetchall()
    counts = {}
    for lecture, status, cnt in counts_raw:
        if lecture not in counts:
            counts[lecture] = {"Present": 0, "Absent": 0}
        counts[lecture][status] = cnt

    con.close()

    return render_template(
        "attendance_teacher.html",
        students=students,
        data=data,
        counts=counts,
        subject=teacher_subject
    )


@app.route("/download_attendance_pdf/<lecture>")
def download_attendance_pdf(lecture):
    if "role" not in session or session["role"] != "teacher":
        return redirect("/teacher/login")

    con = db()
    cur = con.cursor()

    cur.execute("SELECT subject FROM teachers WHERE username=?", (session["user"],))
    teacher_row = cur.fetchone()
    if not teacher_row:
        con.close()
        return "Teacher profile not found"

    teacher_subject = teacher_row[0]

    cur.execute(
        """
        SELECT roll_no, status, date
        FROM attendance
        WHERE subject=? AND lecture_no=?
        ORDER BY roll_no
        """,
        (teacher_subject, lecture),
    )
    records = cur.fetchall()
    con.close()

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as exc:
        return pdf_dependency_error(exc)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    present_count = sum(1 for _, status, _ in records if str(status).lower() == "present")
    absent_count = len(records) - present_count

    pdf.setTitle(f"Attendance Lecture {lecture}")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, height - 50, f"Attendance Report - {teacher_subject}")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, height - 75, f"Lecture No: {lecture}")
    pdf.drawString(40, height - 92, f"Present: {present_count} | Absent: {absent_count}")

    y = height - 125
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Roll No")
    pdf.drawString(170, y, "Status")
    pdf.drawString(270, y, "Date")
    y -= 14
    pdf.setFont("Helvetica", 10)

    for roll_no, status, date in records:
        if y < 70:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y, str(roll_no))
        pdf.drawString(170, y, str(status))
        pdf.drawString(270, y, str(date))
        y -= 16

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"attendance_{teacher_subject}_lecture_{lecture}.pdf",
        mimetype="application/pdf",
    )

@app.route("/view_attendance")
def view_attendance():
    if "role" not in session or session["role"] != "student":
        return redirect("/student/login")

    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT roll_no FROM students WHERE username=?",
        (session["user"],)
    )
    roll_row = cur.fetchone()
    if not roll_row:
        con.close()
        return "Student not found"
    roll = roll_row[0]

    cur.execute("""
        SELECT subject, lecture_no, status, date
        FROM attendance
        WHERE roll_no=?
        ORDER BY date DESC
    """, (roll,))

    data = cur.fetchall()
    con.close()

    return render_template("attendance_student.html", data=data)

@app.route("/download_student_attendance_pdf")
def download_student_attendance_pdf():
    if "role" not in session or session["role"] != "student":
        return redirect("/student/login")

    con = db()
    cur = con.cursor()

    # Get student roll number
    cur.execute("SELECT roll_no FROM students WHERE username=?", (session["user"],))
    student = cur.fetchone()
    if not student:
        con.close()
        return "Student not found"

    roll = student[0]

    # Fetch all attendance records for this student
    cur.execute("""
        SELECT subject, lecture_no, status, date
        FROM attendance
        WHERE roll_no=?
        ORDER BY date DESC
    """, (roll,))
    data = cur.fetchall()
    con.close()

    # Import PDF dependencies lazily so app startup still works if policy blocks DLLs.
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
    except Exception as exc:
        return pdf_dependency_error(exc)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    elements.append(Paragraph("My Attendance Report", styles['Title']))
    elements.append(Paragraph(f"Roll No: {roll}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Table data
    table_data = [["Subject", "Lecture No", "Status", "Date"]]
    for row in data:
        table_data.append([row[0], row[1], row[2], row[3]])

    # Create table
    table = Table(table_data, colWidths=[120, 80, 80, 120])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return Response(
        buffer,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=attendance_{roll}.pdf"}
    )
# ================= MARKS =================

def get_grade(marks, max_marks):
    percentage = (marks / max_marks) * 100 if max_marks else 0
    if percentage >= 90:
        return "AA"
    elif percentage >= 80:
        return "A"
    elif percentage >= 70:
        return "B"
    elif percentage >= 60:
        return "C"
    elif percentage >= 50:
        return "D"
    else:
        return "F"


def get_letter_grade(percentage):
    if percentage >= 90:
        return "A+"
    elif percentage >= 80:
        return "A"
    elif percentage >= 70:
        return "B"
    elif percentage >= 60:
        return "C"
    elif percentage >= 50:
        return "D"
    return "F"


def build_student_analysis_data(cur, roll):
    cur.execute("SELECT name, semester, username FROM students WHERE roll_no=?", (roll,))
    student_row = cur.fetchone()
    if not student_row:
        return None

    name, semester, username = student_row

    cur.execute("SELECT subject, type, marks, max_marks FROM marks WHERE roll_no=? ORDER BY subject, type", (roll,))
    marks_data = cur.fetchall()

    cur.execute("SELECT subject, lecture_no, status, date FROM attendance WHERE roll_no=? ORDER BY date DESC", (roll,))
    attendance_data = cur.fetchall()

    subject_totals = {}
    total_obtained = 0
    total_max = 0

    for subject, type_, marks, max_marks in marks_data:
        if subject not in subject_totals:
            subject_totals[subject] = {"obtained": 0, "max": 0}
        subject_totals[subject]["obtained"] += marks
        subject_totals[subject]["max"] += max_marks
        total_obtained += marks
        total_max += max_marks

    cur.execute("""
        SELECT subject, AVG(subject_percentage)
        FROM (
            SELECT roll_no, subject, (SUM(marks) * 100.0 / SUM(max_marks)) AS subject_percentage
            FROM marks
            GROUP BY roll_no, subject
        ) AS subject_stats
        GROUP BY subject
        ORDER BY subject
    """)
    class_avg_rows = cur.fetchall()
    class_average_map = {subject: round(avg_percentage, 2) if avg_percentage is not None else 0 for subject, avg_percentage in class_avg_rows}

    subject_rows = []
    for subject, values in subject_totals.items():
        obtained = values["obtained"]
        maximum = values["max"]
        percentage = round((obtained / maximum) * 100, 2) if maximum else 0
        class_average = class_average_map.get(subject, 0)
        subject_rows.append({
            "subject": subject,
            "obtained": obtained,
            "max": maximum,
            "percentage": percentage,
            "class_average": class_average,
            "status": "Pass" if percentage >= 50 else "Fail",
        })

    subject_rows.sort(key=lambda item: item["subject"])

    subject_labels = [row["subject"] for row in subject_rows]
    subject_percentages = [row["percentage"] for row in subject_rows]
    class_average_percentages = [row["class_average"] for row in subject_rows]

    attendance_subject_totals = {}
    present_count = 0
    absent_count = 0
    for subject, lecture_no, status, date in attendance_data:
        if subject not in attendance_subject_totals:
            attendance_subject_totals[subject] = {"present": 0, "total": 0}
        attendance_subject_totals[subject]["total"] += 1
        if status.lower() == "present":
            attendance_subject_totals[subject]["present"] += 1
            present_count += 1
        else:
            absent_count += 1

    attendance_labels = list(attendance_subject_totals.keys())
    attendance_percentages = [
        round((values["present"] / values["total"]) * 100, 2) if values["total"] else 0
        for values in attendance_subject_totals.values()
    ]

    overall_percentage = (total_obtained / total_max) * 100 if total_max else 0
    grade = get_letter_grade(overall_percentage)
    grade_points = {"A+": 10, "A": 9, "B": 8, "C": 7, "D": 6, "F": 0}
    sgpa = grade_points[grade]
    attendance_rate = round((present_count / len(attendance_data)) * 100, 2) if attendance_data else 0

    return {
        "student": {"name": name, "roll": roll, "semester": semester, "username": username},
        "marks_data": marks_data,
        "attendance_data": attendance_data,
        "subject_rows": subject_rows,
        "total_obtained": total_obtained,
        "total_max": total_max,
        "overall_percentage": round(overall_percentage, 2),
        "grade": grade,
        "sgpa": sgpa,
        "attendance_rate": attendance_rate,
        "present_count": present_count,
        "absent_count": absent_count,
        "subject_labels": subject_labels,
        "subject_percentages": subject_percentages,
        "class_average_percentages": class_average_percentages,
        "attendance_labels": attendance_labels,
        "attendance_percentages": attendance_percentages,
    }

@app.route("/add_marks", methods=["GET", "POST"])
def add_marks():
    if not role_required("teacher"):
        return redirect("/teacher/login")

    valid_semesters = {"1", "2", "3", "4", "5", "6"}

    def semester_filter_values(semester_value):
        sem = semester_value.strip()
        return (sem.lower(), f"sem {sem}".lower())
    selected_semester = request.values.get("semester", "1").strip()
    if selected_semester not in valid_semesters:
        selected_semester = "1"

    success_message = None
    error_message = None

    con = db()
    cur = con.cursor()

    cur.execute("SELECT subject FROM teachers WHERE username=?", (session.get("user"),))
    teacher_row = cur.fetchone()
    default_subject = teacher_row[0].strip() if teacher_row and teacher_row[0] else ""

    if request.method == "POST":
        roll = request.form.get("roll", "").strip()
        subject = request.form.get("subject", "").strip() or default_subject
        selected_semester = request.form.get("semester", selected_semester).strip()
        if selected_semester not in valid_semesters:
            selected_semester = "1"

        assessments = [
            ("Unit Test 1", request.form.get("ut1_marks", "").strip(), request.form.get("ut1_max", "").strip()),
            ("Unit Test 2", request.form.get("ut2_marks", "").strip(), request.form.get("ut2_max", "").strip()),
            ("Final Exam", request.form.get("final_marks", "").strip(), request.form.get("final_max", "").strip()),
        ]

        if not roll or not subject:
            error_message = "Roll number and subject are required."
        else:
            sem_plain, sem_prefixed = semester_filter_values(selected_semester)
            cur.execute(
                """
                SELECT 1
                FROM students
                WHERE roll_no=?
                  AND LOWER(TRIM(semester)) IN (?, ?)
                """,
                (roll, sem_plain, sem_prefixed),
            )
            if not cur.fetchone():
                error_message = "Selected student does not belong to this semester."
            else:
                rows_to_insert = []
                try:
                    for exam_type, marks_str, max_str in assessments:
                        if not marks_str or not max_str:
                            raise ValueError("All marks and max marks fields are required.")

                        marks_val = int(marks_str)
                        max_val = int(max_str)

                        if marks_val < 0 or max_val <= 0:
                            raise ValueError("Marks must be non-negative and max marks must be greater than 0.")
                        if marks_val > max_val:
                            raise ValueError("Obtained marks cannot be greater than max marks.")

                        rows_to_insert.append((roll, subject, exam_type, marks_val, max_val))
                except ValueError as exc:
                    error_message = str(exc)

                if not error_message:
                    cur.executemany(
                        """
                        INSERT INTO marks (roll_no, subject, type, marks, max_marks)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        rows_to_insert,
                    )
                    con.commit()
                    success_message = f"Marks saved for roll number {roll}."

    sem_plain, sem_prefixed = semester_filter_values(selected_semester)
    cur.execute(
        """
        SELECT roll_no, name, semester
        FROM students
        WHERE LOWER(TRIM(semester)) IN (?, ?)
        ORDER BY roll_no
        """,
        (sem_plain, sem_prefixed),
    )
    students = cur.fetchall()
    con.close()

    return render_template(
        "add_marks.html",
        students=students,
        semesters=["1", "2", "3", "4", "5", "6"],
        selected_semester=selected_semester,
        success_message=success_message,
        error_message=error_message,
        default_subject=default_subject,
    )

@app.route("/view_marks")
def view_marks():
    if not role_required("student"):
        return redirect("/student/login")

    con = db()
    cur = con.cursor()
    cur.execute("SELECT roll_no, name FROM students WHERE username=?", (session["user"],))
    student = cur.fetchone()

    if not student:
        con.close()
        return "Student not found"

    roll, name = student
    cur.execute("SELECT subject, type, marks, max_marks FROM marks WHERE roll_no=?", (roll,))
    data = cur.fetchall()
    con.close()

    total_obtained = sum([row[2] for row in data])
    total_max = sum([row[3] for row in data])
    percentage = (total_obtained / total_max) * 100 if total_max else 0

    if percentage >= 90:
        grade = "A+"
    elif percentage >= 80:
        grade = "A"
    elif percentage >= 70:
        grade = "B"
    elif percentage >= 60:
        grade = "C"
    elif percentage >= 50:
        grade = "D"
    else:
        grade = "F"

    grade_points = {"A+": 10, "A": 9, "B": 8, "C": 7, "D": 6, "F": 0}
    sgpa = grade_points[grade]

    return render_template("view_marks.html",
                           name=name,
                           roll=roll,
                           data=data,
                           total_obtained=total_obtained,
                           total_max=total_max,
                           percentage=percentage,
                           grade=grade,
                           sgpa=sgpa)


@app.route("/student/analysis")
def student_analysis():
    if not role_required("student"):
        return redirect("/student/login")

    con = db()
    cur = con.cursor()

    cur.execute("SELECT roll_no FROM students WHERE username=?", (session["user"],))
    roll_row = cur.fetchone()
    if not roll_row:
        con.close()
        return "Student not found"

    analysis = build_student_analysis_data(cur, roll_row[0])
    con.close()

    if not analysis:
        return "Student not found"


    return render_template(
        "student_analysis.html",
        student=analysis["student"],
        marks_data=analysis["marks_data"],
        attendance_data=analysis["attendance_data"],
        subject_rows=analysis["subject_rows"],
        total_obtained=analysis["total_obtained"],
        total_max=analysis["total_max"],
        overall_percentage=analysis["overall_percentage"],
        grade=analysis["grade"],
        sgpa=analysis["sgpa"],
        attendance_rate=analysis["attendance_rate"],
        present_count=analysis["present_count"],
        absent_count=analysis["absent_count"],
        subject_labels=analysis["subject_labels"],
        subject_percentages=analysis["subject_percentages"],
        class_average_percentages=analysis["class_average_percentages"],
        attendance_labels=analysis["attendance_labels"],
        attendance_percentages=analysis["attendance_percentages"],
    )


@app.route("/download_student_analysis_pdf")
def download_student_analysis_pdf():
    if not role_required("student"):
        return redirect("/student/login")

    con = db()
    cur = con.cursor()
    cur.execute("SELECT roll_no FROM students WHERE username=?", (session["user"],))
    roll_row = cur.fetchone()
    if not roll_row:
        con.close()
        return "Student not found"

    analysis = build_student_analysis_data(cur, roll_row[0])
    con.close()

    if not analysis:
        return "Student not found"

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as exc:
        return pdf_dependency_error(exc)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setTitle("Student Analysis Report")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, height - 50, "Student Analysis Report")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, height - 75, f"Name: {analysis['student']['name']}")
    pdf.drawString(40, height - 92, f"Roll No: {analysis['student']['roll']}")
    pdf.drawString(40, height - 109, f"Semester: {analysis['student']['semester']}")
    pdf.drawString(40, height - 126, f"Overall Marks: {analysis['overall_percentage']}% | Grade: {analysis['grade']} | SGPA: {analysis['sgpa']}")
    pdf.drawString(40, height - 143, f"Attendance Rate: {analysis['attendance_rate']}%")

    y = height - 175
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, "Subject Comparison")
    y -= 18

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Subject")
    pdf.drawString(170, y, "Your %")
    pdf.drawString(240, y, "Class Avg %")
    pdf.drawString(340, y, "Status")
    y -= 14
    pdf.setFont("Helvetica", 10)

    for row in analysis["subject_rows"]:
        if y < 70:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y, str(row["subject"]))
        pdf.drawString(170, y, f"{row['percentage']}%")
        pdf.drawString(240, y, f"{row['class_average']}%")
        pdf.drawString(340, y, row["status"])
        y -= 16

    y -= 10
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, "Attendance Summary")
    y -= 18
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, y, f"Present Lectures: {analysis['present_count']}")
    y -= 14
    pdf.drawString(40, y, f"Absent Lectures: {analysis['absent_count']}")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"student_analysis_{analysis['student']['roll']}.pdf",
        mimetype="application/pdf",
    )

@app.route("/download_marksheet")
def download_marksheet():
    if not role_required("student"):
        return redirect("/student/login")

    con = db()
    cur = con.cursor()
    cur.execute("SELECT roll_no, name FROM students WHERE username=?", (session["user"],))
    student = cur.fetchone()

    if not student:
        con.close()
        return "Student not found"

    roll, name = student
    cur.execute("SELECT subject, type, marks, max_marks FROM marks WHERE roll_no=?", (roll,))
    data = cur.fetchall()
    con.close()

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as exc:
        return pdf_dependency_error(exc)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("Marksheet")

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(150, 800, "DEOGIRI COLLAGE CHH.SAMBHAJINAGAR")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 770, f"Name: {name}")
    pdf.drawString(50, 750, f"Roll No: {roll}")
    pdf.drawString(50, 730, f"Year: 2026")

    y = 700
    pdf.drawString(50, y, "Subject")
    pdf.drawString(200, y, "Obtain Marks")
    pdf.drawString(300, y, "Total Marks")
    pdf.drawString(400, y, "Grade")
    y -= 20

    total_obtained = 0
    total_max = 0

    for subject, type_, marks, max_marks in data:
        grade = get_grade(marks, max_marks)
        pdf.drawString(50, y, f"{subject} ({type_})")
        pdf.drawString(200, y, str(marks))
        pdf.drawString(300, y, str(max_marks))
        pdf.drawString(400, y, grade)
        total_obtained += marks
        total_max += max_marks
        y -= 20

    percentage = (total_obtained / total_max) * 100 if total_max else 0
    division = "FIRST" if percentage >= 60 else "SECOND" if percentage >= 50 else "THIRD"

    pdf.drawString(50, y - 20, f"Total Marks: {total_obtained}/{total_max}")
    pdf.drawString(50, y - 40, f"Percentage: {percentage:.2f}%")
    pdf.drawString(50, y - 60, f"Division: {division}")
    pdf.drawString(400, y - 100, "Signature")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="marksheet.pdf", mimetype="application/pdf")

@app.route("/teacher/view_marks")
def teacher_view_marks():
    if not role_required("teacher"):
        return redirect("/teacher/login")

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT s.roll_no, s.name, m.subject, m.type, m.marks, m.max_marks
        FROM students s
        JOIN marks m ON s.roll_no = m.roll_no
        ORDER BY s.roll_no, m.subject, m.type
    """)
    data = cur.fetchall()
    con.close()

    passing_marks = 12
    results = []

    for row in data:
        roll, name, subject, type_, marks, max_marks = row
        status = "Pass" if marks >= passing_marks else "Fail"
        results.append((roll, name, subject, type_, marks, max_marks, status))

    return render_template("teacher_view_marks.html", results=results)
#====================upload==================

@app.route('/upload_pdf', methods=['GET', 'POST'])
def upload_pdf():
    if request.method == 'POST':
        # file upload logic here
        return "File Uploaded Successfully"
    return render_template('downloads.html')


@app.route("/download_attendance")
def download_attendance():
    if "role" not in session or session["role"] != "student":
        return redirect("/student/login")

    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT roll_no FROM students WHERE username=?",
        (session["user"],)
    )
    roll_row = cur.fetchone()
    if not roll_row:
        con.close()
        return "Student not found"
    roll = roll_row[0]

    cur.execute("""
        SELECT subject, lecture_no, status, date
        FROM attendance WHERE roll_no=?
    """, (roll,))

    data = cur.fetchall()
    con.close()

    def generate():
        yield "Subject,Lecture,Status,Date\n"
        for row in data:
            yield f"{row[0]},{row[1]},{row[2]},{row[3]}\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=attendance.csv"}
    )

# ================= LOGOUT =================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
