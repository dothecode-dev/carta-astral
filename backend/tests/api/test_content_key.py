from api.interpretation_service import content_key


def test_distinto_tier_genera_distinto_hash():
    """El hash incluye el tier: mismo input con tier distinto produce hashes
    distintos. Sin esto, un informe completo pagado podría reutilizar el texto
    de una lectura breve de otra carta con los mismos datos de nacimiento."""
    chart_data = {"placements": []}
    lang = "es"
    prompt_version = "v2"

    hash_corto = content_key(chart_data, lang, prompt_version, tier="corto")
    hash_largo = content_key(chart_data, lang, prompt_version, tier="largo")

    assert hash_corto != hash_largo


def test_mismo_tier_genera_mismo_hash():
    """Mismo input, mismo tier, mismo hash. Verifica que la función es
    determinística y puede reutilizar lectura entre cartas idénticas del
    mismo producto."""
    chart_data = {"placements": []}
    lang = "es"
    prompt_version = "v2"

    hash_1 = content_key(chart_data, lang, prompt_version, tier="largo")
    hash_2 = content_key(chart_data, lang, prompt_version, tier="largo")

    assert hash_1 == hash_2
