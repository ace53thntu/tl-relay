"""Two-layer configuration: a neutral repo file merged with the home file."""
import os
import pathlib

from runtime import yamlio

MAPPING_BLOCKS = ("project", "install", "tracker", "neutrality")


class ConfigError(Exception):
    pass


HOME_VARS = ("TL_RELAY_HOME", "AI_SDLC_HOME")
HOME_FILES = ("tl-relay.yaml", "ai-sdlc.yaml")


def default_home():
    for name in HOME_VARS:
        if os.environ.get(name):
            return pathlib.Path(os.environ[name])
    home = pathlib.Path.home()
    if not (home / ".tl-relay").exists() and (home / ".ai-sdlc").exists():
        return home / ".ai-sdlc"
    return home / ".tl-relay"


def default_repo():
    return pathlib.Path(os.environ.get("TL_RELAY_REPO") or pathlib.Path(__file__).resolve().parents[2])


def home_file(home):
    for name in HOME_FILES:
        if (pathlib.Path(home) / name).is_file():
            return pathlib.Path(home) / name
    return pathlib.Path(home) / HOME_FILES[0]


def merge(repo_doc, home_doc):
    merged = dict(repo_doc)
    for key, value in home_doc.items():
        if value is None and key in merged:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def check_blocks(doc, path):
    for key in MAPPING_BLOCKS:
        if key in doc and doc[key] is not None and not isinstance(doc[key], dict):
            raise ConfigError("%s: %s must be a mapping" % (path, key))


def _read(path):
    if not path.is_file():
        return {}
    try:
        doc = yamlio.load(path)
    except yamlio.YamlError as exc:
        raise ConfigError("%s: %s" % (path, exc))
    if not isinstance(doc, dict):
        raise ConfigError("%s: the top level must be a mapping" % path)
    check_blocks(doc, path)
    return doc


def load(repo, home):
    return merge(_read(pathlib.Path(repo) / "maintainer" / "tl-relay.yaml"), _read(home_file(home)))
