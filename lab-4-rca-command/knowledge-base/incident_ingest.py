"""
Incident Ingestion Pipeline
===========================
Processes post-incident reports and ingests them into the vector knowledge base.
Supports multiple input formats: Markdown, JSON, HTML, and structured reports.
"""

import os
import json
import re
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum
import logging

from .vector_store import VectorStore, create_vector_store

logger = logging.getLogger(__name__)


class IncidentFormat(Enum):
    """Supported incident report formats."""
    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"
    STRUCTURED = "structured"  # Our standard structured format


@dataclass
class IncidentReport:
    """Structured incident report."""
    incident_id: str
    title: str
    severity: str
    status: str
    started_at: str
    resolved_at: Optional[str]
    duration_minutes: Optional[int]
    root_cause: str
    resolution: str
    impact: str
    slo_impact: Optional[str] = None
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    services_affected: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_searchable_text(self) -> str:
        """Convert to text optimized for vector search."""
        parts = [
            f"Incident: {self.title}",
            f"Severity: {self.severity}",
            f"Root Cause: {self.root_cause}",
            f"Resolution: {self.resolution}",
            f"Impact: {self.impact}",
        ]
        if self.slo_impact:
            parts.append(f"SLO Impact: {self.slo_impact}")
        if self.action_items:
            actions = "; ".join([f"{a.get('description', '')} (Owner: {a.get('owner', '')})" for a in self.action_items])
            parts.append(f"Action Items: {actions}")
        if self.services_affected:
            parts.append(f"Services: {', '.join(self.services_affected)}")
        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")
        return "\n".join(parts)

    def to_metadata(self) -> Dict[str, Any]:
        """Convert to metadata for vector store."""
        return {
            "type": "incident",
            "incident_id": self.incident_id,
            "severity": self.severity,
            "status": self.status,
            "started_at": self.started_at,
            "resolved_at": self.resolved_at,
            "duration_minutes": self.duration_minutes,
            "services_affected": self.services_affected,
            "tags": self.tags,
            "root_cause_category": self._categorize_root_cause(),
            **self.metadata
        }

    def _categorize_root_cause(self) -> str:
        """Categorize root cause for filtering."""
        rc_lower = self.root_cause.lower()
        categories = {
            "deployment": ["deployment", "rollback", "release", "version"],
            "database": ["database", "connection pool", "query", "lock", "deadlock"],
            "resource_exhaustion": ["cpu", "memory", "disk", "oom", "exhaustion", "limit"],
            "network": ["network", "dns", "latency", "timeout", "connectivity"],
            "configuration": ["config", "configuration", "feature flag", "flag"],
            "dependency": ["dependency", "cascade", "upstream", "downstream", "third party"],
            "code": ["bug", "exception", "null pointer", "memory leak", "logic error"],
            "security": ["breach", "unauthorized", "authentication", "authorization", "token"],
        }
        for cat, keywords in categories.items():
            if any(kw in rc_lower for kw in keywords):
                return cat
        return "other"


class IncidentIngestionPipeline:
    """
    Pipeline for ingesting incident reports into the knowledge base.

    Features:
    - Multi-format parsing (Markdown, JSON, HTML)
    - Automatic field extraction
    - Deduplication via content hashing
    - Tag extraction and normalization
    - Timeline parsing
    - Action item extraction
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        persist_directory: str = "./chroma_db"
    ):
        self.vector_store = vector_store or create_vector_store(persist_directory)
        self.processed_hashes = set()
        self._load_processed_hashes()

    def _load_processed_hashes(self):
        """Load previously processed content hashes."""
        hash_file = Path(self.vector_store.persist_directory) / "processed_hashes.json"
        if hash_file.exists():
            try:
                with open(hash_file) as f:
                    self.processed_hashes = set(json.load(f))
            except Exception as e:
                logger.warning(f"Could not load processed hashes: {e}")

    def _save_processed_hashes(self):
        """Save processed content hashes."""
        hash_file = Path(self.vector_store.persist_directory) / "processed_hashes.json"
        try:
            with open(hash_file, "w") as f:
                json.dump(list(self.processed_hashes), f)
        except Exception as e:
            logger.warning(f"Could not save processed hashes: {e}")

    def _compute_content_hash(self, content: str) -> str:
        """Compute hash of content for deduplication."""
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def ingest_file(self, file_path: Union[str, Path]) -> Optional[IncidentReport]:
        """Ingest an incident report from a file."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        content = path.read_text(encoding="utf-8")
        content_hash = self._compute_content_hash(content)

        if content_hash in self.processed_hashes:
            logger.info(f"Skipping already processed: {file_path}")
            return None

        # Detect format
        fmt = self._detect_format(path, content)

        # Parse based on format
        if fmt == IncidentFormat.MARKDOWN:
            report = self._parse_markdown(content, path.stem)
        elif fmt == IncidentFormat.JSON:
            report = self._parse_json(content, path.stem)
        elif fmt == IncidentFormat.HTML:
            report = self._parse_html(content, path.stem)
        elif fmt == IncidentFormat.STRUCTURED:
            report = self._parse_structured(content, path.stem)
        else:
            logger.error(f"Unsupported format: {fmt}")
            return None

        if report:
            # Store in vector DB
            self.vector_store.add_document(
                content=report.to_searchable_text(),
                metadata=report.to_metadata(),
                collection_name="incidents",
                document_id=report.incident_id
            )

            # Track processed
            self.processed_hashes.add(content_hash)
            self._save_processed_hashes()

            logger.info(f"Ingested incident: {report.incident_id} - {report.title}")
            return report

        return None

    def ingest_directory(self, dir_path: Union[str, Path], recursive: bool = True) -> List[IncidentReport]:
        """Ingest all incident reports from a directory."""
        path = Path(dir_path)
        if not path.exists():
            logger.error(f"Directory not found: {dir_path}")
            return []

        pattern = "**/*" if recursive else "*"
        files = list(path.glob(pattern))

        reports = []
        for file_path in files:
            if file_path.is_file() and file_path.suffix in [".md", ".json", ".html", ".txt", ".yaml", ".yml"]:
                report = self.ingest_file(file_path)
                if report:
                    reports.append(report)

        return reports

    def _detect_format(self, path: Path, content: str) -> IncidentFormat:
        """Detect the format of an incident report."""
        suffix = path.suffix.lower()

        if suffix == ".json":
            return IncidentFormat.JSON
        elif suffix in [".html", ".htm"]:
            return IncidentFormat.HTML
        elif suffix in [".yaml", ".yml"]:
            return IncidentFormat.STRUCTURED
        elif suffix == ".md":
            # Check if it's our structured format
            if content.startswith("---") and "incident_id:" in content[:500]:
                return IncidentFormat.STRUCTURED
            return IncidentFormat.MARKDOWN
        else:
            # Try to detect from content
            if content.strip().startswith("{"):
                return IncidentFormat.JSON
            elif content.strip().startswith("<"):
                return IncidentFormat.HTML
            return IncidentFormat.MARKDOWN

    def _parse_markdown(self, content: str, source: str) -> Optional[IncidentReport]:
        """Parse a Markdown incident report."""
        # Extract frontmatter if present
        frontmatter = {}
        body = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    import yaml
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2]
                except Exception:
                    pass

        # Extract fields from frontmatter or body
        incident_id = frontmatter.get("incident_id", f"INC-{source}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")

        # Try to extract from body using patterns
        title = frontmatter.get("title", self._extract_pattern(body, r"(?:^|\n)#+\s*(.+)", "Untitled Incident"))
        severity = frontmatter.get("severity", self._extract_pattern(body, r"(?i)severity[:\s]+(SEV-\d+)", "SEV-3"))
        status = frontmatter.get("status", self._extract_pattern(body, r"(?i)status[:\s]+(\w+)", "resolved"))
        root_cause = frontmatter.get("root_cause", self._extract_section(body, "root cause"))
        resolution = frontmatter.get("resolution", self._extract_section(body, "resolution"))
        impact = frontmatter.get("impact", self._extract_section(body, "impact"))
        slo_impact = frontmatter.get("slo_impact", self._extract_section(body, "slo impact"))

        # Parse timeline
        timeline = self._parse_timeline(body)

        # Parse action items
        action_items = self._parse_action_items(body)

        # Extract services
        services_affected = frontmatter.get("services_affected", self._extract_services(body))

        # Extract tags
        tags = frontmatter.get("tags", self._extract_tags(body, root_cause))

        # Parse timestamps
        started_at = frontmatter.get("started_at", self._extract_timestamp(body, "started"))
        resolved_at = frontmatter.get("resolved_at", self._extract_timestamp(body, "resolved"))
        duration_minutes = frontmatter.get("duration_minutes")

        if not duration_minutes and started_at and resolved_at:
            try:
                start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                end = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
                duration_minutes = int((end - start).total_seconds() / 60)
            except Exception:
                pass

        return IncidentReport(
            incident_id=incident_id,
            title=title,
            severity=severity,
            status=status,
            started_at=started_at or datetime.utcnow().isoformat(),
            resolved_at=resolved_at,
            duration_minutes=duration_minutes,
            root_cause=root_cause or "Unknown",
            resolution=resolution or "Unknown",
            impact=impact or "Unknown",
            slo_impact=slo_impact,
            action_items=action_items,
            timeline=timeline,
            services_affected=services_affected,
            tags=tags,
            metadata={"source": source, "format": "markdown"}
        )

    def _parse_json(self, content: str, source: str) -> Optional[IncidentReport]:
        """Parse a JSON incident report."""
        try:
            data = json.loads(content)

            # Handle both flat and nested structures
            if "incident" in data:
                data = data["incident"]

            return IncidentReport(
                incident_id=data.get("incident_id", f"INC-{source}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"),
                title=data.get("title", "Untitled Incident"),
                severity=data.get("severity", "SEV-3"),
                status=data.get("status", "resolved"),
                started_at=data.get("started_at", datetime.utcnow().isoformat()),
                resolved_at=data.get("resolved_at"),
                duration_minutes=data.get("duration_minutes"),
                root_cause=data.get("root_cause", "Unknown"),
                resolution=data.get("resolution", "Unknown"),
                impact=data.get("impact", "Unknown"),
                slo_impact=data.get("slo_impact"),
                action_items=data.get("action_items", []),
                timeline=data.get("timeline", []),
                services_affected=data.get("services_affected", []),
                tags=data.get("tags", []),
                metadata={"source": source, "format": "json", **data.get("metadata", {})}
            )
        except Exception as e:
            logger.error(f"Failed to parse JSON: {e}")
            return None

    def _parse_html(self, content: str, source: str) -> Optional[IncidentReport]:
        """Parse an HTML incident report (basic extraction)."""
        # Simple HTML parsing - in production use BeautifulSoup
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()

        # Try to extract structured data from known patterns
        return self._parse_markdown(text, source)

    def _parse_structured(self, content: str, source: str) -> Optional[IncidentReport]:
        """Parse a structured YAML/Markdown report with frontmatter."""
        try:
            import yaml

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2] if len(parts) > 2 else ""
                else:
                    frontmatter = yaml.safe_load(content) or {}
                    body = ""
            else:
                frontmatter = yaml.safe_load(content) or {}
                body = ""

            return IncidentReport(
                incident_id=frontmatter.get("incident_id", f"INC-{source}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"),
                title=frontmatter.get("title", "Untitled Incident"),
                severity=frontmatter.get("severity", "SEV-3"),
                status=frontmatter.get("status", "resolved"),
                started_at=frontmatter.get("started_at", datetime.utcnow().isoformat()),
                resolved_at=frontmatter.get("resolved_at"),
                duration_minutes=frontmatter.get("duration_minutes"),
                root_cause=frontmatter.get("root_cause", "Unknown"),
                resolution=frontmatter.get("resolution", "Unknown"),
                impact=frontmatter.get("impact", "Unknown"),
                slo_impact=frontmatter.get("slo_impact"),
                action_items=frontmatter.get("action_items", []),
                timeline=frontmatter.get("timeline", []),
                services_affected=frontmatter.get("services_affected", []),
                tags=frontmatter.get("tags", []),
                metadata={"source": source, "format": "structured", **frontmatter.get("metadata", {})}
            )
        except Exception as e:
            logger.error(f"Failed to parse structured format: {e}")
            return None

    def _extract_pattern(self, text: str, pattern: str, default: str) -> str:
        """Extract first match of pattern from text."""
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else default

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        """Extract a section from markdown text."""
        # Try various heading formats
        patterns = [
            rf"(?i)##+\s*{re.escape(section_name)}[:\s]*\n(.+?)(?=\n##+|\Z)",
            rf"(?i)\*\*{re.escape(section_name)}\*\*[:\s]*\n(.+?)(?=\n\*\*|\Z)",
            rf"(?i){re.escape(section_name)}[:\s]+\n(.+?)(?=\n\w+[:\s]+\n|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        return None

    def _parse_timeline(self, text: str) -> List[Dict[str, Any]]:
        """Parse timeline entries from text."""
        timeline = []

        # Pattern: timestamp - description
        pattern = r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s*[-–—]\s*(.+)"

        for match in re.finditer(pattern, text):
            timeline.append({
                "timestamp": match.group(1).strip(),
                "description": match.group(2).strip()
            })

        return timeline

    def _parse_action_items(self, text: str) -> List[Dict[str, Any]]:
        """Parse action items from text."""
        action_items = []

        # Pattern: - [ ] or - [x] or 1. or •
        pattern = r"(?:^|\n)(?:[-*•]\s*(?:\[[ xX]\]\s*)?|\d+\.\s*)(.+?)(?:\s*\(Owner:\s*([^)]+)\))?(?:\s*Due:\s*([^\n]+))?(?=\n|$)"

        for match in re.finditer(pattern, text, re.MULTILINE):
            action_items.append({
                "description": match.group(1).strip(),
                "owner": match.group(2).strip() if match.group(2) else "",
                "due_date": match.group(3).strip() if match.group(3) else "",
                "completed": False
            })

        return action_items

    def _extract_services(self, text: str) -> List[str]:
        """Extract service names from text."""
        # Common service patterns
        services = set()

        # Pattern: service-name, service_name, ServiceName
        patterns = [
            r"\b([a-z]+-[a-z]+(?:-[a-z]+)?)-service\b",
            r"\b([a-z]+_[a-z]+(?:_[a-z]+)?)-service\b",
            r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)Service\b",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            services.update(m.lower() for m in matches)

        return sorted(services)

    def _extract_tags(self, text: str, root_cause: str) -> List[str]:
        """Extract tags from text and root cause."""
        tags = set()

        # Extract from root cause
        rc_tags = {
            "deployment": ["deployment", "release", "rollback"],
            "database": ["database", "connection pool", "query"],
            "resource": ["cpu", "memory", "disk", "oom"],
            "network": ["network", "dns", "latency", "timeout"],
            "config": ["config", "feature flag"],
            "dependency": ["cascade", "upstream", "downstream"],
        }

        rc_lower = root_cause.lower()
        for tag, keywords in rc_tags.items():
            if any(kw in rc_lower for kw in keywords):
                tags.add(tag)

        # Common incident tags
        common_tags = [
            "sev-1", "sev-2", "sev-3",
            "rollback", "scale", "config-change",
            "database", "cache", "queue", "api",
            "latency", "error-rate", "availability"
        ]

        text_lower = text.lower()
        for tag in common_tags:
            if tag in text_lower:
                tags.add(tag)

        return sorted(tags)

    def _extract_timestamp(self, text: str, prefix: str) -> Optional[str]:
        """Extract timestamp from text."""
        patterns = [
            rf"(?i){prefix}[:\s]+(\d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}:\d{{2}}:\d{{2}})",
            rf"(?i){prefix}[:\s]+(\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:\s*[AP]M)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None

    def create_report_from_dict(self, data: Dict[str, Any]) -> IncidentReport:
        """Create an IncidentReport from a dictionary (for programmatic creation)."""
        return IncidentReport(
            incident_id=data.get("incident_id", f"INC-MANUAL-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"),
            title=data.get("title", "Manual Incident"),
            severity=data.get("severity", "SEV-3"),
            status=data.get("status", "resolved"),
            started_at=data.get("started_at", datetime.utcnow().isoformat()),
            resolved_at=data.get("resolved_at"),
            duration_minutes=data.get("duration_minutes"),
            root_cause=data.get("root_cause", "Unknown"),
            resolution=data.get("resolution", "Unknown"),
            impact=data.get("impact", "Unknown"),
            slo_impact=data.get("slo_impact"),
            action_items=data.get("action_items", []),
            timeline=data.get("timeline", []),
            services_affected=data.get("services_affected", []),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {})
        )

    def ingest_report(self, report: IncidentReport) -> str:
        """Ingest an already-parsed IncidentReport."""
        doc_id = self.vector_store.add_document(
            content=report.to_searchable_text(),
            metadata=report.to_metadata(),
            collection_name="incidents",
            document_id=report.incident_id
        )
        logger.info(f"Ingested incident report: {report.incident_id}")
        return doc_id


def create_ingestion_pipeline(
    persist_directory: str = "./chroma_db"
) -> IncidentIngestionPipeline:
    """Factory function to create an IncidentIngestionPipeline."""
    return IncidentIngestionPipeline(persist_directory=persist_directory)


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)

    pipeline = create_ingestion_pipeline("./test_chroma_db_ingest")

    # Create a sample incident programmatically
    sample_incident = pipeline.create_report_from_dict({
        "incident_id": "INC-2024-042",
        "title": "java-service elevated error rate (12%)",
        "severity": "SEV-2",
        "status": "resolved",
        "started_at": "2024-03-15T14:22:00Z",
        "resolved_at": "2024-03-15T14:40:00Z",
        "duration_minutes": 18,
        "root_cause": "Connection pool exhaustion after v2.3.1 deployment - Missing connectionTimeout and idleTimeout in HikariCP config",
        "resolution": "Rolled back to v2.3.0; fix deployed in v2.3.2",
        "impact": "~2,400 failed orders; $12K estimated revenue impact",
        "slo_impact": "Availability SLO burned 0.8% of monthly budget",
        "action_items": [
            {"description": "Add connection pool config validation to CI", "owner": "@jane", "due_date": "2024-03-22"},
            {"description": "Add connection leak detection to integration tests", "owner": "@john", "due_date": "2024-03-29"},
            {"description": "Update java-service runbook with pool exhaustion steps", "owner": "@sarah", "due_date": "2024-03-20"}
        ],
        "timeline": [
            {"timestamp": "14:22", "description": "Alert fired: java-service error rate > 10%"},
            {"timestamp": "14:23", "description": "IC acknowledged. Investigating."},
            {"timestamp": "14:28", "description": "RCA agent identified connection pool exhaustion"},
            {"timestamp": "14:30", "description": "Ops validated via MCP metrics"},
            {"timestamp": "14:32", "description": "Rollback initiated: v2.3.1 → v2.3.0"},
            {"timestamp": "14:40", "description": "All services healthy. Incident resolved."}
        ],
        "services_affected": ["java-service", "orders-api"],
        "tags": ["connection_pool", "deployment", "database", "java"],
        "metadata": {"team": "platform", "runbook_used": "java-service-pool-exhaustion"}
    })

    pipeline.ingest_report(sample_incident)

    # Search for similar incidents
    print("\n=== Search for 'connection pool' ===")
    results = pipeline.vector_store.search("connection pool", collection_name="incidents", n_results=3)
    for r in results:
        print(f"  Score: {r.score:.3f} | {r.document.metadata.get('incident_id')} | {r.document.content[:150]}...")

    pipeline.vector_store.close()
    print("\nDemo complete!")