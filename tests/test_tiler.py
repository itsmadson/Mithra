import pytest
from bina_worker.tiler import MAX_SIDE, split_bbox


def test_small_bbox_returns_itself():
    bbox = (59.600, 36.293, 59.605, 36.298)
    assert split_bbox(bbox) == [bbox]


def test_large_bbox_is_split():
    bbox = (59.60, 36.29, 59.64, 36.33)
    tiles = split_bbox(bbox)
    assert len(tiles) > 1


def test_every_tile_is_under_the_api_limit():
    bbox = (59.60, 36.29, 59.64, 36.33)
    for w, s, e, n in split_bbox(bbox):
        assert e - w < 0.01
        assert n - s < 0.01


def test_tiles_cover_the_whole_bbox():
    w0, s0, e0, n0 = (59.60, 36.29, 59.64, 36.33)
    tiles = split_bbox((w0, s0, e0, n0))
    assert min(t[0] for t in tiles) == pytest.approx(w0)
    assert min(t[1] for t in tiles) == pytest.approx(s0)
    assert max(t[2] for t in tiles) == pytest.approx(e0)
    assert max(t[3] for t in tiles) == pytest.approx(n0)


def test_tiles_do_not_overlap():
    tiles = split_bbox((59.60, 36.29, 59.64, 36.33))
    assert len(tiles) == len(set(tiles))
    xs = sorted({(t[0], t[2]) for t in tiles})
    for (_, prev_e), (next_w, _) in zip(xs, xs[1:]):
        assert prev_e == pytest.approx(next_w)


def test_bbox_exactly_on_the_limit_is_split():
    # 0.01 is NOT strictly smaller than 0.01, so it must be split.
    tiles = split_bbox((59.60, 36.29, 59.61, 36.30))
    assert len(tiles) > 1
    for w, _, e, _ in tiles:
        assert e - w < 0.01


def test_max_side_is_below_the_api_limit():
    assert MAX_SIDE < 0.01


def test_inverted_bbox_raises():
    with pytest.raises(ValueError):
        split_bbox((59.64, 36.29, 59.60, 36.33))


def test_degenerate_bbox_raises():
    with pytest.raises(ValueError):
        split_bbox((59.60, 36.29, 59.60, 36.33))
