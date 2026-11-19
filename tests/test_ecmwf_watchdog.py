"""Testes do watchdog ECMWF — sem rede e sem alterar Actions."""
import unittest
from datetime import datetime, timedelta, timezone
from scripts.ecmwf_watchdog import evaluate, latest_window

UTC = timezone.utc


def dt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def run(when, id=1, event="schedule", branch="main", status="in_progress"):
    return dict(created_at=when, id=id, event=event, head_branch=branch,
                status=status, html_url=f"https://github.com/example/actions/runs/{id}")


class WatchdogTests(unittest.TestCase):
    def test_window_14_40_is_06(self):
        x,y=latest_window(dt("2026-11-19T16:12:00Z"))
        self.assertEqual(x,dt("2026-11-19T14:40:00Z"))
        self.assertEqual(y,dt("2026-11-19T06:00:00Z"))

    def test_window_02_40_is_previous_day_18(self):
        x,y=latest_window(dt("2026-11-19T04:11:00Z"))
        self.assertEqual(y,dt("2026-11-18T18:00:00Z"))

    def test_window_09_45(self):
        x,y=latest_window(dt("2026-11-19T11:20:00Z"))
        self.assertEqual(y,dt("2026-11-19T00:00:00Z"))

    def test_window_21_45(self):
        x,y=latest_window(dt("2026-11-19T23:19:00Z"))
        self.assertEqual(y,dt("2026-11-19T12:00:00Z"))

    def test_before_grace_no_recovery(self):
        self.assertEqual(evaluate(dt("2026-11-19T15:20:00Z"),[])[0],"outside")

    def test_recover_missing(self):
        state,_,cycle,_=evaluate(dt("2026-11-19T16:15:00Z"),[])
        self.assertEqual((state,cycle),("recover","2026-11-19T06:00:00Z"))

    def test_delayed_scheduled_run_prevents_duplicate(self):
        existing=[run("2026-11-19T15:33:21Z",id=44556105784)]
        state,_,_,match=evaluate(dt("2026-11-19T16:15:00Z"),existing)
        self.assertEqual((state,match["id"]),("covered",44556105784))

    def test_pending_manual_recovery_prevents_duplicate(self):
        state,_,_,_=evaluate(dt("2026-11-19T16:15:00Z"),
                              [run("2026-11-19T16:12:00Z",event="workflow_dispatch",status="queued")])
        self.assertEqual(state,"covered")

    def test_different_branch_ignored(self):
        state,_,_,_=evaluate(dt("2026-11-19T16:15:00Z"),
                              [run("2026-11-19T15:15:00Z",branch="dev")])
        self.assertEqual(state,"recover")

    def test_old_runs_do_not_satisfy_new_cycle(self):
        state,_,_,_=evaluate(dt("2026-11-19T16:15:00Z"),
                              [run("2026-11-19T11:19:22Z")])
        self.assertEqual(state,"recover")

    def test_outside_recovery_window_never_dispatch(self):
        self.assertEqual(evaluate(dt("2026-11-19T20:14:00Z"),[])[0],"outside")


if __name__ == "__main__":
    unittest.main()
