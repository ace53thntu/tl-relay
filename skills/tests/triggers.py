import json
import os
import sys

BOOTSTRAP = "using-tl-relay"
PLUGIN_PREFIX = "superpowers:"


def skill_calls(lines):
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        if event.get("parent_tool_use_id"):
            continue
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
                name = (block.get("input") or {}).get("skill")
                if isinstance(name, str):
                    yield name


def first_skill(lines):
    for name in skill_calls(lines):
        if name != BOOTSTRAP:
            return name
    return None


def plugin_calls(lines):
    return [name for name in skill_calls(lines) if name.startswith(PLUGIN_PREFIX)]


def first_text(lines):
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        if event.get("parent_tool_use_id"):
            continue
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                return block["text"].replace("\n", " ")[:200]
    return None


def grade(lines, expect):
    lines = list(lines)
    plugin = plugin_calls(lines)
    if plugin:
        return False, "plugin skill called: %s" % ", ".join(plugin)
    first = first_skill(lines)
    if first is None:
        reason = "no Skill call, expected %s" % expect
        text = first_text(lines)
        if text is not None:
            reason += "; answered: %s" % text
        return False, reason
    if first != expect:
        return False, "first Skill call was %s, expected %s" % (first, expect)
    return True, first


def parses(line):
    try:
        json.loads(line)
    except ValueError:
        return False
    return True


def result_events(lines):
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            yield event


def classify(lines, expect):
    lines = list(lines)
    for line in lines:
        if line.strip() and not parses(line):
            return "ERROR", "stream has an unparsable line"
        if first_skill([line]) is not None:
            break
    ok, reason = grade(lines, expect)
    if ok:
        return "PASS", reason
    if plugin_calls(lines) or first_skill(lines) is not None:
        return "FAIL", reason
    results = list(result_events(lines))
    if not results:
        return "ERROR", "stream ended with no result event"
    if any(event.get("is_error") is True for event in results):
        return "ERROR", "agent returned an error result"
    return "FAIL", reason


def watch(expect, stream, marker=None, seen_path=None):
    seen = []
    late = False
    sink = open(seen_path, "w") if seen_path else None
    for line in stream:
        seen.append(line)
        if sink:
            sink.write(line)
        first = first_skill(seen[-1:])
        if first is not None or plugin_calls(seen[-1:]):
            break
        if any(result_events(seen[-1:])):
            late = marker is not None and os.path.exists(marker)
            break
    if sink:
        sink.close()
    verdict, reason = classify(seen, expect)
    if late and verdict == "FAIL":
        return "ERROR", reason
    return verdict, reason


def main(argv):
    if len(argv) not in (3, 4) or argv[1] != "watch":
        sys.stderr.write("usage: triggers.py watch <expect> [timeout-marker]\n")
        return 2
    sys.stdin.reconfigure(errors="replace")
    verdict, reason = watch(argv[2], sys.stdin, argv[3] if len(argv) == 4 else None, os.environ.get("TL_RELAY_TRIGGER_SEEN"))
    if verdict == "PASS":
        print("PASS")
        return 0
    print("%s: %s" % (verdict, reason))
    return 1 if verdict == "FAIL" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
