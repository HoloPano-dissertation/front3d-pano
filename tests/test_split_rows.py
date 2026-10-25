import pytest

from front3d_pano.dataset.rows import index_rows


def test_house_leakage_is_rejected():
    rows = [{"room_id": "a/keep", "house_id": "a", "split": "train"},
            {"room_id": "a/other", "house_id": "a", "split": "test"}]
    with pytest.raises(ValueError, match="House leakage"):
        index_rows(rows)


def test_duplicate_room_is_rejected():
    rows = [{"room_id": "a/keep", "house_id": "a", "split": "train"}] * 2
    with pytest.raises(ValueError, match="Duplicate room"):
        index_rows(rows)


def test_unknown_split_is_rejected():
    with pytest.raises(ValueError, match="Unknown split"):
        index_rows([{"room_id": "a/keep", "house_id": "a", "split": "excluded"}])
