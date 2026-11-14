import os
import sqlite3
from datetime import datetime

from flask import Flask, flash, g, redirect, render_template, request, url_for

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.environ.get("DATABASE", os.path.join(BASE_DIR, "course.db"))

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    DATABASE=DATABASE,
)

DAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
CATEGORIES = ["必修", "限选", "选修", "通识"]

LETTER_SCORES = {
    "A": 95, "A-": 87, "B+": 83, "B": 79, "B-": 76,
    "C+": 73, "C": 69, "C-": 66, "D+": 63, "D": 60, "F": 30,
}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            credits REAL NOT NULL,
            day TEXT NOT NULL,
            start TEXT NOT NULL,
            end TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '必修',
            score TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.commit()


def parse_score(raw):
    """把 '85' 或 'A-' 转成百分制分数；空值返回 None。"""
    raw = (raw or "").strip().upper()
    if not raw:
        return None
    if raw in LETTER_SCORES:
        return float(LETTER_SCORES[raw])
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if 0 <= value <= 100 else None


def score_to_gpa(score):
    """北交大 4.0 绩点换算（按手册的分段）。"""
    if score is None:
        return None
    if score >= 90:
        return 4.0
    if score >= 85:
        return 3.7
    if score >= 81:
        return 3.3
    if score >= 78:
        return 3.0
    if score >= 75:
        return 2.7
    if score >= 71:
        return 2.3
    if score >= 68:
        return 2.0
    if score >= 65:
        return 1.7
    if score >= 61:
        return 1.3
    if score >= 60:
        return 1.0
    return 0.0


def read_form():
    return {
        "name": request.form.get("name", "").strip(),
        "credits": request.form.get("credits", "").strip(),
        "day": request.form.get("day", "").strip(),
        "start": request.form.get("start", "").strip(),
        "end": request.form.get("end", "").strip(),
        "location": request.form.get("location", "").strip(),
        "category": request.form.get("category", "必修").strip(),
        "score": request.form.get("score", "").strip(),
    }


def validate_course(data):
    errors = []
    if not data["name"]:
        errors.append("课程名不能为空。")
    try:
        credits = float(data["credits"])
        if credits <= 0:
            raise ValueError
    except ValueError:
        errors.append("学分必须是大于 0 的数字。")
    if data["day"] not in DAYS:
        errors.append("请选择星期。")
    try:
        start = datetime.strptime(data["start"], "%H:%M")
        end = datetime.strptime(data["end"], "%H:%M")
        if start >= end:
            errors.append("结束时间必须晚于开始时间。")
    except ValueError:
        errors.append("时间格式应为 HH:MM。")
    if data["score"] and parse_score(data["score"]) is None:
        errors.append("成绩请填 0–100 或 A/A-/B+…/F，留空也可以。")
    return errors


def find_conflicts(day, start, end, exclude_id=None):
    """返回与给定时间段重叠的课程。字符串 HH:MM 可以直接比较大小。"""
    query = "SELECT * FROM courses WHERE day = ? AND start < ? AND end > ?"
    params = [day, end, start]
    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)
    return get_db().execute(query, params).fetchall()


def form_values(course=None):
    if course is None:
        return {
            "name": "", "credits": "", "day": "周一", "start": "",
            "end": "", "location": "", "category": "必修", "score": "",
        }
    return {key: course[key] for key in (
        "name", "credits", "day", "start", "end", "location", "category", "score"
    )}


@app.route("/")
def index():
    db = get_db()
    rows = db.execute("SELECT * FROM courses").fetchall()
    rows = sorted(
        rows,
        key=lambda r: (DAYS.index(r["day"]) if r["day"] in DAYS else 99, r["start"]),
    )
    conflict_ids = set()
    for i, first in enumerate(rows):
        for second in rows[i + 1:]:
            if (
                first["day"] == second["day"]
                and first["start"] < second["end"]
                and first["end"] > second["start"]
            ):
                conflict_ids.update([first["id"], second["id"]])
    return render_template(
        "index.html", courses=rows, conflict_ids=conflict_ids, days=DAYS
    )


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        data = read_form()
        errors = validate_course(data)
        if not errors:
            conflicts = find_conflicts(data["day"], data["start"], data["end"])
            if conflicts:
                other = conflicts[0]
                errors.append(
                    f"时间冲突：{other['name']}（{other['start']}–{other['end']}）。"
                )
        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template(
                "form.html", course=None, form=data, days=DAYS, categories=CATEGORIES
            )

        db = get_db()
        db.execute(
            """
            INSERT INTO courses (name, credits, day, start, end, location, category, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"], float(data["credits"]), data["day"], data["start"],
                data["end"], data["location"], data["category"], data["score"],
            ),
        )
        db.commit()
        flash("课程已添加。", "success")
        return redirect(url_for("index"))

    return render_template(
        "form.html", course=None, form=form_values(), days=DAYS, categories=CATEGORIES
    )


@app.route("/course/<int:course_id>/edit", methods=["GET", "POST"])
def edit(course_id):
    db = get_db()
    course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if course is None:
        flash("课程不存在。", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        data = read_form()
        errors = validate_course(data)
        if not errors:
            conflicts = find_conflicts(
                data["day"], data["start"], data["end"], exclude_id=course_id
            )
            if conflicts:
                other = conflicts[0]
                errors.append(
                    f"时间冲突：{other['name']}（{other['start']}–{other['end']}）。"
                )
        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template(
                "form.html", course=course, form=data, days=DAYS, categories=CATEGORIES
            )

        db.execute(
            """
            UPDATE courses
            SET name = ?, credits = ?, day = ?, start = ?, end = ?,
                location = ?, category = ?, score = ?
            WHERE id = ?
            """,
            (
                data["name"], float(data["credits"]), data["day"], data["start"],
                data["end"], data["location"], data["category"], data["score"],
                course_id,
            ),
        )
        db.commit()
        flash("课程已更新。", "success")
        return redirect(url_for("index"))

    return render_template(
        "form.html", course=course, form=form_values(course), days=DAYS,
        categories=CATEGORIES,
    )


@app.route("/course/<int:course_id>/delete", methods=["POST"])
def delete(course_id):
    db = get_db()
    db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    db.commit()
    flash("课程已删除。", "success")
    return redirect(url_for("index"))


@app.route("/gpa")
def gpa():
    db = get_db()
    rows = db.execute("SELECT * FROM courses").fetchall()
    scored = []
    total_credits = 0.0
    weighted_points = 0.0
    gpa_points = 0.0

    for course in rows:
        percent = parse_score(course["score"])
        if percent is None:
            continue
        point = score_to_gpa(percent)
        scored.append({"course": course, "percent": percent, "gpa": point})
        total_credits += course["credits"]
        weighted_points += percent * course["credits"]
        gpa_points += point * course["credits"]

    average = weighted_points / total_credits if total_credits else None
    gpa_value = gpa_points / total_credits if total_credits else None

    target = request.args.get("target", "").strip()
    remaining = request.args.get("remaining", "").strip()
    required = None
    if target and remaining:
        try:
            target_value = float(target)
            remaining_value = float(remaining)
            if remaining_value > 0:
                required = (
                    target_value * (total_credits + remaining_value) - weighted_points
                ) / remaining_value
        except ValueError:
            flash("目标均分和剩余学分都要填数字。", "warning")

    return render_template(
        "gpa.html",
        scored=scored,
        total_credits=total_credits,
        average=average,
        gpa_value=gpa_value,
        required=required,
        target=target,
        remaining=remaining,
    )


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)
