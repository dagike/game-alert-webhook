from gamealert.sources.base import Item
from gamealert.state import State


def item(id, source="free_games"):
    return Item(source=source, id=id, title=f"Game {id}")


def test_new_then_sent():
    s = State(":memory:")
    a, b = item("a"), item("b")
    assert s.filter_new([a, b]) == [a, b]
    s.mark_sent([a])
    assert s.filter_new([a, b]) == [b]


def test_same_id_different_source_is_separate():
    s = State(":memory:")
    s.mark_sent([item("a", "ps_plus")])
    assert s.filter_new([item("a", "free_games")]) == [item("a", "free_games")]


def test_duplicates_in_one_list_count_once():
    s = State(":memory:")
    assert len(s.filter_new([item("a"), item("a")])) == 1


def test_persists_on_disk(tmp_path):
    p = tmp_path / "sub" / "state.db"
    s = State(p)
    s.mark_sent([item("a")])
    s.close()
    assert State(p).is_sent(item("a"))
