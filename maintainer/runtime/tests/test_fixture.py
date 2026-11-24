import pathlib
import subprocess
import sys
import unittest

import fixture


class SymlinkSkipTest(unittest.TestCase):
    def test_symlink_tests_skip_without_symlink_rights(self):
        here = pathlib.Path(__file__).resolve().parent
        names = [
            "test_install.Install.test_env_writes_project_root_resolved",
            "test_install.Install.test_symlink_loop_in_a_config_dir_is_a_refusal",
            "test_install.Install.test_unreadable_target_refuses_before_any_write",
            "test_install.Install.test_symlinked_user_settings_stays_a_symlink",
            "test_install.Install.test_failed_install_keeps_a_broken_symlink_as_a_symlink",
        ]
        code = (
            "import os, sys, unittest\n"
            "def deny(*a, **k):\n"
            "    raise OSError(1314, 'A required privilege is not held by the client')\n"
            "os.symlink = deny\n"
            f"sys.path[:0] = [{str(here)!r}, {str(here.parents[1])!r}]\n"
            f"suite = unittest.defaultTestLoader.loadTestsFromNames({names!r})\n"
            "r = unittest.TextTestRunner(stream=open(os.devnull, 'w')).run(suite)\n"
            "print(r.testsRun, len(r.skipped), len(r.errors), len(r.failures))\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual((proc.returncode, proc.stdout), (0, "5 6 0 0\n"), proc.stderr)


if __name__ == "__main__":
    unittest.main()
