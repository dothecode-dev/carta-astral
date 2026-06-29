from api.text_norm import normalize, tokenize


def test_normalize_lowercases_and_strips_spanish_accents():
    assert normalize("Córdoba") == "cordoba"


def test_normalize_transliterates_latin_extended():
    # NFKD no resolvía estos: ø/ł no son combining marks.
    assert normalize("Tromsø") == "tromso"
    assert normalize("Łódź") == "lodz"
    assert normalize("Straße") == "strasse"


def test_normalize_collapses_internal_whitespace():
    assert normalize("  San   Carlos  de  Bariloche ") == "san carlos de bariloche"


def test_tokenize_splits_into_normalized_words():
    assert tokenize("San Carlos de Bariloche") == ["san", "carlos", "de", "bariloche"]


def test_tokenize_drops_empty_tokens():
    assert tokenize("   ") == []
