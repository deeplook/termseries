# Obsidian daily notes

The `obsidian` subcommand plots numeric fields tracked in the YAML
frontmatter of Obsidian daily notes -- one point per day, one curve per
field. Point it at a daily-notes folder (top-level `.md` files only, not
recursive) with `:field1,field2` appended to select which frontmatter keys
to plot; fields are mandatory, they're never auto-expanded, since daily
notes tend to accumulate plenty of incidental numeric-looking keys
(streak counts, word counts) that would make an auto-plotted chart noisy.

```markdown
---
mood: 7
weight: 72.5
---

Today was productive...
```

Each note's date comes from its filename (`YYYY-MM-DD.md`, the Obsidian
Daily Notes / Periodic Notes plugin convention) or, for notes with a
different name, a `date:` frontmatter key as a fallback. Notes with neither
are silently skipped, so templates and one-off notes in the same folder
don't break the scan. A field missing from *some* notes -- or present but
left empty (`exercise-dumbbells:` with nothing after the colon, the common
habit-tracker-template pattern of a key that's always there but only filled
in on days it applies) -- is skipped silently too. A field present with an
actual non-numeric value (a string, a list, etc.) raises instead, since
that's more likely a mistake worth seeing than data worth silently
dropping.

```bash
termseries obsidian ~/vault/Daily:mood,weight --last 90d
```

The same `--last`/`--from`/`--to`/`--first` time-range syntax as every
other subcommand applies, plus `--unit` to set the y-axis label. When the
same field is requested from two different directories in one command, the
second one is labelled `<dirname>.<field>` to disambiguate.
