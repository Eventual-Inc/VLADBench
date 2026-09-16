# Original VLADBench scoring sources (preserved for provenance)

The three released files in this directory are byte-for-byte Git objects from
[Depth2World/VLADBench commit b0dde78ab7d4a7c0a9118a2cb519adaef1118f41](https://github.com/Depth2World/VLADBench/tree/b0dde78ab7d4a7c0a9118a2cb519adaef1118f41):

- `evaluate_utils.py`: scorer implementations and the 28-task mapping.
- `evaluate_vlm.py`: original component weights and question-weighted aggregation.
- `all_task.json`: 29-task catalog, including unimplemented `Trajectory`.

This commit was obtained from this checkout's `origin/main` Git object; `origin`
is `https://github.com/Depth2World/VLADBench.git`. Its author date is March 26,
2026. This is an identified source version, not a claim that it remains the latest
remote revision. `provenance.json` records SHA-256 hashes, which the wrapper checks
before loading the scorer or weights.

## Explicit source repair and variants

The original scorer does not compile. Commit
`fc9e407b9c859126320e9527d287135b5bb0f368` introduced this line in
`Judge_criterion_QA`, which is still present at the preserved source commit:

```python
if ''.join(clean_pred.split(';') in ques_nopath:
```

The `upstream` runtime variant inserts one closing parenthesis:

```python
if ''.join(clean_pred.split(';')) in ques_nopath:
```

The bytes of `original/evaluate_utils.py` stay unchanged. The repair is performed
only on the in-memory source before compilation, checked to match exactly once,
and appears in every score's `scorer.runtime_patches`. Consequently, `upstream`
means **preserved upstream with a disclosed syntax-only repair**, not execution
of an unmodified, working upstream release. No metric or response parsing change
is added to this variant. Original weights are extracted from the preserved
`evaluate_vlm.py` without executing its model-file reads or spreadsheet writes.
