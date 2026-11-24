# Memories

Write to `<config>/projects/<record project>/memory/`. `<config>` is the `--config-dir` you passed, else `$CLAUDE_CONFIG_DIR`, else `~/.claude`.

- Frontmatter holds `name`, `description`, `metadata.type: feedback` and `metadata.source: retro`. Write `description` as a plain unquoted value.
- The body opens with `retro_id: <id>` from `ledger.py next-id --kind memory --target <file>`, then the fact, **Why:** and **How to apply:**.
- Add one pointer line to `MEMORY.md`. A file that carries `metadata.source: retro` and covers the same fact gets updated instead. Any other file that covers it means write nothing.
- Then run `ledger.py record --id <id> --kind memory --target <file> --text "<the fact in operator_language>"`.
