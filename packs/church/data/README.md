# Pack data

`web.json`: the World English Bible (public domain), produced by
`uv run python scripts/fetch_bible.py`. Used to verify scripture references
found in transcripts and to give the model the exact text so it never invents a
quotation. Git-ignored; about 5 MB. Fetched once at install time.
