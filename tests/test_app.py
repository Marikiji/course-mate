import pytest

import app as app_module


@pytest.fixture()
def client(tmp_path):
    app_module.app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "test.db"),
    )
    with app_module.app.app_context():
        app_module.init_db()
    with app_module.app.test_client() as test_client:
        yield test_client


def add_course(
    client,
    name="离散数学",
    credits="3",
    day="周一",
    start="08:00",
    end="09:40",
    score="",
):
    return client.post(
        "/add",
        data={
            "name": name,
            "credits": credits,
            "day": day,
            "start": start,
            "end": end,
            "location": "A-301",
            "category": "必修",
            "score": score,
        },
        follow_redirects=True,
    )


def test_add_course(client):
    response = add_course(client)
    assert response.status_code == 200
    assert "离散数学" in response.get_data(as_text=True)


def test_conflict_is_blocked(client):
    add_course(client, name="课程 A", start="08:00", end="09:40")
    response = add_course(client, name="课程 B", start="09:00", end="10:00")
    text = response.get_data(as_text=True)
    assert "时间冲突" in text
    assert "课程 B" in text  # form is rendered again with the attempted values


def test_gpa_calculation(client):
    # 两门课时间错开，否则第二门会被冲突检测拦住
    add_course(client, name="课程 A", credits="3", score="80",
               start="08:00", end="09:40")
    add_course(client, name="课程 B", credits="2", score="90",
               start="10:00", end="11:40")
    response = client.get("/gpa")
    text = response.get_data(as_text=True)
    assert "84.00" in text  # weighted average: (80*3 + 90*2) / 5
    assert "3.40" in text   # GPA: (3.0*3 + 4.0*2) / 5
