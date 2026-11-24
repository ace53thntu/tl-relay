#!/usr/bin/env python3
# PostToolUse "*": thay credential trong output cua tool TRUOC khi output duoc gui len model.
# Viet sau lan ro 2026-09-30: log xcodebuild in ca moi truong, hai token ABC_GITHUB_* lot vao transcript.
#
# Chi tra updatedToolOutput khi co thay doi: hook chay song song tren output GOC,
# tra ban y nguyen se de len ban da redact cua hook khac.
# Output sai shape thi Claude Code dung output goc, nen giu nguyen cau truc tool_response.
import json
import os
import re
import sys
import tempfile
import time

MASK = "[REDACTED]"
LOG = os.path.join(tempfile.gettempdir(), "claude-redact-hook.log")

SECRET_NAME = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|AUTH|CREDENTIAL|PRIVATE_KEY|_PAT$)", re.I)

PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\bdop_v1_[a-f0-9]{40,}"),
    re.compile(r"\bPMAK-[A-Za-z0-9\-]{40,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
]

# NAME=value, NAME\=value (xcodebuild), .npmrc _authToken=, https://user:pass@host
KV = re.compile(
    r"\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|AUTH|CREDENTIAL|PRIVATE_KEY)[A-Z0-9_]*\\?=)"
    r"([\"']?)([^\s\"']{6,})"
)
NPMRC = re.compile(r"(_auth(?:Token)?\s*=\s*)(\S{6,})")
URL_CRED = re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:)([^@\s/]{6,})@")


def env_values():
    vals = set()
    for name, value in os.environ.items():
        if not SECRET_NAME.search(name):
            continue
        v = value.strip()
        if len(v) >= 12 and not v.startswith("/"):
            vals.add(v)
    return sorted(vals, key=len, reverse=True)


VALUES = env_values()


def redact(s):
    for v in VALUES:
        if v in s:
            s = s.replace(v, MASK)
    for p in PATTERNS:
        s = p.sub(MASK, s)
    s = KV.sub(lambda m: m.group(1) + m.group(2) + MASK, s)
    s = NPMRC.sub(lambda m: m.group(1) + MASK, s)
    s = URL_CRED.sub(lambda m: m.group(1) + MASK + "@", s)
    return s


def walk(node):
    if isinstance(node, str):
        return redact(node)
    if isinstance(node, list):
        return [walk(x) for x in node]
    if isinstance(node, dict):
        return {k: walk(v) for k, v in node.items()}
    return node


def log(line):
    try:
        with open(LOG, "a") as f:
            f.write(line)
    except OSError:
        pass


def main():
    payload = json.load(sys.stdin)
    if "tool_response" not in payload:
        return
    original = payload["tool_response"]
    redacted = walk(original)
    if redacted == original:
        return
    log("%s redacted %s\n" % (time.strftime("%F %T"), payload.get("tool_name", "?")))
    json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": redacted}}, sys.stdout)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("%s ERROR %s\n" % (time.strftime("%F %T"), type(e).__name__))
