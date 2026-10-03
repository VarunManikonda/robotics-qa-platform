import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.sqlite3")))


def post(client, **kw):
    body = {"project": "cobot_qa", "name": "run", "status": "pass"}
    body.update(kw)
    r = client.post("/runs", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_create_and_get(client):
    run = post(client, name="fk_check", metric=0.5, payload={"a": 1})
    got = client.get(f"/runs/{run['id']}").json()
    assert got["name"] == "fk_check"
    assert got["payload"] == {"a": 1}
    assert got["created_at"]


def test_get_missing_is_404(client):
    assert client.get("/runs/999").status_code == 404


def test_rejects_bad_status_and_empty_project(client):
    assert client.post("/runs", json={"project": "x", "name": "n", "status": "bad"}).status_code == 422
    assert client.post("/runs", json={"project": "", "name": "n", "status": "pass"}).status_code == 422


def test_progressive_filters_combine(client):
    post(client, project="cobot_qa", name="reach_a", status="pass", metric=1.0)
    post(client, project="cobot_qa", name="reach_b", status="fail", metric=9.0)
    post(client, project="amr_health", name="imu", status="fail", metric=5.0)
    post(client, project="amr_health", name="odom", status="warn", metric=2.0)

    def names(**params):
        return sorted(i["name"] for i in client.get("/runs", params=params).json()["items"])

    assert names() == ["imu", "odom", "reach_a", "reach_b"]
    assert names(project="cobot_qa") == ["reach_a", "reach_b"]
    assert names(project="cobot_qa", status="fail") == ["reach_b"]
    assert names(status="fail") == ["imu", "reach_b"]
    assert names(q="reach") == ["reach_a", "reach_b"]
    assert names(min_metric=4, max_metric=6) == ["imu"]
    assert names(project="amr_health", q="odom") == ["odom"]
    assert names(project="amr_health", status="fail", q="reach") == []


def test_text_search_treats_wildcards_literally(client):
    post(client, name="abc", message="100% done")
    post(client, name="abd", message="fully done")
    hits = client.get("/runs", params={"q": "100%"}).json()["items"]
    assert [h["name"] for h in hits] == ["abc"]
    assert client.get("/runs", params={"q": "_"}).json()["items"] == []


def test_keyset_pagination_walks_everything_once(client):
    for i in range(25):
        post(client, name=f"r{i}")
    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": 10}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/runs", params=params).json()
        seen += [i["id"] for i in page["items"]]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    assert seen == sorted(seen, reverse=True)
    assert len(seen) == len(set(seen)) == 25


def test_exact_page_boundary_has_no_phantom_next_page(client):
    for i in range(10):
        post(client, name=f"r{i}")
    page = client.get("/runs", params={"limit": 10}).json()
    assert len(page["items"]) == 10
    assert page["next_cursor"] is None


def test_limit_validation(client):
    assert client.get("/runs", params={"limit": 0}).status_code == 422
    assert client.get("/runs", params={"limit": 201}).status_code == 422


def test_stats(client):
    post(client, project="cobot_qa", status="pass")
    post(client, project="cobot_qa", status="fail")
    post(client, project="amr_health", status="warn")
    s = client.get("/stats").json()
    assert s["cobot_qa"] == {"pass": 1, "fail": 1, "warn": 0}
    assert s["amr_health"] == {"pass": 0, "fail": 0, "warn": 1}


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Robotics QA Dashboard" in r.text


def test_summary_endpoint_reflects_recent_runs(client):
    post(client, name="part:block_red_1", status="pass", metric=4.0, payload={"cycle_time_s": 4.0})
    post(client, name="part:block_blue_1", status="fail", metric=4.2, payload={"cycle_time_s": 4.2})
    s = client.get("/summary").json()
    assert s["status"] == "green" and s["totals"]["parts"] == 2 and s["totals"]["defects"] == 1
    post(client, project="amr_health", name="velocity_tracking", status="fail")
    assert client.get("/summary").json()["status"] == "red"


def test_summary_window_is_validated(client):
    post(client, project="amr_health", name="velocity_tracking", status="fail")
    # the run was just created so a 1 hour window sees it; a 0 hour window is rejected
    assert client.get("/summary", params={"hours": 1}).json()["status"] == "red"
    assert client.get("/summary", params={"hours": 0}).status_code == 422


def test_problems_filter_hides_rejected_parts_but_keeps_real_issues(client):
    post(client, name="part:a", status="pass")
    post(client, name="part:b", status="fail")          # correctly rejected: normal
    post(client, name="part:c", status="warn")           # could not move: a problem
    post(client, project="amr_health", name="velocity_tracking", status="fail")
    items = client.get("/runs", params={"problems": "true"}).json()["items"]
    assert sorted(i["name"] for i in items) == ["part:c", "velocity_tracking"]


def test_index_is_plain_language(client):
    html = client.get("/").text
    assert "Robot cell status" in html and "What needs your attention" in html


def test_summary_ignores_runs_older_than_the_window(tmp_path):
    import sqlite3

    path = str(tmp_path / "old.sqlite3")
    c = TestClient(create_app(path))
    post(c, project="amr_health", name="velocity_tracking", status="fail")
    db = sqlite3.connect(path)
    db.execute("UPDATE runs SET created_at='2020-01-01T00:00:00.000Z'")
    db.commit()
    db.close()
    assert c.get("/summary", params={"hours": 24}).json()["status"] == "idle"


def test_index_names_both_robots_and_has_a_robot_filter(client):
    html = client.get("/").text
    assert "Robot arm" in html and "Mobile robot" in html and 'id="robot"' in html
