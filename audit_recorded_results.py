#!/usr/bin/env python3
"""Audit exported answer flags against checked-in leaderboards; no model calls.

This verifies snapshot arithmetic, not the original model responses or grading.
"""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def audit():
    source = (ROOT / 'scoring-data.js').read_bytes()
    text = source.decode().strip()
    prefix = 'window.SCORING_DATA = '
    assert text.startswith(prefix) and text.endswith(';'), 'Unexpected snapshot format'
    data = json.loads(text[len(prefix):-1])
    clips = data['clips']
    assert len({c['id'] for c in clips}) == len(clips) == 87
    questions = [q for c in clips for q in c['questions']]
    assert len(questions) == 261
    excluded = [(c['id'], i) for c in clips for i, q in enumerate(c['questions']) if q['excluded']]
    assert excluded == [('3_1_1_86', 2)]
    scored = [q for q in questions if not q['excluded']]
    assert len(scored) == data['expected'] == 260
    labels = Counter(q['gold'] for q in scored if q['kind'] == 'judge')
    assert labels == {'yes': 172, 'no': 2}
    assert sum(q['kind'] == 'reason' for q in scored) == 86
    print('87 clips; 261 source questions; 260 scored (174 judgment + 86 reason).')
    print('Judgment gold: 172 yes / 174 = 98.9%; two questions per clip.')
    print('Snapshot SHA256:', hashlib.sha256(source).hexdigest())
    for variant, board in [('official', 'LEADERBOARD.md'), ('reword', 'LEADERBOARD-reword.md')]:
        completed = []
        for run in (r for r in data['runs'] if r['prompt'] == variant):
            assert len(run['answers']) == len(clips), run['file']
            entries = []
            for clip, answers in zip(clips, run['answers']):
                assert len(answers) == len(clip['questions']), run['file']
                entries.extend((q, a) for q, a in zip(clip['questions'], answers) if not q['excluded'])
            count = sum(bool(a['pred'].strip()) for q, a in entries)
            assert count == run['completed'], run['file']
            if count != 260:
                print(f"Incomplete: {run['file']} ({count}/260); excluded from ranking")
                continue
            judge = sum(a['ok'] for q, a in entries if q['kind'] == 'judge') / 174
            reason = sum(a['ok'] for q, a in entries if q['kind'] == 'reason') / 86
            obey = sum(a['obey'] for q, a in entries) / 260
            score = 100 * (0.7 * judge + 0.1 * reason + 0.2 * obey)
            completed.append((score, judge, reason, obey, run))
        completed.sort(key=lambda r: r[0], reverse=True)
        rows = [line.split('|')[1:-1] for line in (ROOT / board).read_text().splitlines()
                if line.startswith('| ') and line.split('|')[1].strip().isdigit()]
        assert len(rows) == len(completed), board
        for row, (score, judge, reason, obey, run) in zip(rows, completed):
            actual = [v.strip() for v in row[4:8]]
            expected = [f'{score:.2f}', f'{judge:.1%}', f'{reason:.1%}', f'{obey:.1%}']
            assert actual == expected, (board, run['file'], actual, expected)
        print(f'{board}: {len(completed)} completed runs across {len({r[4]["model"] for r in completed})} model labels; all score columns match.')
    costs = json.loads((ROOT / 'benchmark_costs.json').read_text(), parse_float=Decimal)
    for model in costs['models']:
        assert sum(c['amount_usd'] for c in model['charges']) == model['total_usd'], model['model']
    assert sum(m['total_usd'] for m in costs['models']) == costs['known_total_usd']
    print(f"Billing arithmetic: ${costs['known_total_usd']} (account/endpoint totals; allocation caveats apply).")


if __name__ == '__main__':
    audit()
