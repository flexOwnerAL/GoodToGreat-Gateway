from app.utils.tokens import estimate_tokens, usage_block


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_nonempty():
    assert estimate_tokens("hello") >= 1


def test_usage_block_shape():
    block = usage_block("hello world", "answer here")
    assert block["total_tokens"] == block["prompt_tokens"] + block["completion_tokens"]
    assert block["prompt_tokens"] >= 1
    assert block["completion_tokens"] >= 1
