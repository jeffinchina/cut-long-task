"""Pure quota decision from a fresh tool snapshot; no network or scheduler writes."""
import argparse
import datetime as dt
from decimal import Decimal
import json
import math
from pathlib import Path


def decide(raw, observed_at, now, reserve='0.2', limit_id='codex', delay_minutes=7):
    def result(decision, reason, **fields):
        return {'decision': decision, 'reason': reason, 'observed_at': observed_at.isoformat(),
                'limit_id': limit_id, 'T': float(Decimal(str(reserve))), **fields}
    threshold = Decimal(str(reserve))
    if isinstance(delay_minutes, bool) or not isinstance(delay_minutes, int) or delay_minutes < 0:
        raise ValueError('delay_minutes must be a nonnegative integer')
    if not threshold.is_finite() or not 0 <= threshold <= 1:
        raise ValueError('reserve must be in [0,1]')
    if observed_at.tzinfo is None or now.tzinfo is None:
        raise ValueError('timezone-aware observations required')
    age = (now - observed_at).total_seconds()
    if age < -5 or age > 180:
        return result('retry_once', 'unverified_stale_observation')
    if isinstance(raw, dict) and isinstance(raw.get('content'), list):
        texts = [x.get('text', '') for x in raw['content'] if x.get('type') == 'text']
        try:
            raw = json.loads(texts[0]) if len(texts) == 1 else {}
        except (ValueError, TypeError):
            raw = {}
    if not isinstance(raw, dict):
        return result('retry_once', 'unverified_payload')
    if raw.get('ordinaryUsageAllowed') is False:
        return result('pause', 'hard_limit')
    if raw.get('ordinaryUsageAllowed') is not True:
        return result('retry_once', 'unverified_usage_permission')
    buckets = raw.get('rateLimitsByLimitId')
    bucket = buckets.get(limit_id) if isinstance(buckets, dict) and buckets else raw.get('rateLimits')
    if not isinstance(bucket, dict) or bucket.get('limitId') != limit_id:
        return result('retry_once', 'unverified_bucket')
    windows = [x for x in bucket.values() if isinstance(x, dict) and x.get('windowDurationMins') in (300, 10080)]
    five = []
    for window in windows:
        used = window.get('usedPercent')
        valid = not isinstance(used, bool) and isinstance(used, (int, float)) and math.isfinite(used)
        if not valid:
            return result('retry_once', 'unverified_window')
        if window['windowDurationMins'] == 10080:
            if used >= 100:
                return result('pause', 'hard_limit_weekly')
            continue
        reset = window.get('resetsAt')
        if isinstance(reset, bool) or not isinstance(reset, (int, float)) or not math.isfinite(reset):
            return result('retry_once', 'unverified_reset')
        if reset <= now.timestamp():
            return result('retry_once', 'unverified_expired_reset')
        remaining = (Decimal(100) - max(Decimal(0), min(Decimal(100), Decimal(str(used))))) / 100
        five.append((remaining, used, reset))
    if not five:
        return result('retry_once', 'unverified_five_hour_window')
    remaining, used, _ = min(five)
    blocking = [x for x in five if x[0] <= threshold]
    reset = max(x[2] for x in blocking) if blocking else min(x[2] for x in five)
    next_check = dt.datetime.fromtimestamp(reset + delay_minutes * 60, dt.timezone.utc)
    return result('resume' if remaining > threshold else 'pause',
                  'resume' if remaining > threshold else 'reserve_threshold',
                  R=float(remaining), used_percent=used, window_minutes=300,
                  resetsAt=reset, delay_minutes=delay_minutes,
                  next_check_utc=next_check.isoformat())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--observed-at', required=True)
    parser.add_argument('--reserve', default='0.2')
    parser.add_argument('--limit-id', default='codex')
    parser.add_argument('--delay-minutes', type=int, default=7)
    args = parser.parse_args()
    output = decide(json.loads(args.snapshot.read_text(encoding='utf-8-sig')),
                    dt.datetime.fromisoformat(args.observed_at.replace('Z', '+00:00')),
                    dt.datetime.now(dt.timezone.utc), args.reserve, args.limit_id, args.delay_minutes)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
