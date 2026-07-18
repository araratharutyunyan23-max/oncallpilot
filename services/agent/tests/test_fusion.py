from app.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_combines_and_orders():
    dense = [1, 2, 3]
    sparse = [3, 4, 1]
    fused = reciprocal_rank_fusion([dense, sparse], k=60)
    ids = [i for i, _ in fused]
    # 1 and 3 each appear in both arms → they should top the fusion
    assert set(ids[:2]) == {1, 3}
    assert reciprocal_rank_fusion([dense, sparse], k=60) == fused  # deterministic


def test_rrf_single_list_preserves_order():
    assert [i for i, _ in reciprocal_rank_fusion([[5, 6, 7]])] == [5, 6, 7]


def test_rrf_empty():
    assert reciprocal_rank_fusion([]) == []
