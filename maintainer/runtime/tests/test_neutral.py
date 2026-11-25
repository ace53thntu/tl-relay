import contextlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import sdlc  # noqa: E402
from runtime import neutral  # noqa: E402


LOCAL_ENV = subprocess.run(["git", "rev-parse", "--local-env-vars"], check=True, capture_output=True,
                           text=True).stdout.split()
ENV = {k: v for k, v in os.environ.items() if k not in LOCAL_ENV and not k.startswith(("AI_SDLC_", "TL_RELAY_"))}


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True, env=ENV)


class CheckNeutralTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = pathlib.Path(tmp.name) / "home"
        self.home.mkdir()
        self.repo = pathlib.Path(tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        self.commit("a.md", "acme-internal\n")

    def head(self):
        return subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], check=True, capture_output=True,
                              env=ENV).stdout.decode().strip()

    def commit(self, name, text):
        path = self.repo / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode())
        git(self.repo, "add", name)
        git(self.repo, "commit", "-q", "-m", "x")

    def run_check(self, patterns, text=None, repo=None, env=None, sdlc_repo=None, drop=(), cwd=None, range_spec=None):
        if text is None and patterns:
            text = "neutrality:\n  patterns: [%s]\n" % ", ".join("'%s'" % p for p in patterns)
        if text:
            (self.home / "tl-relay.yaml").write_text(text)
        out, err = io.StringIO(), io.StringIO()
        env = {"TL_RELAY_HOME": str(self.home), "TL_RELAY_REPO": str(sdlc_repo or self.home), **(env or {})}
        before = os.getcwd()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            for name in drop:
                os.environ.pop(name, None)
            try:
                if cwd:
                    os.chdir(cwd)
                code = sdlc.main(["check-neutral", "--repo", str(repo or self.repo)]
                                 + (["--range=%s" % range_spec] if range_spec is not None else []))
            finally:
                os.chdir(before)
        return code, out.getvalue(), err.getvalue()

    def test_hit_is_reported(self):
        code, out, _ = self.run_check(["acme"])
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["a.md:1: acme"])

    def test_clean_repo_exits_0(self):
        code, out, _ = self.run_check(["zzz"])
        self.assertEqual((code, out), (0, ""))

    def test_empty_patterns_exit_2(self):
        code, _, err = self.run_check([])
        self.assertEqual(code, 2)
        self.assertEqual(err.strip(), "neutrality.patterns is empty in %s/tl-relay.yaml" % self.home)

    def test_check_neutral_reads_a_legacy_home(self):
        (self.home / "ai-sdlc.yaml").write_text("neutrality:\n  patterns: ['zzz']\n")
        out, err = io.StringIO(), io.StringIO()
        env = {"AI_SDLC_HOME": str(self.home)}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            os.environ.pop("TL_RELAY_HOME", None)
            code = sdlc.main(["check-neutral", "--repo", str(self.repo)])
        self.assertEqual((code, out.getvalue()), (0, ""))

    def test_untracked_file_is_ignored(self):
        (self.repo / "b.md").write_text("zzz-secret\n")
        code, out, _ = self.run_check(["zzz"])
        self.assertEqual((code, out), (0, ""))

    def test_word_boundary_after_hyphen(self):
        word = "dg" + "l-"
        self.commit("c.md", "see yaa-%ssvc here\n" % word)
        code, out, _ = self.run_check([r"\b" + word])
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["c.md:1: \\b" + word])

    def test_git_failure_exits_2(self):
        bare = self.home / "notrepo"
        bare.mkdir()
        code, _, err = self.run_check(["acme"], repo=bare)
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: "))

    def test_first_configured_pattern_reported_once(self):
        code, out, _ = self.run_check(["internal", "acme"])
        self.assertEqual(out.splitlines(), ["a.md:1: internal"])

    def test_second_pattern_on_other_line_keeps_own_name(self):
        self.commit("a.md", "acme-internal\nother zzz\n")
        code, out, _ = self.run_check(["acme", "zzz"])
        self.assertEqual(out.splitlines(), ["a.md:1: acme", "a.md:2: zzz"])

    def test_non_list_patterns_exit_2(self):
        code, _, err = self.run_check(None, text="neutrality:\n  patterns: acme\n")
        self.assertEqual(code, 2)
        self.assertIn("neutrality.patterns", err)

    def test_non_string_pattern_exit_2(self):
        code, _, err = self.run_check(None, text="neutrality:\n  patterns: [1]\n")
        self.assertEqual(code, 2)
        self.assertIn("neutrality.patterns", err)

    def test_pcre_only_pattern_reports_hit(self):
        code, out, _ = self.run_check(["ac(?|m)e"])
        self.assertEqual((code, out.splitlines()), (1, ["a.md:1: ac(?|m)e"]))

    def test_non_utf8_file_reports_hit(self):
        self.commit("bin.txt", b"caf\xe9 acme\n")
        code, out, _ = self.run_check(["acme"])
        self.assertEqual(code, 1)
        self.assertIn("bin.txt:1: acme", out.splitlines())

    def test_colon_in_file_name(self):
        self.commit("we:ird.md", "acme\n")
        code, out, _ = self.run_check(["acme"])
        self.assertIn("we:ird.md:1: acme", out.splitlines())

    def test_subdirectory_repo_scans_whole_repo(self):
        self.commit("sub/x.md", "clean\n")
        code, out, _ = self.run_check(["acme"], repo=self.repo / "sub")
        self.assertEqual((code, out.splitlines()), (1, ["a.md:1: acme"]))

    def test_repo_layer_patterns_do_not_count(self):
        self.commit("tl-relay.yaml", "neutrality:\n  patterns: ['acme']\n")
        code, _, err = self.run_check([], sdlc_repo=self.repo)
        self.assertEqual(code, 2)
        self.assertIn("is empty", err)

    def test_exported_git_dir_does_not_redirect_the_scan(self):
        decoy = self.home / "decoy"
        decoy.mkdir()
        git(decoy, "init", "-q")
        (decoy / "d.md").write_text("clean\n")
        git(decoy, "add", "d.md")
        git(decoy, "commit", "-q", "-m", "d")
        code, out, _ = self.run_check(["acme"], env={"GIT_DIR": str(decoy / ".git")})
        self.assertEqual((code, out.splitlines()), (1, ["a.md:1: acme"]))

    def test_local_env_vars_are_scrubbed(self):
        empty = self.home / "emptyobjects"
        empty.mkdir()
        code, out, _ = self.run_check(["acme"], env={"GIT_OBJECT_DIRECTORY": str(empty)})
        self.assertEqual((code, out.splitlines()), (1, ["a.md:1: acme"]))
        attrs = self.home / "attrs"
        attrs.write_text("* binary\n")
        code, out, _ = self.run_check(["acme"], env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.attributesFile",
                                                     "GIT_CONFIG_VALUE_0": str(attrs)})
        self.assertEqual((code, out.splitlines()), (1, ["a.md:1: acme"]))

    def test_empty_pattern_exits_2(self):
        code, out, err = self.run_check(["acme", ""])
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err.strip(), "error: neutrality.patterns must not hold an empty pattern")

    def test_file_name_with_newline(self):
        self.commit("a\nb.md", "acme\n")
        code, out, err = self.run_check(["acme"])
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("a\\nb.md:1: acme", out.splitlines())

    def test_crafted_file_name_cannot_forge_a_line(self):
        self.commit("x\nREADME.md:1: ok", "acme\n")
        code, out, _ = self.run_check(["acme"])
        self.assertEqual(code, 1)
        self.assertNotIn("README.md:1: ok", out.splitlines())
        self.assertIn("x\\nREADME.md:1: ok:1: acme", out.splitlines())

    def test_range_finds_a_leak_a_later_commit_removed(self):
        base = self.head()
        self.commit("b.md", "acme-leak\n")
        leaked = self.head()
        self.commit("b.md", "clean\n")
        code, out, _ = self.run_check(["acme-leak"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:b.md:1: acme-leak" % leaked, out)

    def test_range_finds_a_pattern_only_in_a_path(self):
        base = self.head()
        self.commit("acme-path.md", "clean\n")
        leaked = self.head()
        git(self.repo, "rm", "-q", "acme-path.md")
        git(self.repo, "commit", "-q", "-m", "x")
        code, out, _ = self.run_check(["acme-path"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(tree path): acme-path" % leaked, out)

    def test_range_finds_a_pattern_in_the_author(self):
        base = self.head()
        (self.repo / "b.md").write_text("clean\n")
        git(self.repo, "add", "b.md")
        git(self.repo, "commit", "-q", "-m", "x", "--author=acme-person <p@example.com>")
        code, out, _ = self.run_check(["acme-person"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit identity): acme-person" % self.head(), out)

    def test_range_finds_a_pattern_in_the_committer_email(self):
        base = self.head()
        (self.repo / "b.md").write_text("clean\n")
        git(self.repo, "add", "b.md")
        git(self.repo, "-c", "user.email=me@acme-mail.example", "commit", "-q", "-m", "x",
            "--author=t <t@example.com>")
        code, out, _ = self.run_check(["acme-mail"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit identity): acme-mail" % self.head(), out)

    def test_range_does_not_match_an_identity_timestamp(self):
        base = self.head()
        self.commit("b.md", "clean\n")
        stamp = subprocess.run(["git", "-C", str(self.repo), "log", "-1", "--format=%at"], check=True,
                               capture_output=True, env=ENV).stdout.decode().strip()
        self.assertEqual(self.run_check([stamp], range_spec="%s..HEAD" % base)[0], 0)

    ALLOWED = "me@acme-mail.example"

    def commit_as(self, author=ALLOWED, committer=ALLOWED, name="t", message="x", path=None, body="clean\n"):
        if path:
            (self.repo / path).write_text(body)
            git(self.repo, "add", path)
        git(self.repo, "-c", "user.name=t", "-c", "user.email=%s" % committer, "commit", "-q", "--allow-empty",
            "-m", message, "--author=%s <%s>" % (name, author))
        return self.head()

    def allow_config(self, value="[%s]" % ALLOWED):
        return "neutrality:\n  patterns: ['acme-mail']\n  identity_allow: %s\n" % value

    def scan(self, base, text=None):
        return self.run_check(["acme-mail"], text=text or self.allow_config(), range_spec="%s..HEAD" % base)

    def test_an_exact_allowed_email_passes(self):
        base = self.head()
        self.commit_as()
        self.assertEqual(self.scan(base)[:2], (0, ""))

    def test_a_near_match_of_an_allowed_email_still_hits(self):
        for email in ("x" + self.ALLOWED, self.ALLOWED + ".org", "me@acme-mail.test", "ME@acme-mail.example"):
            with self.subTest(email=email):
                base = self.head()
                sha = self.commit_as(author=email, committer=email)
                code, out, _ = self.scan(base)
                self.assertEqual(code, 1)
                self.assertIn("%s:(commit identity): acme-mail" % sha, out)

    def test_an_allowed_author_does_not_excuse_a_forbidden_committer(self):
        base = self.head()
        sha = self.commit_as(committer="other@acme-mail.example")
        code, out, _ = self.scan(base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit identity): acme-mail" % sha, out)

    def test_an_allowed_committer_does_not_excuse_a_forbidden_author(self):
        base = self.head()
        sha = self.commit_as(author="other@acme-mail.example")
        code, out, _ = self.scan(base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit identity): acme-mail" % sha, out)

    def test_an_allowed_address_in_a_message_still_hits(self):
        base = self.head()
        sha = self.commit_as(message="contact %s" % self.ALLOWED)
        code, out, _ = self.scan(base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit message): acme-mail" % sha, out)
        self.assertNotIn("(commit identity)", out)

    def test_an_allowed_address_in_a_file_still_hits(self):
        base = self.head()
        sha = self.commit_as(path="b.md", body=self.ALLOWED + "\n")
        code, out, _ = self.scan(base)
        self.assertEqual(code, 1)
        self.assertIn("%s:b.md:1: acme-mail" % sha, out)
        self.assertNotIn("(commit identity)", out)

    def test_an_allowed_address_in_a_path_still_hits(self):
        base = self.head()
        sha = self.commit_as(path=self.ALLOWED + ".md")
        code, out, _ = self.scan(base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(tree path): acme-mail" % sha, out)
        self.assertNotIn("(commit identity)", out)

    def test_a_forbidden_name_beside_an_allowed_email_hits(self):
        base = self.head()
        sha = self.commit_as(name="acme-mail person")
        code, out, _ = self.scan(base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit identity): acme-mail" % sha, out)

    def test_an_allowed_address_used_as_a_name_hits(self):
        base = self.head()
        sha = self.commit_as(name=self.ALLOWED.replace("@", " at "))
        code, out, _ = self.scan(base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit identity): acme-mail" % sha, out)

    def test_a_missing_or_empty_allowlist_exempts_nothing(self):
        base = self.head()
        sha = self.commit_as()
        for text in ("neutrality:\n  patterns: ['acme-mail']\n", self.allow_config("[]")):
            with self.subTest(text=text):
                code, out, _ = self.scan(base, text)
                self.assertEqual(code, 1)
                self.assertIn("%s:(commit identity): acme-mail" % sha, out)

    def test_a_malformed_allowlist_exits_two_naming_the_key(self):
        for value in ("me@example.invalid", "5", "true", "{a: b}", "[5]", "['']", "['  ']", "[[a]]", "[true]", ""):
            for range_spec in ("HEAD..HEAD", None):
                with self.subTest(value=value, range_spec=range_spec):
                    code, _, err = self.run_check(["zzz"], text="neutrality:\n  patterns: ['zzz']\n  identity_allow: %s\n"
                                                  % value, range_spec=range_spec)
                    self.assertEqual(code, 2)
                    self.assertIn("neutrality.identity_allow", err)
                    self.assertEqual(len(err.strip().splitlines()), 1)

    def test_a_tag_chain_that_repeats_an_object_is_refused(self):
        first, second = "a" * 40, "b" * 40
        target = {first: second, second: first}
        calls = []
        real = neutral._grep

        def fake(top, scrub, *args):
            if args[0] != "cat-file":
                return real(top, scrub, *args)
            calls.append(args)
            if len(calls) > 20:
                raise AssertionError("the chain walk did not stop")
            if args[1] == "-t":
                return 0, b"tag\n", ""
            return 0, b"object %s\ntype tag\ntag x\n\nm\n" % target[args[2]].encode(), ""

        with mock.patch.object(neutral, "_grep", fake):
            with self.assertRaisesRegex(neutral.NeutralError, "repeats"):
                neutral.tag_hits(self.repo, ["zzz"], first)

    def test_a_sha256_tag_chain_is_scanned(self):
        repo = self.home.parent / "sha256"
        repo.mkdir()
        git(repo, "init", "-q", "--object-format=sha256")
        (repo / "a.md").write_text("clean\n")
        git(repo, "add", "a.md")
        git(repo, "commit", "-q", "-m", "x")
        git(repo, "tag", "-a", "-m", "acme-tag", "v1")
        oid = subprocess.run(["git", "-C", str(repo), "rev-parse", "refs/tags/v1"], check=True, capture_output=True,
                             env=ENV).stdout.decode().strip()
        self.assertEqual(neutral.tag_hits(repo, ["acme-tag"], oid), ["%s:(tag message): acme-tag" % oid])

    def test_a_sha1_length_id_is_refused_in_a_sha256_repository(self):
        repo = self.home.parent / "sha256-short"
        repo.mkdir()
        git(repo, "init", "-q", "--object-format=sha256")
        with self.assertRaises(neutral.NeutralError):
            neutral.tag_hits(repo, ["zzz"], "a" * 40)

    def test_an_empty_range_exits_zero(self):
        self.assertEqual(self.run_check(["acme"], range_spec="HEAD..HEAD")[0], 0)

    def test_a_bad_range_exits_two(self):
        self.assertEqual(self.run_check(["acme"], range_spec="nope..HEAD")[0], 2)

    def test_a_range_starting_with_a_dash_exits_two(self):
        self.assertEqual(self.run_check(["acme"], range_spec="--all")[0], 2)

    def test_an_empty_range_value_exits_two(self):
        self.assertEqual(self.run_check(["acme"], range_spec="")[0], 2)

    def test_working_tree_attributes_do_not_hide_a_leak(self):
        base = self.head()
        self.commit("b.md", "acme-leak\n")
        self.commit("b.md", "clean\n")
        (self.repo / ".gitattributes").write_text("* binary\n")
        code, out, _ = self.run_check(["acme-leak"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        code, out, _ = self.run_check(["acme-internal"])
        self.assertEqual((code, out.splitlines()), (1, ["a.md:1: acme-internal"]))

    def test_info_attributes_do_not_hide_a_leak(self):
        (self.repo / ".git" / "info").mkdir(exist_ok=True)
        (self.repo / ".git" / "info" / "attributes").write_text("* binary\n")
        self.assertEqual(self.run_check(["acme-internal"])[0], 1)

    def test_a_blob_with_a_nul_is_skipped(self):
        self.commit("blob.bin", b"acme\0zzz\n")
        code, out, _ = self.run_check(["zzz"])
        self.assertEqual((code, out), (0, ""))

    def test_a_replace_ref_does_not_hide_a_commit(self):
        base = self.head()
        self.commit("b.md", "acme-leak\n")
        leaked = self.head()
        self.commit("b.md", "clean\n")
        git(self.repo, "replace", leaked, base)
        code, out, _ = self.run_check(["acme-leak"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:b.md:1: acme-leak" % leaked, out)

    def test_a_shallow_clone_exits_two(self):
        self.commit("b.md", "clean\n")
        shallow = self.home / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://%s" % self.repo, str(shallow)], check=True,
                       capture_output=True, env=ENV)
        self.assertEqual(self.run_check(["acme"], repo=shallow, range_spec="HEAD..HEAD")[0], 2)

    def test_a_reversed_range_exits_two(self):
        base = self.head()
        self.commit("b.md", "acme-leak\n")
        self.assertEqual(self.run_check(["acme"], range_spec="HEAD..%s" % base)[0], 2)

    def test_a_non_commit_endpoint_exits_two(self):
        base = self.head()
        self.commit("b.md", "acme-leak\n")
        self.assertEqual(self.run_check(["acme"], range_spec="%s..HEAD^{tree}" % base)[0], 2)

    def test_range_finds_a_pattern_in_a_commit_message(self):
        base = self.head()
        git(self.repo, "commit", "--allow-empty", "-q", "-m", "mentions acme-leak here")
        code, out, _ = self.run_check(["ACME-LEAK"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit message): ACME-LEAK" % self.head(), out.splitlines())

    def test_a_late_nul_does_not_hide_a_leak(self):
        self.commit("late.md", b"acme-leak\n" + b"x" * 12000 + b"\0tail\n")
        code, out, _ = self.run_check(["acme-leak"])
        self.assertEqual(code, 1)
        self.assertIn("late.md:1: acme-leak", out.splitlines())

    def test_a_diverged_range_is_scanned(self):
        base = self.head()
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.commit("b.md", "acme-leak\n")
        feature = self.head()
        git(self.repo, "checkout", "-q", base)
        self.commit("c.md", "clean\n")
        code, out, _ = self.run_check(["acme-leak"], range_spec="%s..%s" % (self.head(), feature))
        self.assertEqual(code, 1)
        self.assertIn("%s:b.md:1: acme-leak" % feature, out)

    def test_a_log_output_encoding_does_not_hide_a_message(self):
        base = self.head()
        git(self.repo, "config", "i18n.logOutputEncoding", "UTF-16")
        git(self.repo, "commit", "--allow-empty", "-q", "-m", "mentions acme-leak here")
        code, out, _ = self.run_check(["acme-leak"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit message): acme-leak" % self.head(), out.splitlines())

    def test_a_nul_in_a_message_does_not_hide_a_pattern(self):
        base = self.head()
        tree = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD^{tree}"], check=True,
                              capture_output=True, env=ENV).stdout.decode().strip()
        who = b"t <t@example.com> 0 +0000"
        body = b"tree %s\nparent %s\nauthor %s\ncommitter %s\n\nclean\0acme-leak\n" % (
            tree.encode(), base.encode(), who, who)
        sha = subprocess.run(["git", "-C", str(self.repo), "hash-object", "-t", "commit", "-w", "--literally",
                              "--stdin"], input=body, check=True, capture_output=True,
                             env=ENV).stdout.decode().strip()
        git(self.repo, "update-ref", "HEAD", sha)
        code, out, _ = self.run_check(["acme-leak"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit message): acme-leak" % sha, out.splitlines())

    def raw_commit(self, headers, body):
        tree = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD^{tree}"], check=True,
                              capture_output=True, env=ENV).stdout.decode().strip()
        who = b"t <t@example.com> 0 +0000"
        data = b"tree %s\nparent %s\nauthor %s\ncommitter %s\n%s\n%s" % (
            tree.encode(), self.head().encode(), who, who, headers, body)
        sha = subprocess.run(["git", "-C", str(self.repo), "hash-object", "-t", "commit", "-w", "--literally",
                              "--stdin"], input=data, check=True, capture_output=True,
                             env=ENV).stdout.decode().strip()
        git(self.repo, "update-ref", "HEAD", sha)
        return sha

    def test_a_latin1_message_is_matched_as_text(self):
        base = self.head()
        (self.home / "msg").write_bytes(b"caf\xe9-leak\n")
        git(self.repo, "-c", "i18n.commitEncoding=ISO-8859-1", "commit", "--allow-empty", "-q", "-F",
            str(self.home / "msg"))
        code, out, _ = self.run_check(["caf\u00e9-leak"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit message): caf\u00e9-leak" % self.head(), out.splitlines())

    def test_a_utf16_message_is_matched_as_text(self):
        base = self.head()
        sha = self.raw_commit(b"encoding UTF-16\n", "mentions acme-leak\n".encode("utf-16"))
        code, out, _ = self.run_check(["acme-leak"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit message): acme-leak" % sha, out.splitlines())

    def assert_message_hit(self, headers, body, pattern):
        base = self.head()
        sha = self.raw_commit(headers, body)
        code, out, err = self.run_check([pattern], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1, err)
        self.assertIn("%s:(commit message): %s" % (sha, pattern), out.splitlines())

    def test_a_utf16_message_without_a_header_is_matched_as_text(self):
        self.assert_message_hit(b"", "mentions acme-leak\n".encode("utf-16"), "acme-leak")

    def test_a_wrong_encoding_header_does_not_hide_a_message(self):
        for headers, body, pattern in ((b"encoding cp037\n", b"mentions acme-leak\n", "acme-leak"),
                                       (b"encoding UTF-16\n", b"mentions acme-leak\n", "acme-leak"),
                                       (b"encoding ISO-8859-1\n", "caf\u00e9-leak\n".encode(), "caf\u00e9-leak")):
            with self.subTest(headers=headers):
                self.assert_message_hit(headers, body, pattern)

    def test_an_encoding_name_python_accepts_and_git_rejects_is_scanned(self):
        for name in (b"u16", b"utf_16", b"UTF-16 "):
            with self.subTest(name=name):
                self.assert_message_hit(b"encoding " + name + b"\n", b"acme-leak\n", "acme-leak")

    def test_a_nul_in_an_encoding_name_is_scanned(self):
        self.assert_message_hit(b"encoding UTF\0-8\n", b"acme-leak\n", "acme-leak")

    def test_an_encoding_name_git_cannot_convert_does_not_block_the_range(self):
        for name in (b"CP1252//TRANSLIT", b"Shift_JIS"):
            with self.subTest(name=name):
                self.assert_message_hit(b"encoding " + name + b"\n", b"acme-leak \xff\n", "acme-leak")

    def test_full_name_grep_config_does_not_hide_a_message(self):
        base = self.head()
        git(self.repo, "commit", "--allow-empty", "-q", "-m", "mentions acme-leak here")
        outer = self.home / "outer"
        (outer / "tmp").mkdir(parents=True)
        git(outer, "init", "-q")
        git(outer, "config", "grep.fullName", "true")
        with mock.patch.object(tempfile, "tempdir", str(outer / "tmp")):
            code, out, _ = self.run_check(["acme-leak"], range_spec="%s..HEAD" % base)
        self.assertEqual(code, 1)
        self.assertIn("%s:(commit message): acme-leak" % self.head(), out.splitlines())

    def test_an_unusable_temp_directory_exits_two(self):
        with mock.patch.object(tempfile, "tempdir", str(self.home / "missing")):
            code, out, err = self.run_check(["acme"], range_spec="HEAD..HEAD")
        self.assertEqual((code, out), (2, ""))
        self.assertNotIn("Traceback", err)

    def test_a_repo_gpg_program_is_not_run(self):
        stub = self.home / "gpg-stub.sh"
        marker = self.home / "gpg-ran"
        stub.write_text("#!/bin/sh\ntouch '%s'\necho acme-leak\necho acme-leak >&2\n" % marker)
        stub.chmod(0o755)
        git(self.repo, "config", "log.showSignature", "true")
        git(self.repo, "config", "gpg.program", str(stub))
        base = self.head()
        self.raw_commit(b"gpgsig -----BEGIN PGP SIGNATURE-----\n \n abc\n -----END PGP SIGNATURE-----\n", b"clean\n")
        code, out, err = self.run_check(["acme-leak"], range_spec="%s..HEAD" % base)
        self.assertFalse(marker.exists())
        self.assertEqual((code, out), (0, ""))

    def test_a_file_named_after_a_commit_does_not_abort_the_range(self):
        base = self.head()
        self.commit("b.md", "clean\n")
        (self.repo / self.head()).write_text("x\n")
        code, out, err = self.run_check(["zzz"], range_spec="%s..HEAD" % base)
        self.assertEqual((code, out), (0, ""), err)

    def commit_raw_name(self, name, text):
        sha = subprocess.run(["git", "-C", str(self.repo), "hash-object", "-w", "--stdin"], input=text, check=True,
                             capture_output=True, env=ENV).stdout.decode().strip()
        git(self.repo, "update-index", "--add", "--cacheinfo", b"100644,%s,%s" % (sha.encode(), name))
        git(self.repo, "commit", "-q", "-m", "y")

    def test_non_utf8_file_name(self):
        self.commit_raw_name(b"caf\xe9.md", b"acme\n")
        code, out, err = self.run_check(["acme"])
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("caf\\xe9.md:1: acme", out.splitlines())

    def test_escaped_lookalike_name_stays_distinct(self):
        self.commit_raw_name(b"caf\xe9.md", b"acme\n")
        self.commit("caf\\xe9.md", "acme\n")
        code, out, _ = self.run_check(["acme"])
        self.assertIn("caf\\xe9.md:1: acme", out.splitlines())
        self.assertIn("caf\\\\xe9.md:1: acme", out.splitlines())

    def test_unicode_line_breaks_and_bidi_are_escaped(self):
        for char, escaped in ((" ", "\\u2028"), ("‮", "\\u202e"), ("\x85", "\\u0085")):
            with self.subTest(escaped=escaped):
                self.commit("u%s.md" % char, "acme\n")
                code, out, _ = self.run_check(["acme"])
                self.assertEqual(len(out.splitlines()), out.count("\n"))
                self.assertIn("u%s.md:1: acme" % escaped, out.splitlines())

    def safe_env(self, system="", global_="", **extra):
        sysf = self.home / "syscfg"
        sysf.write_text(system)
        gf = self.home / "safecfg"
        gf.write_text(global_)
        return {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1", "GIT_CONFIG_SYSTEM": str(sysf), "GIT_CONFIG_GLOBAL": str(gf),
                **extra}

    def assert_trust_matches_git(self, env, drop=(), cwd=None):
        plain_env = {k: v for k, v in ENV.items() if k not in drop}
        plain_env.update(env)
        plain = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--show-toplevel"], capture_output=True,
                               env=plain_env, cwd=cwd).returncode
        code, out, _ = self.run_check(["acme"], env=env, drop=drop, cwd=cwd)
        if plain == 0:
            self.assertEqual((code, out.splitlines()), (1, ["a.md:1: acme"]))
        else:
            self.assertEqual((plain, code, out), (128, 2, ""))
        return plain

    def test_safe_directory_in_global_config_is_trusted(self):
        self.assertEqual(self.assert_trust_matches_git(self.safe_env(global_="[safe]\n\tdirectory = *\n")), 0)

    def test_no_safe_directory_entry_is_rejected(self):
        self.assertEqual(self.assert_trust_matches_git(self.safe_env()), 128)

    def test_global_empty_reset_cancels_system_safe_directory(self):
        env = self.safe_env(system="[safe]\n\tdirectory = *\n", global_="[safe]\n\tdirectory =\n")
        self.assertEqual(self.assert_trust_matches_git(env), 128)

    def test_no_system_config_hides_system_safe_directory(self):
        for value in ("1", "2"):
            with self.subTest(value=value):
                env = self.safe_env(system="[safe]\n\tdirectory = *\n", GIT_CONFIG_NOSYSTEM=value)
                self.assertEqual(self.assert_trust_matches_git(env), 128)

    def test_safe_directory_in_included_file_is_trusted(self):
        inc = self.home / "inc.cfg"
        inc.write_text("[safe]\n\tdirectory = *\n")
        self.assertEqual(self.assert_trust_matches_git(self.safe_env(global_="[include]\n\tpath = %s\n" % inc)), 0)

    def test_xdg_config_is_read_next_to_home_gitconfig(self):
        fake = self.home / "fakehome"
        (fake / "xdg" / "git").mkdir(parents=True)
        (fake / ".gitconfig").write_text("[user]\n\tname = x\n")
        (fake / "xdg" / "git" / "config").write_text("[safe]\n\tdirectory = *\n")
        sysf = self.home / "syscfg"
        sysf.write_text("")
        env = {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1", "GIT_CONFIG_SYSTEM": str(sysf), "HOME": str(fake),
               "XDG_CONFIG_HOME": str(fake / "xdg")}
        self.assertEqual(self.assert_trust_matches_git(env, drop=("GIT_CONFIG_GLOBAL",)), 0)

    def test_include_if_gitdir_follows_git(self):
        other = self.home / "other"
        other.mkdir()
        git(other, "init", "-q")
        other = other.resolve()
        grant = self.home / "grant.cfg"
        grant.write_text("[safe]\n\tdirectory = *\n")
        gcfg = '[safe]\n\tdirectory = %s\n[includeIf "gitdir:%s/"]\n\tpath = %s\n' % (other, other, grant)
        self.assertEqual(self.assert_trust_matches_git(self.safe_env(global_=gcfg), cwd=other), 128)

    def test_directory_name_ending_in_newline_keeps_it(self):
        def make(name, file):
            path = self.home / name
            try:
                path.mkdir()
            except OSError:
                self.skipTest("file system refuses a newline in a directory name")
            git(path, "init", "-q")
            (path / file).write_text("acme\n")
            git(path, "add", file)
            git(path, "commit", "-q", "-m", "n")
            return path.resolve()
        newline = make("foo\n", "n.md")
        make("foo", "s.md")
        gcfg = '[safe]\n\tdirectory = "%s"\n' % str(newline).replace("\n", "\\n")
        env = self.safe_env(global_=gcfg)
        code, out, _ = self.run_check(["acme"], repo=newline, env=env)
        self.assertEqual((code, out.splitlines()), (1, ["n.md:1: acme"]))

    def test_directory_name_ending_in_space_is_scanned(self):
        spaced = self.home / "spaced "
        spaced.mkdir()
        git(spaced, "init", "-q")
        (spaced / "s.md").write_text("acme\n")
        git(spaced, "add", "s.md")
        git(spaced, "commit", "-q", "-m", "s")
        code, out, _ = self.run_check(["acme"], repo=spaced)
        self.assertEqual((code, out.splitlines()), (1, ["s.md:1: acme"]))

    def test_raw_byte_and_code_point_print_differently(self):
        self.commit_raw_name(b"r\x85.md", b"acme\n")
        self.commit("r\u0085.md", "acme\n")
        code, out, _ = self.run_check(["acme"])
        self.assertIn("r\\x85.md:1: acme", out.splitlines())
        self.assertIn("r\\u0085.md:1: acme", out.splitlines())

    def test_git_attr_source_is_ignored(self):
        git(self.repo, "checkout", "-q", "-b", "attrs")
        self.commit(".gitattributes", "* binary\n")
        git(self.repo, "checkout", "-q", "-")
        code, out, _ = self.run_check(["acme"], env={"GIT_ATTR_SOURCE": "attrs"})
        self.assertEqual((code, out.splitlines()), (1, ["a.md:1: acme"]))

    def test_global_config_and_xdg_attributes_are_ignored(self):
        attrs = self.home / "gattrs"
        attrs.write_text("* binary\n")
        gcfg = self.home / "gitconfig"
        gcfg.write_text("[core]\n\tattributesFile = %s\n" % attrs)
        code, out, _ = self.run_check(["acme"], env={"GIT_CONFIG_GLOBAL": str(gcfg)})
        self.assertEqual((code, out.splitlines()), (1, ["a.md:1: acme"]))
        xdg = self.home / "xdg"
        (xdg / "git").mkdir(parents=True)
        (xdg / "git" / "attributes").write_text("*.md binary\n")
        code, out, _ = self.run_check(["acme"], env={"XDG_CONFIG_HOME": str(xdg)})
        self.assertEqual((code, out.splitlines()), (1, ["a.md:1: acme"]))


class AsciiStdout(unittest.TestCase):
    def test_check_neutral_hits_print_on_an_ascii_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            repo, home = tmp / "repo", tmp / "home"
            repo.mkdir()
            home.mkdir()
            (repo / "note.txt").write_text("caf\u00e9\n", encoding="utf-8")
            git(repo, "init", "-q")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "x")
            (home / "tl-relay.yaml").write_text('neutrality:\n  patterns: ["caf\u00e9"]\n', encoding="utf-8")
            env = dict(ENV, TL_RELAY_HOME=str(home), PYTHONIOENCODING="ascii")
            env.pop("TL_RELAY_REPO", None)
            done = subprocess.run([sys.executable, str(pathlib.Path(sdlc.__file__)), "check-neutral", "--repo", str(repo)],
                                  capture_output=True, env=env)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn(b"caf\\xe9", done.stdout)
        self.assertNotIn(b"Traceback", done.stderr)


if __name__ == "__main__":
    unittest.main()
