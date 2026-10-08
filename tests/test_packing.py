from app.services.packing import pack, split_header


def test_merge_adjacent_with_overlap():
    overlap = "X" * 150
    chunks = [
        {"chunk_id": 1, "filing_id": 1, "position": 1, "header": "H1", "text": "A" * 50 + overlap},
        {"chunk_id": 2, "filing_id": 1, "position": 2, "header": "H1", "text": overlap + "B" * 50},
    ]
    res = pack(chunks)
    assert len(res["blocks"]) == 1
    assert res["blocks"][0]["chunk_ids"] == [1, 2]
    assert res["context"].count(overlap) == 1


def test_non_adjacent_do_not_merge():
    chunks = [
        {"chunk_id": 1, "filing_id": 1, "position": 1, "header": "H1", "text": "Chunk one text."},
        {"chunk_id": 2, "filing_id": 1, "position": 5, "header": "H1", "text": "Chunk two text."},
    ]
    assert len(pack(chunks)["blocks"]) == 2


def test_different_filings_never_merge():
    chunks = [
        {"chunk_id": 1, "filing_id": 1, "position": 1, "header": "H1", "text": "Apple revenue increased significantly this year."},
        {"chunk_id": 2, "filing_id": 2, "position": 1, "header": "H2", "text": "Microsoft net income dropped slightly this quarter."},
    ]
    assert len(pack(chunks)["blocks"]) == 2


def test_duplicate_block_skipped():
    text = "This is a unique sentence about revenue growth."
    chunks = [
        {"chunk_id": 1, "filing_id": 1, "position": 1, "header": "H1", "text": text},
        {"chunk_id": 2, "filing_id": 2, "position": 1, "header": "H2", "text": text},
    ]
    res = pack(chunks)
    assert len(res["blocks"]) == 1
    assert res["blocks"][0]["chunk_ids"] == [1]


def test_budget_stops_correctly():
    chunks = [
        {"chunk_id": 1, "filing_id": 1, "position": 1, "header": "H1", "text": "A" * 100},
        {"chunk_id": 2, "filing_id": 2, "position": 1, "header": "H2", "text": "B" * 100},
    ]
    res = pack(chunks, char_budget=150)
    assert len(res["blocks"]) == 1
    assert res["blocks"][0]["chunk_ids"] == [1]


def test_top_1_exceeds_budget_is_truncated():
    chunks = [{"chunk_id": 1, "filing_id": 1, "position": 1, "header": "H1", "text": "A" * 500}]
    res = pack(chunks, char_budget=100)
    assert len(res["blocks"]) == 1
    assert res["blocks"][0]["truncated"] is True
    assert len(res["blocks"][0]["text"]) <= 100


def test_empty_input():
    res = pack([])
    assert res["context"] == ""
    assert res["blocks"] == []


def test_split_header():
    header, body = split_header("MICROSOFT CORP (MSFT) 10-K | Item 8. Financials\nbody text")
    assert header == "MICROSOFT CORP (MSFT) 10-K | Item 8. Financials"
    assert body == "body text"
    assert split_header("no header here") == ("", "no header here")