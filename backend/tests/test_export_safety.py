from backend.app.export_static import public_only


def test_public_only_removes_secrets_and_free_text_nested():
    original = {'price_couple': 6300, 'extras': [
        {'notes': 'texto particular', 'api_key': 'CHAVE-SENSIVEL',
         'smtp_password': 'SENHA', 'estimated_total': 6500}],
         'data_json': '{"departure_token":"secreto"}'}
    result = public_only(original)
    assert result == {'price_couple': 6300, 'extras': [{'estimated_total': 6500}]}
