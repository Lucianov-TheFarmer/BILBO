from __future__ import annotations

from typing import Any

from . import literature
from .common import (
    ANNOTATE_LITERATURE_ENTITIES,
    BATCH_SIZE,
    BM25_METADATA_PATH,
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    LITERATURE_ENTITY_BATCH_SIZE,
    LITERATURE_ENTITY_PATTERN_FILE,
    QDRANT_API_KEY,
    QDRANT_URL,
    RESET_COLLECTION,
    SPARSE_VECTOR_NAME,
    bm25_sparse_vector,
    build_bm25_model,
    embed_texts,
    tokenize_for_bm25,
    write_bm25_model,
)
from .literature import chunk_article, iter_chunks

__all__ = [
    "bm25_sparse_vector",
    "build_bm25_model",
    "chunk_article",
    "embed_texts",
    "iter_chunks",
    "tokenize_for_bm25",
]


def create_qdrant_client(
    qdrant_url: str = QDRANT_URL,
    api_key: str | None = QDRANT_API_KEY,
) -> Any:
    from qdrant_client import QdrantClient

    return QdrantClient(url=qdrant_url, api_key=api_key)


def create_collection(
    dense_vector_size: int,
    collection_name: str = COLLECTION_NAME,
    qdrant_url: str = QDRANT_URL,
    api_key: str | None = QDRANT_API_KEY,
    reset_collection: bool = RESET_COLLECTION,
) -> Any:
    from qdrant_client import models

    client = create_qdrant_client(qdrant_url=qdrant_url, api_key=api_key)
    if reset_collection and client.collection_exists(collection_name):
        client.delete_collection(collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=dense_vector_size,
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
    )
    return client


def build_literature_entity_annotator() -> Any | None:
    if not ANNOTATE_LITERATURE_ENTITIES:
        return None
    return literature.load_annotator(LITERATURE_ENTITY_PATTERN_FILE)


def index_chunks(
    client: Any,
    collection_name: str,
    chunks: list[dict[str, Any]],
    bm25_model: dict[str, Any],
    batch_size: int,
    annotator: Any | None = None,
) -> None:
    from qdrant_client import models

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        embeddings = embed_texts([chunk["text"] for chunk in batch])
        annotations = (
            literature.annotate_many(
                annotator,
                [chunk["text"] for chunk in batch],
                batch_size=LITERATURE_ENTITY_BATCH_SIZE,
            )
            if annotator is not None
            else [{} for _ in batch]
        )
        points = []
        for offset, (chunk, embedding, annotation) in enumerate(
            zip(batch, embeddings, annotations),
            start=start + 1,
        ):
            sparse_indices, sparse_values = bm25_sparse_vector(chunk["text"], bm25_model)
            points.append(
                models.PointStruct(
                    id=offset,
                    vector={
                        DENSE_VECTOR_NAME: embedding,
                        SPARSE_VECTOR_NAME: models.SparseVector(
                            indices=sparse_indices,
                            values=sparse_values,
                        ),
                    },
                    payload={
                        **chunk["metadata"],
                        **annotation,
                        "chunk_id": chunk["id"],
                        "text": chunk["text"],
                    },
                )
            )
        client.upsert(collection_name=collection_name, points=points)
        batch_number = start // batch_size + 1
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        indexed = min(start + batch_size, len(chunks))
        if batch_number == 1 or batch_number == total_batches or batch_number % 50 == 0:
            print(f"Indexados {indexed}/{len(chunks)} chunks")


def main() -> None:
    chunks = iter_chunks()
    print(f"Total de chunks: {len(chunks)}")
    if not chunks:
        raise ValueError("Nenhum chunk gerado; verifique artigos e filtros de indexacao.")

    annotator = build_literature_entity_annotator()
    if annotator is not None:
        print("Anotador de entidades carregado")

    dense_vector_size = len(embed_texts([chunks[0]["text"]])[0])
    bm25_model = build_bm25_model([chunk["text"] for chunk in chunks])
    client = create_collection(dense_vector_size=dense_vector_size)
    index_chunks(
        client=client,
        collection_name=COLLECTION_NAME,
        chunks=chunks,
        bm25_model=bm25_model,
        batch_size=BATCH_SIZE,
        annotator=annotator,
    )
    indexed_points = int(client.count(collection_name=COLLECTION_NAME, exact=True).count)
    if indexed_points != len(chunks):
        raise RuntimeError(
            f"Indexacao incompleta: esperado={len(chunks)}, indexado={indexed_points}. "
            "Metadata BM25 nao foi publicada."
        )
    temporary_bm25_path = BM25_METADATA_PATH.with_suffix(BM25_METADATA_PATH.suffix + ".tmp")
    write_bm25_model(bm25_model, metadata_path=temporary_bm25_path)
    temporary_bm25_path.replace(BM25_METADATA_PATH)
    print(f"Colecao Qdrant salva em {QDRANT_URL}/{COLLECTION_NAME}")
    print(f"Metadata BM25 salva em {BM25_METADATA_PATH}")


if __name__ == "__main__":
    main()
