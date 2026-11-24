# Finding schema

Every reviewer persona returns an object `{"findings": [...]}` of findings in this shape. The Workflow script validates each finding and rejects the persona's output when a field is missing.

```json
{"persona": "qa", "page": "lld/booking.md", "anchor": "#6-edge-cases",
 "severity": "blocking", "key_class": "none",
 "guess": "Assumed three retries", "question": "How many attempts before the booking fails?"}
```

| Field | Values |
| --- | --- |
| `persona` | `sa`, `se`, `qa`, `security`, `temporal` |
| `page` | Path of the page inside the page tree |
| `anchor` | Heading anchor on the page; the empty string when the reviewer cannot name one |
| `severity` | `blocking`, `minor` |
| `key_class` | `contract`, `data_model`, `architecture`, `security_release`, `timeline`, `none` |
| `guess` | What the reviewer had to assume to continue |
| `question` | What the page must answer so the reviewer needs no guess |

## Tagging rules

- Tag `key_class` by the choice the page must make: `contract`, `data_model`, `architecture`, `security_release` or `timeline`. Tag `none` when no such choice is open.
- A question about what existing code already does is `none`, because the writer answers it from the code at the baseline. Examples: a current error code, timeout, schema field, index or admission rule.
- At stage `hla`, a question that asks for LLD detail is `minor`. LLD detail covers exact response bodies and field values, error codes and messages, token claims, timeouts, retry intervals and attempts, clock margins, column values after a write, alert names and recipients, test methods and pass counts.

A question only an outside owner can answer is `minor`, and `question` names that owner. This rule wins over the empty or off-page anchor rule. It also wins over the key-decision check. Such a finding stays its own `minor` finding.

## Merged finding

The merge agent merges findings with equal non-empty `page` + `anchor`. It replaces `persona` with `personas`, a list of every persona that reported the finding, keeps the higher `severity`, keeps the first `key_class` other than `none` that a reviewer set, and adds `error_class`. A finding with an empty or off-page `anchor` is never merged or dropped. An off-page anchor matches no heading on its `page`. The finding stays its own finding with `error_class` set to `missing_detail`. It is `blocking` when its `key_class` is not `none`, else `blocking` unless the reviewer marked it `minor`. The empty or off-page anchor rule wins over the key-decision check.

The key-decision check applies to a finding whose `key_class` is not `none`. It marks the finding `key_decision_unasked` and `blocking` when the Agent decisions section has no row for its `page` and `anchor`. It skips findings that the outside-owner rule or the empty or off-page anchor rule covers. Only the key-decision check sets `key_decision_unasked`.

```json
{"personas": ["qa", "se"], "page": "lld/booking.md", "anchor": "#6-edge-cases",
 "severity": "blocking", "key_class": "none", "error_class": "missing_detail",
 "guess": "Assumed three retries", "question": "How many attempts before the booking fails?"}
```

`error_class` is one of `missing_detail`, `voice_structure`, `length_focus`, `key_decision_unasked`, `other`.
