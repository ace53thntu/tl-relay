#!/usr/bin/env python3
# PreToolUse/Bash: boc lenh de shell luon thoat 0 va in "[exit code N]" khi lenh loi.
# Lenh loi di qua PostToolUseFailure, su kien do khong thay duoc output, nen
# redact-secrets-output.py chi che duoc output cua lenh thoat 0.
# `exit N` ben trong lenh do trap EXIT bat; lenh tu dat trap EXIT rieng thi van lot.
# Chi boc o bypass mode: lenh da boc khong qua duoc kiem tra permission o cac mode khac.
import json
import sys

MARK = "__cc_rc=$?;"
TRAP = "trap '__cc_rc=$?; [ \"$__cc_rc\" -eq 0 ] || printf \"\\n[exit code %s]\\n\" \"$__cc_rc\"; exit 0' EXIT\n"


def main():
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    cmd = tool_input.get("command")
    if payload.get("permission_mode") != "bypassPermissions":
        return
    if not isinstance(cmd, str) or not cmd.strip() or MARK in cmd:
        return
    wrapped = TRAP + "{ %s\n}; %s [ \"$__cc_rc\" -eq 0 ] || printf '\\n[exit code %%s]\\n' \"$__cc_rc\"" % (cmd, MARK)
    json.dump(
        {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": dict(tool_input, command=wrapped)}},
        sys.stdout,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
