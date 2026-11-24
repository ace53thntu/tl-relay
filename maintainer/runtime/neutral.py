import os
import re
import subprocess
import tempfile


class NeutralError(Exception):
    pass


def _local_env_vars():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG_") and k not in ("GIT_DIR", "GIT_WORK_TREE")}
    done = subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, env=env)
    if done.returncode != 0:
        raise NeutralError("git rev-parse --local-env-vars failed: %s" % os.fsdecode(done.stderr).strip())
    return os.fsdecode(done.stdout).split()


def _trusted_toplevel(repo, scrub):
    env = {k: v for k, v in os.environ.items() if k not in scrub}
    done = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"], capture_output=True, env=env)
    if done.returncode != 0:
        raise NeutralError("git rev-parse failed: %s" % os.fsdecode(done.stderr).strip())
    out = done.stdout
    return os.fsdecode(out[:-1] if out.endswith(b"\n") else out)


def _grep(top, scrub, *args):
    env = {k: v for k, v in os.environ.items() if k not in scrub and k != "GIT_ATTR_SOURCE"}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_ATTR_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    config = ["-c", "core.attributesFile=/dev/null", "-c", "safe.directory=%s" % top]
    done = subprocess.run(["git", "--no-replace-objects", "-C", top, *config, *args], capture_output=True, env=env)
    return done.returncode, done.stdout, os.fsdecode(done.stderr).strip()


_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\\": "\\\\"}


def _escape(c):
    if c in _ESCAPES:
        return _ESCAPES[c]
    if "\udc80" <= c <= "\udcff":
        return "\\x%02x" % (ord(c) - 0xdc00)
    if c.isprintable():
        return c
    code = ord(c)
    return "\\x%02x" % code if code < 0x80 else "\\u%04x" % code if code < 0x10000 else "\\U%08x" % code


def _printable(path):
    return "".join(_escape(c) for c in path.decode("utf-8", "surrogateescape"))


def _has_nul(top, scrub, rev, path):
    code, out, err = _grep(top, scrub, "cat-file", "blob", rev.encode() + b":" + path)
    if code != 0:
        raise NeutralError("git cat-file failed: %s" % err)
    return b"\0" in out[:8000]


def hits(repo, patterns, rev="HEAD"):
    scrub = _local_env_vars()
    top = _trusted_toplevel(repo, scrub)
    first = {}
    for index, pattern in enumerate(patterns):
        code, out, err = _grep(top, scrub, "grep", "-z", "-naiP", "--no-color", "-e", pattern, rev, "--", ".")
        if code == 1:
            continue
        if code != 0:
            raise NeutralError("git grep failed: %s" % err)
        pos = 0
        for row in re.finditer(rb"(.*?)\0(\d+)\0[^\n]*\n", out, re.S):
            if row.start() != pos:
                raise NeutralError("git grep output is malformed at byte %d" % pos)
            pos = row.end()
            first.setdefault((row.group(1)[len(rev.encode()) + 1:], int(row.group(2))), index)
        if pos != len(out):
            raise NeutralError("git grep output is malformed at byte %d" % pos)
    nul = {}
    kept = []
    for path, number in sorted(first):
        if path not in nul:
            nul[path] = _has_nul(top, scrub, rev, path)
        if not nul[path]:
            kept.append((path, number))
    return ["%s:%d: %s" % (_printable(path), number, patterns[first[(path, number)]]) for path, number in kept]


def _git_out(top, scrub, *args):
    code, out, err = _grep(top, scrub, *args)
    if code != 0:
        raise NeutralError("git %s failed: %s" % (args[0], err))
    return os.fsdecode(out).strip()


_IDENTITY = re.compile(rb"(?:author|committer|tagger) (.*)<([^<>]*)> \d+ [+-]\d+")
_OBJECT_LENGTH = {"sha1": 40, "sha256": 64}
_TAG_TARGET = re.compile(rb"object ([^\n]*)(?:\n|$)")


def _identity_text(header, logged, allow, kinds=(b"author ", b"committer ")):
    kept = []
    for line in header.split(b"\n"):
        if not line.startswith(kinds):
            continue
        match = _IDENTITY.fullmatch(line)
        if not match:
            kept.append(line)
        elif match.group(2) in allow:
            kept.append(match.group(1))
        else:
            kept.append(match.group(1) + b"<" + match.group(2) + b">")
    for index, value in enumerate(logged.split(b"\n")):
        if index % 2 == 0 or value not in allow:
            kept.append(value)
    return b"\n".join(kept)


def _commit_texts(top, scrub, commit, allow):
    code, out, err = _grep(top, scrub, "cat-file", "commit", commit)
    if code != 0:
        raise NeutralError("git cat-file failed: %s" % err)
    code, logged, err = _grep(top, scrub, "-c", "log.showSignature=false", "log", "-1", "--no-show-signature",
                              "--no-mailmap", "--encoding=UTF-8", "--format=%an%n%ae%n%cn%n%ce%x00%B",
                              "--end-of-options", commit, "--")
    if code != 0:
        raise NeutralError("git log failed: %s" % err)
    code, paths, err = _grep(top, scrub, "ls-tree", "-r", "-z", "--name-only", "--full-tree", commit)
    if code != 0:
        raise NeutralError("git ls-tree failed: %s" % err)
    header, _, raw = out.partition(b"\n\n")
    names, _, text = logged.partition(b"\0")
    return {
        "message": (raw + b"\n" + text).replace(b"\0", b"\n") + b"\n" + raw.replace(b"\0", b""),
        "identity": _identity_text(header, names, allow),
        "path": paths.replace(b"\0", b"\n"),
    }


def _text_hits(top, scrub, texts, patterns):
    found = {}
    commits = set(texts)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for commit, text in texts.items():
                with open(os.path.join(tmp, commit), "wb") as handle:
                    handle.write(text)
            for pattern in patterns:
                code, out, err = _grep(tmp, scrub, "-c", "grep.fullName=false", "grep", "--no-index", "-l", "-aiP",
                                       "--no-color", "-e", pattern)
                if code == 1:
                    continue
                if code != 0:
                    raise NeutralError("git grep failed: %s" % err)
                for commit in os.fsdecode(out).split():
                    if commit not in commits:
                        raise NeutralError("git grep named an unexpected file: %s" % commit)
                    found.setdefault(commit, []).append(pattern)
    except OSError as exc:
        raise NeutralError("message scan failed: %s" % exc)
    return found


def tag_hits(repo, patterns, oid, identity_allow=()):
    scrub = _local_env_vars()
    top = _trusted_toplevel(repo, scrub)
    length = _OBJECT_LENGTH.get(_git_out(top, scrub, "rev-parse", "--show-object-format"))
    if length is None:
        raise NeutralError("unknown object format in %s" % top)
    full = re.compile(r"[0-9a-f]{%d}" % length)
    if not full.fullmatch(oid):
        raise NeutralError("tag object must be a full object id: %s" % oid)
    allow = {address.encode("utf-8", "surrogateescape") for address in identity_allow}
    messages, identities = {}, {}
    current = oid
    while _git_out(top, scrub, "cat-file", "-t", current) == "tag":
        if current in messages:
            raise NeutralError("tag chain repeats object %s" % current)
        code, out, err = _grep(top, scrub, "cat-file", "tag", current)
        if code != 0:
            raise NeutralError("git cat-file failed: %s" % err)
        header, _, body = out.partition(b"\n\n")
        target = _TAG_TARGET.match(header)
        if not target or not full.fullmatch(target.group(1).decode("ascii", "replace")):
            raise NeutralError("tag object %s names no full target id" % current)
        messages[current] = body.replace(b"\0", b"\n") + b"\n" + body.replace(b"\0", b"")
        identities[current] = _identity_text(header, b"", allow, (b"tagger ",))
        current = target.group(1).decode()
    if not messages:
        return []
    found_messages = _text_hits(top, scrub, messages, patterns)
    found_identities = _text_hits(top, scrub, identities, patterns)
    rows = []
    for tag in messages:
        rows.extend("%s:(tag message): %s" % (tag, pattern) for pattern in found_messages.get(tag, []))
        rows.extend("%s:(tag identity): %s" % (tag, pattern) for pattern in found_identities.get(tag, []))
    return rows


def range_hits(repo, patterns, spec, identity_allow=()):
    base, sep, head = spec.partition("..")
    if not sep or not base or not head or base.startswith("-") or head.startswith("-") or head.startswith("."):
        raise NeutralError("range must read <base>..<head>: %s" % spec)
    scrub = _local_env_vars()
    top = _trusted_toplevel(repo, scrub)
    if _git_out(top, scrub, "rev-parse", "--is-shallow-repository") == "true":
        raise NeutralError("range scan needs full history, and this repository is shallow")
    base, head = (_git_out(top, scrub, "rev-parse", "--verify", "--end-of-options", rev + "^{commit}")
                  for rev in (base, head))
    if head != base:
        code, _, err = _grep(top, scrub, "merge-base", "--is-ancestor", head, base)
        if code == 0:
            raise NeutralError("range head is an ancestor of its base: %s" % spec)
        if code != 1:
            raise NeutralError("git merge-base failed: %s" % err)
    walk = "%s..%s" % (base, head)
    commits = _git_out(top, scrub, "rev-list", "--end-of-options", walk, "--").split()
    allow = {address.encode("utf-8", "surrogateescape") for address in identity_allow}
    texts = {commit: _commit_texts(top, scrub, commit, allow) for commit in commits}
    messages, identities, paths = (
        _text_hits(top, scrub, {commit: texts[commit][kind] for commit in commits}, patterns)
        for kind in ("message", "identity", "path")
    )
    rows = []
    for commit in commits:
        rows.extend("%s:%s" % (commit, row) for row in hits(repo, patterns, commit))
        rows.extend("%s:(commit message): %s" % (commit, pattern) for pattern in messages.get(commit, []))
        rows.extend("%s:(commit identity): %s" % (commit, pattern) for pattern in identities.get(commit, []))
        rows.extend("%s:(tree path): %s" % (commit, pattern) for pattern in paths.get(commit, []))
    return rows
