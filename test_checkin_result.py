import unittest
from unittest.mock import Mock, patch
import checkin

CHALLENGE = "Cloudflare verification failed. Nothing was recorded — please retry."

class CheckinResultTests(unittest.TestCase):
    def test_explicit_challenge_is_not_success_even_if_code_is_zero(self):
        self.assertEqual(checkin.classify_checkin(0, CHALLENGE), "manual")

    def test_explicit_challenge_is_not_repeat_even_if_code_is_one(self):
        self.assertEqual(checkin.classify_checkin(1, CHALLENGE), "manual")

    def test_checkin_result_is_actionable_and_has_no_points(self):
        with patch.object(checkin, "checkin_request", return_value={"code": 4, "message": CHALLENGE}), patch.object(checkin, "api_get", return_value={}):
            result = checkin.checkin_account(Mock(), "fixture", 1)
        self.assertEqual(result["result"], "manual")
        self.assertIn("手动", result["status"])

    def test_repeat_and_new_credit_stay_distinct(self):
        self.assertEqual(checkin.classify_checkin(1, "已签到"), "repeat")
        self.assertEqual(checkin.classify_checkin(0, "got 5 points"), "ok")

    def test_generic_failure_is_not_a_cloudflare_verdict(self):
        self.assertEqual(checkin.classify_checkin(4, "Service unavailable"), "fail")

    def test_all_manual_run_has_nonzero_exit_and_separate_count(self):
        account = {"index": 1, "email": "hidden", "status": "待手动验证", "total_points": "-", "remaining_days": "-", "result": "manual"}
        with patch.dict(checkin.os.environ, {"COOKIES": "gld:sess=fixture; gld:sess.sig=fixture"}, clear=True), patch.object(checkin, "validate_cookie", return_value=(True, "")), patch.object(checkin, "checkin_account", return_value=account), patch.object(checkin, "push_all", return_value=(0, 0)) as push:
            self.assertEqual(checkin.main(), 1)
        self.assertIn("待手动验证 1", push.call_args.args[0])
        self.assertIn("新增签到 0", push.call_args.args[0])

    def test_actions_summary_links_to_manual_checkin(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        account = {"index": 1, "email": "hidden", "status": "待手动验证", "total_points": "-", "remaining_days": "-", "result": "manual"}
        with TemporaryDirectory() as work:
            summary = Path(work) / "summary.md"
            env = {"COOKIES": "gld:sess=fixture; gld:sess.sig=fixture", "GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": str(summary)}
            with patch.dict(checkin.os.environ, env, clear=True), patch.object(checkin, "validate_cookie", return_value=(True, "")), patch.object(checkin, "checkin_account", return_value=account), patch.object(checkin, "push_all", return_value=(0, 0)), patch("builtins.print") as emit:
                self.assertEqual(checkin.main(), 1)
            self.assertIn("::warning title=GLaDOS 需要手动签到::", emit.call_args.args[0])
            self.assertIn("https://glados.cloud/console/checkin", summary.read_text())
            self.assertNotIn("fixture", summary.read_text())
