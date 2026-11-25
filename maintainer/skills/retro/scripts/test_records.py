import json
import unittest
from pathlib import Path

from records import repo_skills, compile_patterns, extract, redact

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[4]
SKILLS = frozenset(["run-plan", "write-plan"])
TOKEN = "ghp_" + "a" * 36


def load():
    with open(FIXTURES / "decisions.jsonl", encoding="utf-8") as handle:
        entries = [json.loads(line) for line in handle if line.strip()]
    entries[-1]["message"]["content"] += TOKEN
    return entries


def fresh():
    return {"skills": [], "pending": None, "last_ts": None}


VI = compile_patterns({"recommended": ["đề xuất"], "correction_prefix": ["không", "sai", "khoan", "đừng", "chưa đúng"],
                       "correction_rule": ["từ giờ", "lần sau", "luôn luôn"]})


def run(entries=None, ctx=None, patterns=VI):
    return extract(entries or load(), ctx if ctx is not None else fresh(), SKILLS, "proj", patterns)


def pick(recs, **match):
    return [r for r in recs if all(r.get(k) == v for k, v in match.items())]


class ExtractTest(unittest.TestCase):
    def test_ask_decisions_come_from_the_result_entry(self):
        asks = pick(run(), kind="decision", via="ask")
        self.assertEqual(
            [(r["options"], r["recommended"], r["answer"]) for r in asks],
            [(["Fix it (Recommended)", "Skip"], "Fix it (Recommended)", "Fix it (Recommended)"),
             (["Yes", "No"], None, "No")],
        )
        self.assertEqual(asks[0]["skills"], ["run-plan"])
        self.assertEqual(asks[0]["question"], "Fix the failing check?")
        self.assertEqual(asks[0]["excerpt"], "Fix the failing check?")

    def test_record_ids_are_unique(self):
        recs = run()
        self.assertEqual(len({r["id"] for r in recs}), len(recs))
        self.assertEqual([r["id"] for r in pick(recs, via="ask")], ["s1:e3:decision:0", "s1:e3:decision:1"])

    def test_text_decision_pairs_the_next_operator_message(self):
        d = pick(run(), kind="decision", via="text")[0]
        self.assertEqual((d["options"], d["recommended"], d["answer"]), (["A", "B"], "A", "chọn A"))
        self.assertEqual(d["question"], "Which option?")
        self.assertEqual(d["project"], "proj")
        self.assertEqual(d["session"], "s1")

    def test_text_question_waits_across_batches(self):
        entries = load()
        ctx = fresh()
        first = extract(entries[:4], ctx, SKILLS, "proj", VI)
        self.assertEqual(pick(first, via="text"), [])
        self.assertIsNotNone(ctx["pending"])
        second = extract(entries[4:5], ctx, SKILLS, "proj", VI)
        self.assertEqual(len(pick(second, via="text")), 1)
        self.assertIsNone(ctx["pending"])

    def test_corrections_and_stated_rules(self):
        recs = run()
        self.assertEqual([r["marker"] for r in pick(recs, kind="correction")], ["khoan", "from now on", "rejected"])

    def test_answer_to_a_pending_question_is_not_a_correction(self):
        entries = load()
        entries[4]["message"]["content"] = "từ giờ chọn A"
        self.assertNotIn("từ giờ", [r.get("marker") for r in run(entries)])

    def test_skill_runs_count_only_repo_skills(self):
        entries = load()
        entries.append({"type": "user", "uuid": "z1", "sessionId": "s1", "timestamp": "2026-11-23T12:00:00Z",
                        "message": {"role": "user", "content":
                                    "<command-message>write-plan</command-message>\n"
                                    "<command-name>/write-plan</command-name>\n<command-args>a.md</command-args>"}})
        ctx = fresh()
        recs = run(entries, ctx)
        self.assertEqual([r["skill"] for r in pick(recs, kind="skill_run")], ["run-plan", "write-plan"])
        self.assertEqual(ctx["skills"], ["write-plan", "run-plan"])

    def test_no_field_carries_the_token(self):
        entries = load()
        entries[-1]["message"]["content"] = "stop " + entries[-1]["message"]["content"]
        recs = run(entries)
        self.assertEqual(len(pick(recs, marker="stop")), 1)
        self.assertNotIn(TOKEN, json.dumps(recs))

    def test_excerpt_is_capped(self):
        entries = load()
        entries[-1]["message"]["content"] = "wait " + "x" * 2000
        recs = run(entries)
        self.assertTrue(all(len(r["excerpt"]) <= 600 for r in recs))
        self.assertEqual(len(pick(recs, marker="wait")[0]["excerpt"]), 600)

    def test_seen_timestamps_emit_nothing(self):
        entries = load()
        ctx = fresh()
        self.assertTrue(run(entries, ctx))
        self.assertEqual(run(entries, ctx), [])

    def test_correction_survives_a_batch_cut(self):
        entries = load()
        ctx = fresh()
        extract(entries[:5], ctx, SKILLS, "proj", VI)
        extract([e for e in entries if e["uuid"] == "e6"], ctx, SKILLS, "proj", VI)
        self.assertTrue(ctx["prev_assistant"])
        recs = extract([e for e in entries if e["uuid"] == "e7"], ctx, SKILLS, "proj", VI)
        self.assertEqual([r["marker"] for r in recs], ["khoan"])

    def test_pending_excerpt_is_redacted_and_capped(self):
        ctx = fresh()
        text = "pick\n- A. one\n- B. two\n" + TOKEN + " " + "y" * 2000 + "\nWhich?"
        entry = {"type": "assistant", "uuid": "q", "sessionId": "s1", "timestamp": "2026-11-23T13:00:00Z",
                 "message": {"content": [{"type": "text", "text": text}]}}
        extract([entry], ctx, SKILLS, "proj", VI)
        self.assertIsNotNone(ctx["pending"])
        self.assertNotIn(TOKEN, json.dumps(ctx))
        self.assertLessEqual(len(ctx["pending"]["excerpt"]), 600)

    def test_only_rejected_ask_questions_emit_rejected(self):
        def reply(use_id, ts):
            return {"type": "user", "uuid": "r" + use_id, "sessionId": "s1", "timestamp": ts,
                    "message": {"content": [{"type": "tool_result", "tool_use_id": use_id, "content": "x"}]},
                    "toolUseResult": "Error: The user doesn't want to proceed with this tool use."}

        def call(name, use_id, ts):
            return {"type": "assistant", "uuid": "c" + use_id, "sessionId": "s1", "timestamp": ts,
                    "message": {"content": [{"type": "tool_use", "id": use_id, "name": name, "input": {}}]}}

        ctx = fresh()
        bash = extract([call("Bash", "b1", "2026-11-23T14:00:01Z"), reply("b1", "2026-11-23T14:00:02Z")],
                       ctx, SKILLS, "proj", VI)
        self.assertEqual(bash, [])
        ask = extract([call("AskUserQuestion", "a1", "2026-11-23T14:00:03Z")], ctx, SKILLS, "proj", VI)
        later = extract([reply("a1", "2026-11-23T14:00:04Z")], ctx, SKILLS, "proj", VI)
        self.assertEqual([r["marker"] for r in ask + later], ["rejected"])

    def test_later_stamped_noise_does_not_hide_the_next_message(self):
        entries = load()
        noise = next(e for e in entries if e["uuid"] == "e6a")
        following = entries[entries.index(noise) + 1]
        self.assertGreater(noise["timestamp"], following["timestamp"])
        self.assertEqual(len(pick(run(), marker="khoan")), 1)

    def test_interrupt_keeps_the_assistant_adjacency(self):
        entries = load()
        interrupt = {"type": "user", "uuid": "i1", "sessionId": "s1", "timestamp": "2026-11-23T11:00:06Z",
                     "message": {"content": [{"type": "text", "text": "[Request interrupted by user]"}]}}
        assistant = next(e for e in entries if e["uuid"] == "e6")
        operator = dict(next(e for e in entries if e["uuid"] == "e7"))
        operator["message"] = {"role": "user", "content": "không, dừng lại"}
        recs = run([assistant, interrupt, operator])
        self.assertEqual([r["marker"] for r in pick(recs, kind="correction")], ["không"])

    def test_ctx_may_lack_keys(self):
        ctx = {}
        self.assertTrue(run(load(), ctx))
        self.assertEqual(ctx["last_ts"], load()[-1]["timestamp"])


class HelperTest(unittest.TestCase):
    def test_repo_skills_lists_folders_with_skill_md(self):
        names = repo_skills(REPO)
        self.assertIn("run-plan", names)
        self.assertIn("write-skill", names)
        self.assertNotIn("tests", names)

    def test_redact_masks_a_token(self):
        self.assertNotIn(TOKEN, redact("x " + TOKEN))


class PatternsTest(unittest.TestCase):
    def test_default_patterns_hold_english_words_only(self):
        recs = run(patterns=compile_patterns())
        self.assertEqual([r["marker"] for r in pick(recs, kind="correction")], ["from now on", "rejected"])

    def test_extra_words_extend_the_english_ones(self):
        patterns = compile_patterns({"correction_prefix": ["nein"]})
        self.assertTrue(patterns["correction_prefix"].match("Nein, anders"))
        self.assertTrue(patterns["correction_prefix"].match("no, the other one"))

    def test_extra_words_are_literal(self):
        patterns = compile_patterns({"correction_rule": ["a.b"]})
        self.assertIsNone(patterns["correction_rule"].search("axb"))

    def test_unknown_key_is_refused(self):
        with self.assertRaises(ValueError):
            compile_patterns({"corrections": ["x"]})

    def test_non_list_value_is_refused(self):
        with self.assertRaises(ValueError):
            compile_patterns({"correction_rule": "từ giờ"})


if __name__ == "__main__":
    unittest.main()
