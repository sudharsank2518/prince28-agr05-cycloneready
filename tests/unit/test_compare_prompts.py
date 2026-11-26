from scripts.compare_prompts import confusion_table


def test_confusion_table_counts_actual_and_predicted_labels():
    rows = [
        {"label": "docs", "got": "docs"},
        {"label": "docs", "got": "personal"},
        {"label": "personal", "got": "personal"},
        {"label": "personal", "got": "invalid"},
        {"label": "off_topic", "got": "docs"},
        {"label": "docs", "error": "API failed"},
    ]

    table = confusion_table(rows)

    assert table["docs"]["docs"] == 1
    assert table["docs"]["personal"] == 1
    assert table["personal"]["personal"] == 1
    assert table["personal"]["invalid"] == 1
    assert table["off_topic"]["docs"] == 1
    assert sum(sum(counts.values()) for counts in table.values()) == 5
