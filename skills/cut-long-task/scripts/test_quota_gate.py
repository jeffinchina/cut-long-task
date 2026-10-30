import copy
import datetime as dt
import unittest
from quota_gate import decide


NOW = dt.datetime(2026, 10, 29, 15, 27, 30, tzinfo=dt.timezone.utc)
RESET = NOW.timestamp() + 18000


def fixture(used):
    return {'ordinaryUsageAllowed': True, 'rateLimitsByLimitId': {
        'codex': {'limitId': 'codex', 'primary': {'usedPercent': used, 'windowDurationMins': 300, 'resetsAt': RESET},
                  'secondary': {'usedPercent': 35, 'windowDurationMins': 10080, 'resetsAt': RESET + 604800}}}}


class QuotaGateTests(unittest.TestCase):
    def test_new_fresh_window_resumes_despite_external_old_pause_record(self):
        self.assertEqual(decide(fixture(1), NOW, NOW)['decision'], 'resume')

    def test_exact_reserve_boundary(self):
        self.assertEqual(decide(fixture(84), NOW, NOW, reserve='0.15')['decision'], 'resume')
        self.assertEqual(decide(fixture(85), NOW, NOW, reserve='0.15')['reason'], 'reserve_threshold')
        self.assertEqual(decide(fixture(90), NOW, NOW, reserve='0.15')['reason'], 'reserve_threshold')

    def test_default_reserve_matches_skill_twenty_percent(self):
        self.assertEqual(decide(fixture(79), NOW, NOW)['decision'], 'resume')
        self.assertEqual(decide(fixture(80), NOW, NOW)['reason'], 'reserve_threshold')
        self.assertEqual(decide(fixture(80), NOW, NOW)['T'], 0.2)

    def test_weekly_hard_limit_is_separate(self):
        raw = fixture(1)
        raw['rateLimitsByLimitId']['codex']['secondary']['usedPercent'] = 100
        self.assertEqual(decide(raw, NOW, NOW)['reason'], 'hard_limit_weekly')

    def test_other_bucket_is_not_current_quota(self):
        raw = fixture(1)
        raw['rateLimitsByLimitId']['review'] = {'limitId': 'review', 'primary': {'usedPercent': 100, 'windowDurationMins': 300}}
        self.assertEqual(decide(raw, NOW, NOW)['decision'], 'resume')

    def test_window_selected_by_duration_not_primary_label(self):
        raw = fixture(1)
        bucket = raw['rateLimitsByLimitId']['codex']
        bucket['primary'], bucket['secondary'] = bucket['secondary'], bucket['primary']
        self.assertEqual(decide(raw, NOW, NOW)['decision'], 'resume')

    def test_missing_or_invalid_observation_does_not_claim_quota_exhausted(self):
        for value in (None, True, float('nan')):
            raw = fixture(value)
            self.assertEqual(decide(raw, NOW, NOW)['decision'], 'retry_once')
        self.assertEqual(decide(fixture(1), NOW - dt.timedelta(minutes=4), NOW)['decision'], 'retry_once')

    def test_expired_reset_is_unverified_not_inferred_recovery(self):
        raw = fixture(90)
        raw['rateLimitsByLimitId']['codex']['primary']['resetsAt'] = NOW.timestamp() - 1
        self.assertEqual(decide(raw, NOW, NOW)['reason'], 'unverified_expired_reset')

    def test_next_check_uses_tool_epoch_plus_seven_minutes(self):
        result = decide(fixture(90), NOW, NOW)
        self.assertEqual(dt.datetime.fromisoformat(result['next_check_utc']).timestamp(), RESET + 420)

    def test_explicit_delay_and_timezone_independent_epoch(self):
        for delay in (0, 5, 10):
            result = decide(fixture(90), NOW, NOW, delay_minutes=delay)
            self.assertEqual(dt.datetime.fromisoformat(result['next_check_utc']).timestamp(), RESET + delay * 60)
        with self.assertRaises(ValueError):
            decide(fixture(90), NOW, NOW, delay_minutes=-1)

    def test_only_blocking_windows_determine_wait(self):
        raw = fixture(90)
        raw['rateLimitsByLimitId']['codex']['another'] = {'usedPercent': 1, 'windowDurationMins': 300, 'resetsAt': RESET + 3600}
        self.assertEqual(decide(raw, NOW, NOW)['resetsAt'], RESET)

    def test_legacy_fallback_only_when_bucket_map_unavailable(self):
        raw = fixture(1)
        raw['rateLimits'] = copy.deepcopy(raw['rateLimitsByLimitId']['codex'])
        raw['rateLimitsByLimitId'] = {'other': {'limitId': 'other'}}
        self.assertEqual(decide(raw, NOW, NOW)['decision'], 'retry_once')
        del raw['rateLimitsByLimitId']
        self.assertEqual(decide(raw, NOW, NOW)['decision'], 'resume')


if __name__ == '__main__':
    unittest.main()
