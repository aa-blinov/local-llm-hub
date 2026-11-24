"""Cancelling a component job marks it cancelled and stops its work."""
import time

from llm_hub.components import Jobs


def test_cancel_running_job_stops_it(tmp_path, monkeypatch):
    monkeypatch.setattr("llm_hub.components.JOBS_DIR", tmp_path)
    jobs = Jobs()
    started = {}

    def slow(log):
        started["yes"] = True
        for _ in range(100):
            time.sleep(0.02)  # stands in for a long install step
        log("finished unexpectedly")

    job_id = jobs.submit("comp", "install", slow)["job"]
    for _ in range(100):
        if started.get("yes"):
            break
        time.sleep(0.01)
    assert jobs.cancel(job_id)["ok"]
    for _ in range(200):
        if jobs.get(job_id)["state"] != "running":
            break
        time.sleep(0.02)
    job = jobs.get(job_id)
    assert job["state"] == "cancelled"
    assert "finished unexpectedly" not in Jobs.tail(job)


def test_cancel_without_running_job_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr("llm_hub.components.JOBS_DIR", tmp_path)
    assert Jobs().cancel("nope")["ok"] is False
