"""
Vector Knowledge Base for Incident Similarity Search
=====================================================
Uses ChromaDB for persistent vector storage with semantic search capabilities.
Supports ingestion of incident reports, runbooks, and architecture documents.
"""

import os
import json
import uuid
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Represents a document in the knowledge base."""
    id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "embedding": self.embedding
        }


@dataclass
class SearchResult:
    """Result from a similarity search."""
    document: Document
    score: float
    distance: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document": self.document.to_dict(),
            "score": self.score,
            "distance": self.distance
        }


class VectorStore:
    """
    ChromaDB-backed vector store for incident knowledge base.

    Collections:
    - incidents: Post-incident reports and RCA findings
    - runbooks: Operational runbooks and playbooks
    - architecture: Architecture decision records and system docs
    - patterns: Known failure patterns and mitigations
    """

    COLLECTIONS = ["incidents", "runbooks", "architecture", "patterns"]

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        embedding_model: str = "all-MiniLM-L6-v2",
        collection_name: str = "incidents"
    ):
        """
        Initialize the vector store.

        Args:
            persist_directory: Path to persist ChromaDB data
            embedding_model: Sentence transformer model for embeddings
            collection_name: Default collection to use
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.embedding_model_name = embedding_model
        self.default_collection = collection_name
        self.client = None
        self.collections = {}
        self.embedding_function = None
        self.model = None

        self._initialize()

    def _initialize(self):
        """Initialize ChromaDB client and embedding function."""
        if not CHROMADB_AVAILABLE:
            logger.warning("ChromaDB not available. Using in-memory fallback.")
            self._init_fallback()
            return

        try:
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )

            # Initialize embedding function
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                self.model = SentenceTransformer(self.embedding_model_name)
                self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=self.embedding_model_name
                )
            else:
                # Use default embedding function
                self.embedding_function = embedding_functions.DefaultEmbeddingFunction()

            # Get or create collections
            for coll_name in self.COLLECTIONS:
                self.collections[coll_name] = self.client.get_or_create_collection(
                    name=coll_name,
                    embedding_function=self.embedding_function,
                    metadata={"description": f"Knowledge base: {coll_name}"}
                )

            logger.info(f"VectorStore initialized with {len(self.COLLECTIONS)} collections at {self.persist_directory}")

        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self._init_fallback()

    def _init_fallback(self):
        """Initialize in-memory fallback when ChromaDB is unavailable."""
        self.client = None
        self.collections = {name: InMemoryCollection(name) for name in self.COLLECTIONS}
        logger.info("Using in-memory fallback for vector store")

    def _get_collection(self, collection_name: Optional[str] = None):
        """Get a collection by name, defaulting to default_collection."""
        name = collection_name or self.default_collection
        if name not in self.collections:
            raise ValueError(f"Collection '{name}' not found. Available: {list(self.collections.keys())}")
        return self.collections[name]

    def add_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        collection_name: Optional[str] = None,
        document_id: Optional[str] = None
    ) -> str:
        """
        Add a document to the vector store.

        Args:
            content: Document text content
            metadata: Document metadata (source, type, tags, etc.)
            collection_name: Target collection
            document_id: Optional custom ID

        Returns:
            Document ID
        """
        doc_id = document_id or str(uuid.uuid4())

        # Ensure required metadata fields
        metadata = dict(metadata)
        metadata.setdefault("created_at", datetime.utcnow().isoformat())
        metadata.setdefault("content_hash", hashlib.sha256(content.encode()).hexdigest()[:16])

        collection = self._get_collection(collection_name)

        if self.client:
            # ChromaDB
            collection.add(
                documents=[content],
                metadatas=[metadata],
                ids=[doc_id]
            )
        else:
            # Fallback
            collection.add(doc_id, content, metadata)

        logger.debug(f"Added document {doc_id} to {collection_name or self.default_collection}")
        return doc_id

    def add_documents_batch(
        self,
        documents: List[Tuple[str, Dict[str, Any]]],
        collection_name: Optional[str] = None
    ) -> List[str]:
        """Add multiple documents in batch."""
        collection = self._get_collection(collection_name)
        ids = [str(uuid.uuid4()) for _ in documents]
        contents = [doc[0] for doc in documents]
        metadatas = []

        for _, metadata in documents:
            m = dict(metadata)
            m.setdefault("created_at", datetime.utcnow().isoformat())
            metadatas.append(m)

        if self.client:
            collection.add(documents=contents, metadatas=metadatas, ids=ids)
        else:
            for doc_id, content, metadata in zip(ids, contents, metadatas):
                collection.add(doc_id, content, metadata)

        return ids

    def search(
        self,
        query: str,
        collection_name: Optional[str] = None,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Search for similar documents.

        Args:
            query: Search query text
            collection_name: Collection to search
            n_results: Number of results to return
            where: Metadata filter (ChromaDB where clause)
            where_document: Document content filter

        Returns:
            List of SearchResult objects
        """
        collection = self._get_collection(collection_name)

        if self.client:
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
                where_document=where_document,
                include=["documents", "metadatas", "distances"]
            )

            search_results = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    doc = Document(
                        id=doc_id,
                        content=results["documents"][0][i],
                        metadata=results["metadatas"][0][i]
                    )
                    distance = results["distances"][0][i]
                    # Convert distance to similarity score (0-1)
                    score = 1.0 / (1.0 + distance)
                    search_results.append(SearchResult(doc, score, distance))

            return search_results
        else:
            return collection.search(query, n_results)

    def get_document(self, document_id: str, collection_name: Optional[str] = None) -> Optional[Document]:
        """Retrieve a document by ID."""
        collection = self._get_collection(collection_name)

        if self.client:
            results = collection.get(ids=[document_id], include=["documents", "metadatas"])
            if results["ids"]:
                return Document(
                    id=results["ids"][0],
                    content=results["documents"][0],
                    metadata=results["metadatas"][0]
                )
        else:
            return collection.get(document_id)

        return None

    def delete_document(self, document_id: str, collection_name: Optional[str] = None) -> bool:
        """Delete a document by ID."""
        collection = self._get_collection(collection_name)

        if self.client:
            collection.delete(ids=[document_id])
        else:
            return collection.delete(document_id)

        return True

    def update_document(
        self,
        document_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None
    ) -> bool:
        """Update an existing document."""
        collection = self._get_collection(collection_name)

        # Get existing document
        existing = self.get_document(document_id, collection_name)
        if not existing:
            return False

        new_content = content if content is not None else existing.content
        new_metadata = metadata if metadata is not None else existing.metadata
        new_metadata["updated_at"] = datetime.utcnow().isoformat()

        if self.client:
            collection.update(
                ids=[document_id],
                documents=[new_content],
                metadatas=[new_metadata]
            )
        else:
            collection.update(document_id, new_content, new_metadata)

        return True

    def list_documents(
        self,
        collection_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """List documents in a collection."""
        collection = self._get_collection(collection_name)

        if self.client:
            results = collection.get(
                limit=limit,
                offset=offset,
                where=where,
                include=["documents", "metadatas"]
            )

            documents = []
            for i, doc_id in enumerate(results["ids"]):
                documents.append(Document(
                    id=doc_id,
                    content=results["documents"][i],
                    metadata=results["metadatas"][i]
                ))
            return documents
        else:
            return collection.list(limit, offset)

    def get_collection_stats(self, collection_name: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for a collection."""
        collection = self._get_collection(collection_name)

        if self.client:
            count = collection.count()
            return {
                "name": collection.name,
                "count": count,
                "metadata": collection.metadata
            }
        else:
            return collection.stats()

    def reset_collection(self, collection_name: str) -> bool:
        """Reset (delete all documents in) a collection."""
        if collection_name not in self.COLLECTIONS:
            return False

        if self.client:
            self.client.delete_collection(collection_name)
            self.collections[collection_name] = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
        else:
            self.collections[collection_name] = InMemoryCollection(collection_name)

        return True

    def close(self):
        """Close the vector store."""
        if self.client:
            # ChromaDB client doesn't need explicit close
            pass


class InMemoryCollection:
    """In-memory fallback collection when ChromaDB is unavailable."""

    def __init__(self, name: str):
        self.name = name
        self.documents = {}  # id -> (content, metadata)

    def add(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        self.documents[doc_id] = (content, metadata)

    def get(self, doc_id: str) -> Optional[Document]:
        if doc_id in self.documents:
            content, metadata = self.documents[doc_id]
            return Document(id=doc_id, content=content, metadata=metadata)
        return None

    def update(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        if doc_id in self.documents:
            self.documents[doc_id] = (content, metadata)

    def delete(self, doc_id: str) -> bool:
        if doc_id in self.documents:
            del self.documents[doc_id]
            return True
        return False

    def list(self, limit: int = 100, offset: int = 0) -> List[Document]:
        items = list(self.documents.items())[offset:offset+limit]
        return [Document(id=k, content=v[0], metadata=v[1]) for k, v in items]

    def search(self, query: str, n_results: int = 5) -> List[SearchResult]:
        """Simple keyword-based search for fallback."""
        query_lower = query.lower()
        results = []

        for doc_id, (content, metadata) in self.documents.items():
            content_lower = content.lower()
            # Simple scoring: count query word matches
            score = sum(1 for word in query_lower.split() if word in content_lower)
            if score > 0:
                doc = Document(id=doc_id, content=content, metadata=metadata)
                results.append(SearchResult(doc, score / len(query_lower.split()), 1.0 - score / len(query_lower.split())))

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:n_results]

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "count": len(self.documents),
            "metadata": {}
        }

    def count(self) -> int:
        return len(self.documents)


def create_vector_store(
    persist_directory: str = "./chroma_db",
    embedding_model: str = "all-MiniLM-L6-v2"
) -> VectorStore:
    """Factory function to create a VectorStore instance."""
    return VectorStore(persist_directory, embedding_model)


if __name__ == "__main__":
    # Demo/test
    logging.basicConfig(level=logging.INFO)

    vs = create_vector_store("./test_chroma_db")

    # Add sample incident
    incident_id = vs.add_document(
        content="SEV-1: Payment service database connection pool exhausted after deployment v2.3.1. "
                "Root cause: Missing connectionTimeout and idleTimeout in HikariCP config. "
                "Resolution: Rolled back to v2.3.0. Added connection pool validation to CI.",
        metadata={
            "type": "incident",
            "severity": "SEV-1",
            "service": "payment-service",
            "root_cause": "connection_pool_exhaustion",
            "resolution": "rollback",
            "tags": ["database", "connection_pool", "deployment"]
        },
        collection_name="incidents"
    )

    # Add sample runbook
    runbook_id = vs.add_document(
        content="Runbook: java-service Connection Pool Exhaustion\n\n"
                "Symptoms: High error rate on /api/* endpoints, thread pool queue full, latency p99 > 30s\n\n"
                "Diagnosis:\n"
                "1. Check HikariCP metrics: hikaricp_connections_active, hikaricp_connections_idle, hikaricp_connections_pending\n"
                "2. Check application logs for 'Connection not available' or 'Pool exhausted'\n"
                "3. Verify recent deployment changed pool config\n\n"
                "Mitigation:\n"
                "1. Immediate: Rollback deployment\n"
                "2. If rollback not possible: Scale replicas\n"
                "3. Config fix: Add connectionTimeout: 5000, idleTimeout: 300000, maximumPoolSize: 50",
        metadata={
            "type": "runbook",
            "service": "java-service",
            "scenario": "connection_pool_exhaustion",
            "tags": ["database", "connection_pool", "java"]
        },
        collection_name="runbooks"
    )

    # Search
    print("\n=== Search for 'connection pool exhausted' ===")
    results = vs.search("connection pool exhausted", collection_name="incidents", n_results=3)
    for r in results:
        print(f"  Score: {r.score:.3f} | ID: {r.document.id[:8]} | {r.document.content[:100]}...")

    print("\n=== Search runbooks for 'pool exhaustion' ===")
    results = vs.search("pool exhaustion", collection_name="runbooks", n_results=3)
    for r in results:
        print(f"  Score: {r.score:.3f} | ID: {r.document.id[:8]} | {r.document.content[:100]}...")

    # Stats
    print("\n=== Collection Stats ===")
    for coll in ["incidents", "runbooks", "architecture", "patterns"]:
        stats = vs.get_collection_stats(coll)
        print(f"  {coll}: {stats['count']} documents")

    vs.close()
    print("\nDemo complete!")