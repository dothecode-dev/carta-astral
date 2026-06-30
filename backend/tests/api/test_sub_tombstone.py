import pytest


def test_sub_hash_is_deterministic_sha256():
    from api.identity import sub_hash

    h = sub_hash("apple", "X")
    assert h == sub_hash("apple", "X")
    assert h != sub_hash("google", "X")
    assert len(h) == 64


@pytest.mark.django_db
def test_tombstone_unique_per_sub_hash():
    from django.db import IntegrityError
    from api.models import SubTombstone

    SubTombstone.objects.create(sub_hash="h", free_credits_consumed=1)
    with pytest.raises(IntegrityError):
        SubTombstone.objects.create(sub_hash="h", free_credits_consumed=1)
