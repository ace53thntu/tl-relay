# Lesson files

- The file is `<home>/lessons/<owner>.md`.
- Write the lesson line in English, like the skills. Each lesson is exactly two lines: `- <id> · <YYYY-MM-DD> · When <condition>, <action>.` then `  source: <session> <YYYY-MM-DDTHH:MM> · seen: <n>`.
- Get `<id>` from `ledger.py next-id --kind lesson --target <file>`. Write it exactly as printed. The file holds lesson lines only, no heading.
- A lesson matching an existing one merges into it: bump `seen` and set the source line to the newest sighting.
- A file holds at most 20 lessons. Before adding one to a full file, delete the lesson whose source line has the oldest timestamp, run `ledger.py drop --id <that id> --target <file>`, and list the drop in the report.
- After each write, run `ledger.py record --id <id> --kind lesson --target <file> --text "<the lesson in operator_language>"`. The notification shows that text.
