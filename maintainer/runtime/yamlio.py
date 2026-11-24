"""Reads and writes the YAML subset the ai-sdlc config uses."""
import atexit
import copy
import json
import os
import pathlib
import subprocess

RUBY = "/usr/bin/ruby"


class YamlError(Exception):
    pass


# safe_load builds no tagged object. A timestamp written without quotes comes back as ISO 8601 text.
SCRIPT = (
    "conv = lambda { |v| case v; when Hash then v.map { |k, x| [k.to_s, conv.call(x)] }.to_h; "
    "when Array then v.map { |x| conv.call(x) }; when Time, Date then v.iso8601; "
    "when Float then v.finite? ? v : v.to_s; else v; end }; "
    "STDOUT.sync = true; while (line = STDIN.gets); "
    "puts JSON.generate(JSON.parse(line).map { |f| begin; "
    "{'doc' => conv.call(YAML.safe_load(File.read(f), permitted_classes: [Time, Date], aliases: true))}; "
    "rescue StandardError, SyntaxError => e; {'error' => e.message}; end }); end"
)

_PROC = None


def _close():
    global _PROC
    proc, _PROC = _PROC, None
    if proc is None:
        return
    proc.kill()
    proc.wait()
    for pipe in (proc.stdin, proc.stdout):
        try:
            pipe.close()
        except OSError:
            pass


atexit.register(_close)


def _process():
    global _PROC
    if _PROC is None or _PROC.poll() is not None:
        _close()
        _PROC = subprocess.Popen([RUBY, "-ryaml", "-rjson", "-rtime", "-rdate", "-e", SCRIPT],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return _PROC


def _exchange(proc, paths):
    proc.stdin.write((json.dumps([os.path.abspath(p) for p in paths]) + "\n").encode())
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise OSError("the Ruby process closed its output")
    return json.loads(line)


_CACHE = {}


def _stamp(path):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size, stat.st_ino)


def load_many(paths):
    """Parses the files that changed since they were last read, all in one process."""
    paths = [str(p) for p in paths]
    stamps = {path: _stamp(path) for path in paths}
    stale = [p for p in dict.fromkeys(paths) if stamps[p] is None or _CACHE.get(p, (None, None))[0] != stamps[p]]
    for path, doc in zip(stale, _parse(stale)):
        _CACHE[path] = (stamps[path], doc)
    return [copy.deepcopy(_CACHE[path][1]) for path in paths]


def _parse(paths):
    if not paths:
        return []
    # This machine has no YAML parser for Python; the system Ruby ships one.
    for attempt in range(2):
        try:
            results = _exchange(_process(), paths)
            break
        except (OSError, ValueError) as exc:
            _close()
            if attempt:
                raise YamlError("cannot read %s: %s" % (", ".join(paths), exc))
        except BaseException:
            _close()
            raise
    for path, result in zip(paths, results):
        if "error" in result:
            raise YamlError("cannot read %s: %s" % (path, result["error"]))
    return [result["doc"] for result in results]


def load(path):
    return load_many([path])[0]


_ESCAPED = {code: "\\u%04x" % code for code in [*range(0x7f, 0xa0), 0x2028, 0x2029, 0xfffe, 0xffff]}


def _scalar(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # A JSON string is a valid YAML double-quoted scalar, newlines included.
    return json.dumps(str(value), ensure_ascii=False).translate(_ESCAPED)


def _lines(value, indent):
    pad = "  " * indent
    lines = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)) and item:
                lines.append("%s%s:" % (pad, key))
                lines.extend(_lines(item, indent + 1))
            elif isinstance(item, (dict, list)):
                lines.append("%s%s: %s" % (pad, key, "{}" if isinstance(item, dict) else "[]"))
            else:
                lines.append("%s%s: %s" % (pad, key, _scalar(item)))
    else:
        for item in value:
            if isinstance(item, dict) and item:
                body = _lines(item, indent + 1)
                lines.append("%s- %s" % (pad, body[0].lstrip()))
                lines.extend(body[1:])
            elif isinstance(item, list):
                raise YamlError("a list inside a list is not supported")
            else:
                lines.append("%s- %s" % (pad, "{}" if isinstance(item, dict) else _scalar(item)))
    return lines


def dump(doc):
    if not isinstance(doc, dict):
        raise YamlError("the top level must be a mapping")
    return "\n".join(_lines(doc, 0)) + "\n"


def write(path, doc):
    """Writes through a temporary file, so a reader never sees half a document."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(dump(doc))
    os.replace(str(temporary), str(path))
