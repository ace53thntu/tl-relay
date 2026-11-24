import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from overlap import UPSTREAM, line_hash, normalise  # noqa: E402

SUPERPOWERS_COMMIT = "22f0b463e7a5e579904dd6211a520321035526f7"


def hashes_under(root):
    found = set()
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line in text.splitlines():
            normalised = normalise(line)
            if normalised is not None:
                found.add(line_hash(normalised))
    return found


def commit_of(directory):
    return subprocess.run(
        ["git", "-C", directory, "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def main(superpowers_dir, agent_skills_dir, skill_creator_dir):
    digests = (
        hashes_under(pathlib.Path(superpowers_dir))
        | hashes_under(pathlib.Path(agent_skills_dir))
        | hashes_under(pathlib.Path(skill_creator_dir))
    )
    header = [
        f"# superpowers 7.0.2 {SUPERPOWERS_COMMIT}",
        f"# agent-skills {commit_of(agent_skills_dir)}",
        f"# skill-creator {commit_of(skill_creator_dir)}",
    ]
    UPSTREAM.write_text("\n".join(header + sorted(digests)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(
            "usage: make-upstream-hashes.py <superpowers-dir> <agent-skills-dir>"
            " <skill-creator-dir>"
        )
    main(sys.argv[1], sys.argv[2], sys.argv[3])
