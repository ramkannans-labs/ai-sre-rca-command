"""
Architecture Documents Parser
=============================
Parses Architecture Decision Records (ADRs), system documentation, and architecture diagrams
into structured format for the knowledge base.
"""

import re
import yaml
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum
import logging

from .vector_store import VectorStore, create_vector_store

logger = logging.getLogger(__name__)


class DocType(Enum):
    """Types of architecture documents."""
    ADR = "adr"                    # Architecture Decision Record
    SYSTEM_DESIGN = "system_design"  # System design document
    API_SPEC = "api_spec"          # API specification
    DATA_MODEL = "data_model"      # Data model documentation
    INFRASTRUCTURE = "infrastructure"  # Infrastructure documentation
    RUNBOOK = "runbook"            # Operational runbook
    INCIDENT_REPORT = "incident_report"  # Post-incident report
    DIAGRAM = "diagram"            # Architecture diagram (Mermaid, PlantUML)


@dataclass
class ArchitectureDoc:
    """Parsed architecture document."""
    id: str
    doc_type: DocType
    title: str
    content: str
    summary: str
    status: str = "active"  # proposed, accepted, deprecated, superseded
    authors: List[str] = field(default_factory=list)
    date: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tags: List[str] = field(default_factory=list)
    related_docs: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    technologies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_file: str = ""

    def to_searchable_text(self) -> str:
        """Convert to text optimized for vector search."""
        parts = [
            f"{self.doc_type.value.upper()}: {self.title}",
            f"Status: {self.status}",
            f"Summary: {self.summary}",
        ]

        if self.authors:
            parts.append(f"Authors: {', '.join(self.authors)}")

        if self.services:
            parts.append(f"Services: {', '.join(self.services)}")

        if self.components:
            parts.append(f"Components: {', '.join(self.components)}")

        if self.technologies:
            parts.append(f"Technologies: {', '.join(self.technologies)}")

        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")

        # Add truncated content
        content_preview = self.content[:2000] + ("..." if len(self.content) > 2000 else "")
        parts.append(f"Content: {content_preview}")

        return "\n".join(parts)

    def to_metadata(self) -> Dict[str, Any]:
        """Convert to metadata for vector store."""
        return {
            "type": "architecture",
            "doc_type": self.doc_type.value,
            "doc_id": self.id,
            "title": self.title,
            "status": self.status,
            "date": self.date,
            "authors": self.authors,
            "tags": self.tags,
            "related_docs": self.related_docs,
            "services": self.services,
            "components": self.components,
            "technologies": self.technologies,
            "source_file": self.source_file,
            **self.metadata
        }


class ArchitectureDocParser:
    """
    Parses architecture documents from various formats.

    Supported formats:
    - ADR (Markdown with frontmatter following MADR format)
    - System design docs (Markdown with structured sections)
    - API specs (OpenAPI/Swagger YAML/JSON)
    - Mermaid diagrams
    - PlantUML diagrams
    """

    def __init__(self):
        self.parsed_docs = []

    def parse_file(self, file_path: Union[str, Path]) -> Optional[ArchitectureDoc]:
        """Parse a single architecture document file."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Document file not found: {file_path}")
            return None

        content = path.read_text(encoding="utf-8")
        return self.parse_content(content, source_file=str(path))

    def parse_content(self, content: str, source_file: str = "") -> Optional[ArchitectureDoc]:
        """Parse document content based on detected type."""
        # Detect document type
        doc_type = self._detect_doc_type(content, source_file)

        if doc_type == DocType.ADR:
            return self._parse_adr(content, source_file)
        elif doc_type == DocType.SYSTEM_DESIGN:
            return self._parse_system_design(content, source_file)
        elif doc_type == DocType.API_SPEC:
            return self._parse_api_spec(content, source_file)
        elif doc_type == DocType.DIAGRAM:
            return self._parse_diagram(content, source_file)
        else:
            # Generic markdown parsing
            return self._parse_generic_markdown(content, source_file, doc_type)

    def parse_directory(self, dir_path: Union[str, Path], recursive: bool = True) -> List[ArchitectureDoc]:
        """Parse all architecture documents in a directory."""
        path = Path(dir_path)
        if not path.exists():
            logger.error(f"Directory not found: {dir_path}")
            return []

        patterns = ["**/*.md", "**/*.yaml", "**/*.yml", "**/*.json", "**/*.mmd", "**/*.puml"]
        files = []
        for pattern in patterns:
            files.extend(path.glob(pattern) if recursive else path.glob(pattern.replace("**/", "")))

        docs = []
        for file_path in files:
            if file_path.is_file():
                # Skip non-architecture markdown files
                if file_path.name.lower() in ["readme.md", "changelog.md", "license.md", "contributing.md"]:
                    continue

                doc = self.parse_file(file_path)
                if doc:
                    docs.append(doc)

        return docs

    def _detect_doc_type(self, content: str, source_file: str) -> DocType:
        """Detect the type of architecture document."""
        path = Path(source_file)
        suffix = path.suffix.lower()

        # Check file extension
        if suffix in [".mmd", ".mermaid"]:
            return DocType.DIAGRAM
        elif suffix in [".puml", ".plantuml"]:
            return DocType.DIAGRAM
        elif suffix in [".yaml", ".yml", ".json"]:
            # Check if OpenAPI spec
            if "openapi:" in content or "swagger:" in content:
                return DocType.API_SPEC

        # Check content for ADR markers
        if content.startswith("---"):
            try:
                frontmatter_end = content.index("---", 3)
                frontmatter = content[3:frontmatter_end]
                if "adr" in frontmatter.lower() or "architecture decision" in frontmatter.lower():
                    return DocType.ADR
                if "status:" in frontmatter.lower() and ("proposed" in frontmatter.lower() or "accepted" in frontmatter.lower()):
                    return DocType.ADR
            except ValueError:
                pass

        # Check for ADR title pattern
        if re.search(r"(?i)^#+\s*(ADR|Architecture Decision Record)\s*[:\-]", content, re.MULTILINE):
            return DocType.ADR

        # Check for system design markers
        if re.search(r"(?i)^#+\s*(System Design|Architecture Overview|Technical Design)", content, re.MULTILINE):
            return DocType.SYSTEM_DESIGN

        # Check for diagram content
        if "```mermaid" in content or "@startuml" in content:
            return DocType.DIAGRAM

        return DocType.SYSTEM_DESIGN  # Default

    def _parse_adr(self, content: str, source_file: str) -> Optional[ArchitectureDoc]:
        """Parse an Architecture Decision Record (MADR format)."""
        frontmatter = {}
        body = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2]
                except Exception as e:
                    logger.warning(f"Failed to parse ADR frontmatter: {e}")

        # Extract title
        title = frontmatter.get("title", "")
        if not title:
            # Try to extract from first heading
            match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = match.group(1).strip() if match else Path(source_file).stem

        # Generate ID
        doc_id = frontmatter.get("id", self._generate_adr_id(title))

        # Extract status
        status = frontmatter.get("status", "proposed").lower()
        valid_statuses = ["proposed", "accepted", "deprecated", "superseded"]
        if status not in valid_statuses:
            status = "proposed"

        # Extract authors
        authors = frontmatter.get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",")]

        # Extract date
        date = frontmatter.get("date", datetime.utcnow().isoformat())

        # Extract tags
        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]

        # Extract related ADRs
        related = frontmatter.get("related", [])
        if isinstance(related, str):
            related = [r.strip() for r in related.split(",")]

        # Generate summary from body
        summary = self._generate_summary(body)

        # Extract services, components, technologies
        services = self._extract_services(body)
        components = self._extract_components(body)
        technologies = self._extract_technologies(body)

        # Add ADR-specific tags
        tags.extend(["adr", f"status-{status}"])

        return ArchitectureDoc(
            id=doc_id,
            doc_type=DocType.ADR,
            title=title,
            content=body.strip(),
            summary=summary,
            status=status,
            authors=authors,
            date=date,
            tags=tags,
            related_docs=related,
            services=services,
            components=components,
            technologies=technologies,
            metadata=frontmatter.get("metadata", {}),
            source_file=source_file
        )

    def _parse_system_design(self, content: str, source_file: str) -> Optional[ArchitectureDoc]:
        """Parse a system design document."""
        frontmatter = {}
        body = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2]
                except Exception:
                    pass

        title = frontmatter.get("title", Path(source_file).stem)
        doc_id = frontmatter.get("id", self._generate_id(title, "SD"))

        return ArchitectureDoc(
            id=doc_id,
            doc_type=DocType.SYSTEM_DESIGN,
            title=title,
            content=body.strip(),
            summary=self._generate_summary(body),
            status=frontmatter.get("status", "active"),
            authors=frontmatter.get("authors", []),
            date=frontmatter.get("date", datetime.utcnow().isoformat()),
            tags=frontmatter.get("tags", []) + ["system_design"],
            related_docs=frontmatter.get("related", []),
            services=self._extract_services(body),
            components=self._extract_components(body),
            technologies=self._extract_technologies(body),
            metadata=frontmatter.get("metadata", {}),
            source_file=source_file
        )

    def _parse_api_spec(self, content: str, source_file: str) -> Optional[ArchitectureDoc]:
        """Parse an OpenAPI/Swagger specification."""
        try:
            if source_file.endswith((".yaml", ".yml")):
                spec = yaml.safe_load(content)
            else:
                spec = json.loads(content)

            info = spec.get("info", {})
            title = info.get("title", Path(source_file).stem)
            version = info.get("version", "1.0.0")
            description = info.get("description", "")

            # Extract paths and components
            paths = list(spec.get("paths", {}).keys())
            components = list(spec.get("components", {}).get("schemas", {}).keys())

            # Generate summary
            summary = f"API: {title} v{version}. {len(paths)} endpoints, {len(components)} schemas. {description[:200]}"

            doc_id = self._generate_id(title, "API")

            return ArchitectureDoc(
                id=doc_id,
                doc_type=DocType.API_SPEC,
                title=f"{title} API v{version}",
                content=content[:5000] + ("..." if len(content) > 5000 else ""),
                summary=summary,
                status="active",
                date=datetime.utcnow().isoformat(),
                tags=["api", "openapi", "specification"],
                services=self._extract_services_from_spec(spec),
                components=components[:50],  # Limit
                technologies=["REST", "OpenAPI", "HTTP"],
                metadata={
                    "version": version,
                    "endpoint_count": len(paths),
                    "schema_count": len(components),
                    "servers": spec.get("servers", [])
                },
                source_file=source_file
            )
        except Exception as e:
            logger.error(f"Failed to parse API spec: {e}")
            return None

    def _parse_diagram(self, content: str, source_file: str) -> Optional[ArchitectureDoc]:
        """Parse a Mermaid or PlantUML diagram."""
        path = Path(source_file)
        title = path.stem.replace("-", " ").replace("_", " ").title()
        doc_id = self._generate_id(title, "DIAG")

        # Determine diagram type
        if "```mermaid" in content:
            diagram_type = "mermaid"
            # Extract mermaid code
            match = re.search(r"```mermaid\n(.+?)```", content, re.DOTALL)
            diagram_content = match.group(1) if match else content
        elif "@startuml" in content:
            diagram_type = "plantuml"
            diagram_content = content
        else:
            diagram_type = "unknown"
            diagram_content = content

        # Try to extract title from diagram
        title_match = re.search(r"(?i)(title|graph|flowchart)\s+(.+)", diagram_content)
        if title_match:
            title = title_match.group(2).strip()

        # Extract components from diagram
        components = self._extract_components_from_diagram(diagram_content)

        summary = f"{diagram_type.upper()} diagram: {title}. Components: {', '.join(components[:10])}"

        return ArchitectureDoc(
            id=doc_id,
            doc_type=DocType.DIAGRAM,
            title=f"Diagram: {title}",
            content=diagram_content,
            summary=summary,
            status="active",
            date=datetime.utcnow().isoformat(),
            tags=["diagram", diagram_type],
            components=components,
            metadata={"diagram_type": diagram_type},
            source_file=source_file
        )

    def _parse_generic_markdown(self, content: str, source_file: str, doc_type: DocType) -> ArchitectureDoc:
        """Parse generic markdown as architecture document."""
        path = Path(source_file)
        title = path.stem.replace("-", " ").replace("_", " ").title()
        doc_id = self._generate_id(title, "DOC")

        return ArchitectureDoc(
            id=doc_id,
            doc_type=doc_type,
            title=title,
            content=content,
            summary=self._generate_summary(content),
            status="active",
            date=datetime.utcnow().isoformat(),
            tags=[doc_type.value],
            services=self._extract_services(content),
            components=self._extract_components(content),
            technologies=self._extract_technologies(content),
            source_file=source_file
        )

    def _generate_adr_id(self, title: str) -> str:
        """Generate ADR ID (e.g., ADR-001)."""
        # Try to extract number from title
        match = re.search(r"(\d+)", title)
        if match:
            return f"ADR-{int(match.group(1)):03d}"

        # Generate from hash
        hash_suffix = hashlib.md5(title.encode()).hexdigest()[:6]
        return f"ADR-{hash_suffix.upper()}"

    def _generate_id(self, title: str, prefix: str = "DOC") -> str:
        """Generate a document ID."""
        clean = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
        return f"{prefix}-{clean}-{timestamp}"

    def _generate_summary(self, content: str, max_length: int = 300) -> str:
        """Generate a summary from content."""
        # Remove code blocks
        content_no_code = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
        # Remove markdown formatting
        content_clean = re.sub(r"[#*`\[\]()]", "", content_no_code)
        # Normalize whitespace
        content_clean = re.sub(r"\s+", " ", content_clean).strip()

        if len(content_clean) <= max_length:
            return content_clean

        # Try to cut at sentence boundary
        truncated = content_clean[:max_length]
        last_period = truncated.rfind(".")
        if last_period > max_length * 0.7:
            return truncated[:last_period + 1]

        return truncated + "..."

    def _extract_services(self, content: str) -> List[str]:
        """Extract service names from content."""
        services = set()

        patterns = [
            r"\b([a-z]+-[a-z]+(?:-[a-z]+)?)-service\b",
            r"\b([a-z]+_[a-z]+(?:_[a-z]+)?)-service\b",
            r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)Service\b",
            r"(?i)service[:\s]+([a-z\-]+)",
            r"(?i)microservice[:\s]+([a-z\-]+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for m in matches:
                if isinstance(m, tuple):
                    m = m[0]
                services.add(m.lower().replace("_", "-"))

        return sorted(services)

    def _extract_services_from_spec(self, spec: Dict) -> List[str]:
        """Extract services from OpenAPI spec."""
        services = set()

        # From servers
        for server in spec.get("servers", []):
            url = server.get("url", "")
            # Extract service name from URL
            match = re.search(r"//([^/]+)", url)
            if match:
                host = match.group(1)
                # Remove domain suffix
                parts = host.split(".")
                if len(parts) > 1:
                    services.add(parts[0])

        # From tags
        for tag in spec.get("tags", []):
            name = tag.get("name", "")
            if name:
                services.add(name.lower().replace(" ", "-"))

        return sorted(services)

    def _extract_components(self, content: str) -> List[str]:
        """Extract component names from content."""
        components = set()

        # Common component patterns
        patterns = [
            r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b",  # PascalCase
            r"(?i)component[:\s]+([a-z\-]+)",
            r"(?i)module[:\s]+([a-z\-]+)",
            r"(?i)library[:\s]+([a-z\-]+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            for m in matches:
                if isinstance(m, tuple):
                    m = m[0]
                components.add(m)

        # Filter out common words
        stop_words = {"The", "This", "That", "With", "From", "Have", "Will", "Should", "Would", "Could"}
        components = {c for c in components if c not in stop_words and len(c) > 2}

        return sorted(components)[:30]

    def _extract_components_from_diagram(self, content: str) -> List[str]:
        """Extract components from diagram content."""
        components = set()

        # Mermaid patterns
        # graph TD; A[Component] --> B[Another]
        mermaid_nodes = re.findall(r'[A-Z]\s*\[([^\]]+)\]', content)
        components.update(mermaid_nodes)

        # A --> B
        mermaid_edges = re.findall(r'([A-Z])\s*-->\s*([A-Z])', content)
        for a, b in mermaid_edges:
            components.add(a)
            components.add(b)

        # PlantUML patterns
        # [Component] or component "Component"
        puml_components = re.findall(r'(?:component|\[)["\s]*([^"\]]+)["\s]*\]', content, re.IGNORECASE)
        components.update(puml_components)

        return sorted(components)[:30]

    def _extract_technologies(self, content: str) -> List[str]:
        """Extract technology names from content."""
        tech_keywords = [
            "kubernetes", "k8s", "docker", "container",
            "aws", "gcp", "azure", "cloud",
            "postgresql", "postgres", "mysql", "mongodb", "redis", "cassandra",
            "kafka", "rabbitmq", "nats", "pulsar",
            "prometheus", "grafana", "loki", "tempo", "jaeger", "zipkin",
            "opentelemetry", "otel", "otelcol",
            "istio", "linkerd", "consul", "envoy",
            "terraform", "helm", "argocd", "flux",
            "java", "spring", "spring boot", "python", "flask", "fastapi", "go", "golang", "rust", "nodejs", "node",
            "react", "vue", "angular",
            "grpc", "rest", "graphql", "protobuf",
            "hikaricp", "hikari", "connection pool",
            "nginx", "traefik", "haproxy",
            "elasticsearch", "opensearch",
            "chromadb", "vector", "embedding",
        ]

        content_lower = content.lower()
        found = set()

        for tech in tech_keywords:
            if tech in content_lower:
                found.add(tech)

        return sorted(found)


class ArchitectureDocIngestor:
    """Ingests parsed architecture documents into the vector knowledge base."""

    def __init__(self, vector_store: Optional[VectorStore] = None, persist_directory: str = "./chroma_db"):
        self.vector_store = vector_store or create_vector_store(persist_directory)
        self.parser = ArchitectureDocParser()

    def ingest_file(self, file_path: Union[str, Path]) -> Optional[ArchitectureDoc]:
        """Parse and ingest a single architecture document."""
        doc = self.parser.parse_file(file_path)
        if doc:
            self._ingest_doc(doc)
        return doc

    def ingest_directory(self, dir_path: Union[str, Path], recursive: bool = True) -> List[ArchitectureDoc]:
        """Parse and ingest all architecture documents in a directory."""
        docs = self.parser.parse_directory(dir_path, recursive)
        for doc in docs:
            self._ingest_doc(doc)
        return docs

    def ingest_doc(self, doc: ArchitectureDoc) -> str:
        """Ingest an already-parsed document."""
        return self._ingest_doc(doc)

    def _ingest_doc(self, doc: ArchitectureDoc) -> str:
        """Store document in vector DB."""
        doc_id = self.vector_store.add_document(
            content=doc.to_searchable_text(),
            metadata=doc.to_metadata(),
            collection_name="architecture",
            document_id=doc.id
        )
        logger.info(f"Ingested architecture doc: {doc.id} - {doc.title}")
        return doc_id

    def search_docs(
        self,
        query: str,
        doc_type: Optional[DocType] = None,
        service: Optional[str] = None,
        status: Optional[str] = None,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for relevant architecture documents."""
        where = {}
        if doc_type:
            where["doc_type"] = doc_type.value
        if service:
            where["services"] = {"$in": [service]}
        if status:
            where["status"] = status

        results = self.vector_store.search(
            query=query,
            collection_name="architecture",
            n_results=n_results,
            where=where if where else None
        )

        return [r.to_dict() for r in results]


def create_architecture_parser() -> ArchitectureDocParser:
    """Factory function to create an ArchitectureDocParser."""
    return ArchitectureDocParser()


def create_architecture_ingestor(persist_directory: str = "./chroma_db") -> ArchitectureDocIngestor:
    """Factory function to create an ArchitectureDocIngestor."""
    return ArchitectureDocIngestor(persist_directory=persist_directory)


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)

    # Sample ADR
    sample_adr = """---
title: "Use Connection Pooling for Database Access"
id: "ADR-001"
status: accepted
authors: ["Jane Doe", "John Smith"]
date: "2024-01-15"
tags: ["database", "performance", "java"]
related: ["ADR-002"]
---

# ADR-001: Use Connection Pooling for Database Access

## Context
Our Java services were creating new database connections for each request, causing high latency and connection exhaustion under load.

## Decision
We will use HikariCP as our connection pool implementation for all Java services.

## Consequences
- Positive: Reduced connection overhead, better resource utilization
- Negative: Need to configure pool sizing correctly
- Risk: Pool exhaustion if not monitored

## Implementation
- Add HikariCP dependency
- Configure pool size based on CPU cores
- Add connection timeout and idle timeout
- Monitor pool metrics via Prometheus
"""

    # Sample system design
    sample_design = """---
title: "Order Processing System Architecture"
id: "SD-001"
status: active
authors: ["Platform Team"]
date: "2024-02-01"
tags: ["architecture", "orders", "event-driven"]
---

# Order Processing System

## Overview
The order processing system handles customer orders through an event-driven architecture.

## Components
- **Order API** (Java/Spring Boot): REST endpoint for order submission
- **Order Processor** (Python/FastAPI): Processes orders asynchronously
- **Payment Service** (Java): Handles payment authorization
- **Inventory Service** (Go): Manages stock levels
- **Notification Service** (Node.js): Sends confirmations

## Data Flow
1. Client submits order via Order API
2. Order API publishes OrderCreated event to Kafka
3. Order Processor consumes and orchestrates fulfillment
4. Payment Service authorizes payment
5. Inventory Service reserves stock
6. Notification Service sends confirmation

## Technologies
- Kubernetes (EKS)
- Kafka for event streaming
- PostgreSQL for order persistence
- Redis for caching
- Prometheus/Grafana for observability
"""

    parser = create_architecture_parser()

    print("=== Parsing ADR ===")
    adr = parser.parse_content(sample_adr, "adr-001-connection-pooling.md")
    if adr:
        print(f"  ID: {adr.id}")
        print(f"  Type: {adr.doc_type.value}")
        print(f"  Title: {adr.title}")
        print(f"  Status: {adr.status}")
        print(f"  Authors: {adr.authors}")
        print(f"  Tags: {adr.tags}")
        print(f"  Services: {adr.services}")
        print(f"  Technologies: {adr.technologies}")
        print(f"  Summary: {adr.summary[:200]}...")

    print("\n=== Parsing System Design ===")
    design = parser.parse_content(sample_design, "sd-001-order-processing.md")
    if design:
        print(f"  ID: {design.id}")
        print(f"  Type: {design.doc_type.value}")
        print(f"  Title: {design.title}")
        print(f"  Services: {design.services}")
        print(f"  Components: {design.components[:10]}")
        print(f"  Technologies: {design.technologies}")
        print(f"  Summary: {design.summary[:200]}...")

    # Test ingestion
    ingestor = create_architecture_ingestor("./test_chroma_db_arch")
    if adr:
        ingestor.ingest_doc(adr)
    if design:
        ingestor.ingest_doc(design)

    # Search
    print("\n=== Search for 'connection pool java' ===")
    results = ingestor.search_docs("connection pool java", doc_type=DocType.ADR)
    for r in results:
        print(f"  Score: {r['score']:.3f} | {r['document']['metadata'].get('doc_id')} | {r['document']['content'][:150]}...")

    print("\n=== Search for 'order processing kafka' ===")
    results = ingestor.search_docs("order processing kafka", doc_type=DocType.SYSTEM_DESIGN)
    for r in results:
        print(f"  Score: {r['score']:.3f} | {r['document']['metadata'].get('doc_id')} | {r['document']['content'][:150]}...")

    ingestor.vector_store.close()
    print("\nDemo complete!")