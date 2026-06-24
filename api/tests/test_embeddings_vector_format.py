from hireloop_api.services.embeddings import _format_vector


def test_format_vector_outputs_pgvector_literal() -> None:
    assert _format_vector([0.1, -0.25, 1.0]) == "[0.1,-0.25,1.0]"
