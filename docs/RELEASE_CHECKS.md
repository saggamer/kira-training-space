# Release verification

- 28 Python unit tests pass against the standalone release tree.
- Browser verification passed for responsive layout, category and search filters,
  live source-revision file links, starter and plugin downloads, browser-local
  inspection/history, escaping and the 1080p video metadata.
- The website does not POST uploaded dataset contents. History stores filenames,
  counts and timestamps only in the visitor's local browser storage.
- Local Soup SFT and DPO preflights were verified during development. Full GPU
  training was not executed for this release.
- Distribution is curated from the plugin allowlist. Personal installation paths,
  workspace data, SQLite files and private run logs are excluded.
- Proprietary font files are excluded; the website uses system font stacks.
