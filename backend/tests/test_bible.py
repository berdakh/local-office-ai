from app.transcribe import Bible, check_text, find_scripture_refs, format_checks

TINY = Bible(
    {
        "John": {"3": {"16": "For God so loved the world...", "17": "For God didn't send..."}},
        "Psalms": {"23": {"1": "Yahweh is my shepherd: I shall lack nothing."}},
        "Song of Solomon": {"1": {"1": "The Song of songs, which is Solomon's."}},
    },
    version="TEST",
)


def test_verified_single_verse():
    c = TINY.check(find_scripture_refs("John 3:16")[0])
    assert c.status == "verified" and c.text.startswith("For God so loved")


def test_verified_range_numbers_verses():
    c = TINY.check(find_scripture_refs("John 3:16-17")[0])
    assert c.status == "verified" and c.text.startswith("16 For God") and "17 For God" in c.text


def test_missing_verse_and_chapter():
    assert TINY.check(find_scripture_refs("John 3:99")[0]).status == "not_found"
    assert TINY.check(find_scripture_refs("John 4:1")[0]).status == "not_found"
    assert TINY.check(find_scripture_refs("Acts 2:1")[0]).status == "not_found"


def test_chapter_only_reference():
    c = TINY.check(find_scripture_refs("Psalm 23")[0])
    assert c.status == "verified" and c.text is None and "1 verses" in c.note


def test_song_of_songs_alias_resolves():
    c = TINY.check(find_scripture_refs("Song of Songs 1:1")[0])
    assert c.status == "verified"


def test_check_text_without_bible_is_unverified():
    checks = check_text("Romans 8:28 and John 3:16", None)
    assert [c.status for c in checks] == ["unverified", "unverified"]


def test_format_checks_marks_not_found():
    out = format_checks(check_text("John 3:16 and John 3:99", TINY), "TEST")
    assert "John 3:16 (TEST): For God so loved" in out
    assert "John 3:99: NOT FOUND" in out
