"""
Runbook Parser
==============
Parses operational runbooks and playbooks into structured format for the knowledge base.
Supports Markdown runbooks with standardized sections.
"""

import re
import yaml
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum
import logging

from .vector_store import VectorStore, create_vector_store

logger = logging.getLogger(__name__)


class RunbookSection(Enum):
    """Standard runbook sections."""
    TITLE = "title"
    SERVICE = "service"
    SYMPTOMS = "symptoms"
    SEVERITY = "severity"
    ESTIMATED_RESOLUTION = "estimated_resolution"
    DIAGNOSIS = "diagnosis"
    MITIGATION = "mitigation"
    VERIFICATION = "verification"
    PREVENTION = "prevention"
    METADATA = "metadata"


@dataclass
class RunbookStep:
    """A single step in a runbook."""
    step_number: int
    title: str
    description: str
    commands: List[str] = field(default_factory=list)
    expected_output: Optional[str] = None
    rollback_commands: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Runbook:
    """Parsed runbook structure."""
    id: str
    title: str
    service: str
    symptoms: List[str] = field(default_factory=list)
    severity: str = "SEV-2"
    estimated_resolution_minutes: int = 15
    diagnosis_steps: List[RunbookStep] = field(default_factory=list)
    mitigation_steps: List[RunbookStep] = field(default_factory=list)
    verification_steps: List[RunbookStep] = field(default_factory=list)
    prevention_steps: List[RunbookStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    version: str = "1.0"
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source_file: str = ""

    def to_searchable_text(self) -> str:
        """Convert to text optimized for vector search."""
        parts = [
            f"Runbook: {self.title}",
            f"Service: {self.service}",
            f"Severity: {self.severity}",
            f"Estimated Resolution: {self.estimated_resolution_minutes} minutes",
        ]

        if self.symptoms:
            parts.append(f"Symptoms: {', '.join(self.symptoms)}")

        # Add diagnosis steps
        if self.diagnosis_steps:
            diag = "Diagnosis: " + "; ".join([
                f"Step {s.step_number}: {s.title} - {s.description}" for s in self.diagnosis_steps
            ])
            parts.append(diag)

        # Add mitigation steps
        if self.mitigation_steps:
            mitig = "Mitigation: " + "; ".join([
                f"Step {s.step_number}: {s.title} - {s.description}" for s in self.mitigation_steps
            ])
            parts.append(mitig)

        # Add verification
        if self.verification_steps:
            verify = "Verification: " + "; ".join([
                f"Step {s.step_number}: {s.title} - {s.description}" for s in self.verification_steps
            ])
            parts.append(verify)

        # Add prevention
        if self.prevention_steps:
            prevent = "Prevention: " + "; ".join([
                f"Step {s.step_number}: {s.title} - {s.description}" for s in self.prevention_steps
            ])
            parts.append(prevent)

        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")

        return "\n".join(parts)

    def to_metadata(self) -> Dict[str, Any]:
        """Convert to metadata for vector store."""
        return {
            "type": "runbook",
            "runbook_id": self.id,
            "title": self.title,
            "service": self.service,
            "severity": self.severity,
            "estimated_resolution_minutes": self.estimated_resolution_minutes,
            "tags": self.tags,
            "version": self.version,
            "last_updated": self.last_updated,
            "source_file": self.source_file,
            "step_count": len(self.diagnosis_steps) + len(self.mitigation_steps) + len(self.verification_steps) + len(self.prevention_steps),
            **self.metadata
        }

    def get_all_steps(self) -> List[RunbookStep]:
        """Get all steps in order."""
        return self.diagnosis_steps + self.mitigation_steps + self.verification_steps + self.prevention_steps

    def get_commands(self) -> List[str]:
        """Extract all commands from the runbook."""
        commands = []
        for step in self.get_all_steps():
            commands.extend(step.commands)
        return commands


class RunbookParser:
    """
    Parses runbook files (Markdown with frontmatter) into structured Runbook objects.

    Expected format:
    ---
    title: "Service: Scenario"
    service: service-name
    symptoms:
      - "symptom 1"
      - "symptom 2"
    severity: SEV-2
    estimated_resolution: 15 min
    tags: [tag1, tag2]
    ---

    ## Diagnosis
    1. Step description
       ```bash
       command
       ```

    ## Mitigation
    1. Step description
       ```bash
       command
       ```

    ## Verification
    - Check condition

    ## Prevention
    - Preventive action
    """

    def __init__(self):
        self.parsed_runbooks = []

    def parse_file(self, file_path: Union[str, Path]) -> Optional[Runbook]:
        """Parse a single runbook file."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Runbook file not found: {file_path}")
            return None

        content = path.read_text(encoding="utf-8")
        return self.parse_content(content, source_file=str(path))

    def parse_content(self, content: str, source_file: str = "") -> Optional[Runbook]:
        """Parse runbook content."""
        # Extract frontmatter
        frontmatter = {}
        body = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2]
                except Exception as e:
                    logger.warning(f"Failed to parse frontmatter: {e}")

        # Generate ID from title or source file
        title = frontmatter.get("title", Path(source_file).stem if source_file else "Untitled Runbook")
        runbook_id = frontmatter.get("id", self._generate_id(title))

        # Parse sections
        diagnosis_steps = self._parse_section(body, "diagnosis", "Diagnosis")
        mitigation_steps = self._parse_section(body, "mitigation", "Mitigation")
        verification_steps = self._parse_section(body, "verification", "Verification")
        prevention_steps = self._parse_section(body, "prevention", "Prevention")

        # Renumber steps sequentially
        all_steps = diagnosis_steps + mitigation_steps + verification_steps + prevention_steps
        for i, step in enumerate(all_steps, 1):
            step.step_number = i

        # Parse estimated resolution
        est_res = frontmatter.get("estimated_resolution", "15 min")
        estimated_minutes = self._parse_duration(est_res)

        # Extract tags
        tags = frontmatter.get("tags", [])
        if not tags:
            tags = self._extract_tags_from_content(body, frontmatter)

        runbook = Runbook(
            id=runbook_id,
            title=title,
            service=frontmatter.get("service", "unknown"),
            symptoms=frontmatter.get("symptoms", []),
            severity=frontmatter.get("severity", "SEV-2"),
            estimated_resolution_minutes=estimated_minutes,
            diagnosis_steps=diagnosis_steps,
            mitigation_steps=mitigation_steps,
            verification_steps=verification_steps,
            prevention_steps=prevention_steps,
            metadata=frontmatter.get("metadata", {}),
            tags=tags,
            version=frontmatter.get("version", "1.0"),
            last_updated=frontmatter.get("last_updated", datetime.utcnow().isoformat()),
            source_file=source_file
        )

        self.parsed_runbooks.append(runbook)
        return runbook

    def parse_directory(self, dir_path: Union[str, Path], recursive: bool = True) -> List[Runbook]:
        """Parse all runbook files in a directory."""
        path = Path(dir_path)
        if not path.exists():
            logger.error(f"Directory not found: {dir_path}")
            return []

        pattern = "**/*.md" if recursive else "*.md"
        files = list(path.glob(pattern))

        runbooks = []
        for file_path in files:
            # Skip non-runbook markdown files
            if file_path.name.lower() in ["readme.md", "changelog.md", "license.md"]:
                continue

            runbook = self.parse_file(file_path)
            if runbook:
                runbooks.append(runbook)

        return runbooks

    def _generate_id(self, title: str) -> str:
        """Generate a runbook ID from title."""
        # Clean title for ID
        clean = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        return f"RB-{clean}-{timestamp}"

    def _parse_duration(self, duration_str: str) -> int:
        """Parse duration string to minutes."""
        duration_str = str(duration_str).lower().strip()

        # Try to extract number and unit
        match = re.match(r"(\d+)\s*(min|minute|minutes|hr|hour|hours|h|m)", duration_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if unit in ["hr", "hour", "hours", "h"]:
                return value * 60
            return value

        # Try just a number (assume minutes)
        match = re.match(r"(\d+)", duration_str)
        if match:
            return int(match.group(1))

        return 15  # default

    def _parse_section(self, body: str, section_key: str, section_title: str) -> List[RunbookStep]:
        """Parse a runbook section (Diagnosis, Mitigation, etc.)."""
        steps = []

        # Find section content
        section_content = self._extract_section_content(body, section_title)
        if not section_content:
            return steps

        # Parse numbered steps or bullet points
        # Pattern: number. title/description
        step_pattern = r"(?:^|\n)\s*(\d+)\.\s*(.+?)(?=\n\s*\d+\.|\n\s*[#*]|\Z)"

        for match in re.finditer(step_pattern, section_content, re.DOTALL | re.MULTILINE):
            step_num = int(match.group(1))
            step_content = match.group(2).strip()

            # Split title and description
            lines = step_content.split("\n")
            title = lines[0].strip()
            description = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

            # Extract code blocks
            commands = self._extract_code_blocks(step_content)

            # Extract expected output
            expected_output = self._extract_expected_output(step_content)

            # Extract rollback commands
            rollback_commands = self._extract_rollback_commands(step_content)

            # Extract prerequisites
            prerequisites = self._extract_prerequisites(step_content)

            # Extract risks
            risks = self._extract_risks(step_content)

            step = RunbookStep(
                step_number=step_num,
                title=title,
                description=description,
                commands=commands,
                expected_output=expected_output,
                rollback_commands=rollback_commands,
                prerequisites=prerequisites,
                risks=risks
            )
            steps.append(step)

        # If no numbered steps, try bullet points
        if not steps:
            bullet_pattern = r"(?:^|\n)\s*[-*•]\s*(.+?)(?=\n\s*[-*•]|\n\s*[#*]|\Z)"
            for i, match in enumerate(re.finditer(bullet_pattern, section_content, re.DOTALL | re.MULTILINE), 1):
                content = match.group(1).strip()
                lines = content.split("\n")
                title = lines[0].strip()
                description = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

                commands = self._extract_code_blocks(content)

                step = RunbookStep(
                    step_number=i,
                    title=title,
                    description=description,
                    commands=commands
                )
                steps.append(step)

        return steps

    def _extract_section_content(self, body: str, section_title: str) -> Optional[str]:
        """Extract content of a section by title."""
        # Try various heading formats
        patterns = [
            rf"(?i)##+\s*{re.escape(section_title)}[:\s]*\n(.+?)(?=\n##+|\Z)",
            rf"(?i)##+\s*{re.escape(section_title)}\s*\n(.+?)(?=\n##+|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        return None

    def _extract_code_blocks(self, content: str) -> List[str]:
        """Extract commands from code blocks."""
        commands = []

        # Find bash/shell code blocks
        pattern = r"```(?:bash|sh|shell|console|terminal)?\n(.+?)```"
        for match in re.finditer(pattern, content, re.DOTALL):
            code = match.group(1).strip()
            # Split into individual commands
            for line in code.split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("//"):
                    commands.append(line)

        # Also find inline commands (lines starting with $ or >)
        inline_pattern = r"(?:^|\n)\s*[\$>]\s*(.+?)(?=\n|$)"
        for match in re.finditer(inline_pattern, content, re.MULTILINE):
            cmd = match.group(1).strip()
            if cmd and cmd not in commands:
                commands.append(cmd)

        return commands

    def _extract_expected_output(self, content: str) -> Optional[str]:
        """Extract expected output annotation."""
        patterns = [
            r"(?i)expected[:\s]+(.+?)(?=\n|$)",
            r"(?i)output[:\s]+(.+?)(?=\n|$)",
            r"(?i)should show[:\s]+(.+?)(?=\n|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1).strip()

        return None

    def _extract_rollback_commands(self, content: str) -> List[str]:
        """Extract rollback commands."""
        commands = []

        # Look for rollback sections
        rollback_pattern = r"(?i)rollback[:\s]*\n(.*?)(?=\n\w+[:\s]*\n|\Z)"
        match = re.search(rollback_pattern, content, re.DOTALL)
        if match:
            rollback_content = match.group(1)
            commands = self._extract_code_blocks(rollback_content)

        return commands

    def _extract_prerequisites(self, content: str) -> List[str]:
        """Extract prerequisites."""
        prereqs = []

        patterns = [
            r"(?i)prerequisite[:\s]+(.+?)(?=\n|$)",
            r"(?i)prereq[:\s]+(.+?)(?=\n|$)",
            r"(?i)requires?[:\s]+(.+?)(?=\n|$)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content):
                prereqs.append(match.group(1).strip())

        return prereqs

    def _extract_risks(self, content: str) -> List[str]:
        """Extract risk annotations."""
        risks = []

        patterns = [
            r"(?i)risk[:\s]+(.+?)(?=\n|$)",
            r"(?i)warning[:\s]+(.+?)(?=\n|$)",
            r"(?i)caution[:\s]+(.+?)(?=\n|$)",
            r"(?i)⚠\s*(.+?)(?=\n|$)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content):
                risks.append(match.group(1).strip())

        return risks

    def _extract_tags_from_content(self, body: str, frontmatter: Dict) -> List[str]:
        """Extract tags from content and frontmatter."""
        tags = set()

        # From frontmatter
        if "tags" in frontmatter:
            tags.update(frontmatter["tags"])

        # From service name
        service = frontmatter.get("service", "")
        if service:
            tags.add(service.replace("-service", ""))

        # From symptoms
        for symptom in frontmatter.get("symptoms", []):
            symptom_lower = symptom.lower()
            if "connection" in symptom_lower:
                tags.add("connection_pool")
            if "latency" in symptom_lower or "slow" in symptom_lower:
                tags.add("latency")
            if "error" in symptom_lower or "500" in symptom_lower:
                tags.add("errors")
            if "timeout" in symptom_lower:
                tags.add("timeout")
            if "memory" in symptom_lower or "oom" in symptom_lower:
                tags.add("memory")
            if "cpu" in symptom_lower:
                tags.add("cpu")

        # From body content
        body_lower = body.lower()
        keyword_tags = {
            "deployment": ["deployment", "deploy", "release", "rollback"],
            "database": ["database", "db ", "sql", "query", "connection pool"],
            "cache": ["cache", "redis", "memcached"],
            "queue": ["queue", "kafka", "rabbitmq", "sqs"],
            "network": ["network", "dns", "latency", "timeout"],
            "security": ["security", "auth", "token", "certificate"],
            "configuration": ["config", "feature flag", "flag"],
        }

        for tag, keywords in keyword_tags.items():
            if any(kw in body_lower for kw in keywords):
                tags.add(tag)

        return sorted(tags)


class RunbookIngestor:
    """Ingests parsed runbooks into the vector knowledge base."""

    def __init__(self, vector_store: Optional[VectorStore] = None, persist_directory: str = "./chroma_db"):
        self.vector_store = vector_store or create_vector_store(persist_directory)
        self.parser = RunbookParser()

    def ingest_file(self, file_path: Union[str, Path]) -> Optional[Runbook]:
        """Parse and ingest a single runbook file."""
        runbook = self.parser.parse_file(file_path)
        if runbook:
            self._ingest_runbook(runbook)
        return runbook

    def ingest_directory(self, dir_path: Union[str, Path], recursive: bool = True) -> List[Runbook]:
        """Parse and ingest all runbooks in a directory."""
        runbooks = self.parser.parse_directory(dir_path, recursive)
        for runbook in runbooks:
            self._ingest_runbook(runbook)
        return runbooks

    def ingest_runbook(self, runbook: Runbook) -> str:
        """Ingest an already-parsed runbook."""
        return self._ingest_runbook(runbook)

    def _ingest_runbook(self, runbook: Runbook) -> str:
        """Store runbook in vector DB."""
        doc_id = self.vector_store.add_document(
            content=runbook.to_searchable_text(),
            metadata=runbook.to_metadata(),
            collection_name="runbooks",
            document_id=runbook.id
        )
        logger.info(f"Ingested runbook: {runbook.id} - {runbook.title}")
        return doc_id

    def search_runbooks(
        self,
        query: str,
        service: Optional[str] = None,
        severity: Optional[str] = None,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for relevant runbooks."""
        where = {}
        if service:
            where["service"] = service
        if severity:
            where["severity"] = severity

        results = self.vector_store.search(
            query=query,
            collection_name="runbooks",
            n_results=n_results,
            where=where if where else None
        )

        return [r.to_dict() for r in results]


def create_runbook_parser() -> RunbookParser:
    """Factory function to create a RunbookParser."""
    return RunbookParser()


def create_runbook_ingestor(persist_directory: str = "./chroma_db") -> RunbookIngestor:
    """Factory function to create a RunbookIngestor."""
    return RunbookIngestor(persist_directory=persist_directory)


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)

    # Sample runbook content
    sample_runbook = """---
title: "java-service: Connection Pool Exhaustion"
service: java-service
symptoms:
  - "High error rate on /api/* endpoints"
  - "Thread pool queue full in logs"
  - "Latency p99 > 30s"
severity: SEV-2
estimated_resolution: 15 min
tags: [connection_pool, database, java, deployment]
---

## Diagnosis
1. Check HikariCP metrics
   ```bash
   curl -s localhost:8080/actuator/metrics/hikaricp.connections.active
   curl -s localhost:8080/actuator/metrics/hikaricp.connections.idle
   curl -s localhost:8080/actuator/metrics/hikaricp.connections.pending
   ```
   Expected: Active connections near max pool size, pending > 0

2. Check application logs for pool exhaustion
   ```bash
   kubectl logs -l app=java-service -n production --tail=100 | grep -i "pool exhausted\|connection not available"
   ```

## Mitigation
1. **Immediate**: Rollback deployment
   ```bash
   kubectl rollout undo deployment/java-service -n production
   ```
   Risk: Brief service disruption during rollback

2. **If rollback not possible**: Scale replicas
   ```bash
   kubectl scale deployment java-service --replicas=20 -n production
   ```

3. **Config fix** (requires deploy):
   - Add `connectionTimeout: 5000`
   - Add `idleTimeout: 300000`
   - Set `maximumPoolSize: 50`

## Verification
1. Error rate < 0.1%
   ```bash
   curl -s localhost:8080/actuator/metrics/http.server.requests | jq '.measurements[] | select(.statistic=="COUNT")'
   ```

2. Latency p99 < 500ms
3. Active connections < 80% of pool
4. No "pool exhausted" logs for 5 min

## Prevention
1. Add connection pool config validation to CI
2. Integration test with load to verify pool sizing
3. Runbook review quarterly
"""

    parser = create_runbook_parser()
    runbook = parser.parse_content(sample_runbook, "sample-runbook.md")

    if runbook:
        print(f"Parsed runbook: {runbook.title}")
        print(f"  ID: {runbook.id}")
        print(f"  Service: {runbook.service}")
        print(f"  Severity: {runbook.severity}")
        print(f"  Estimated resolution: {runbook.estimated_resolution_minutes} min")
        print(f"  Tags: {runbook.tags}")
        print(f"  Diagnosis steps: {len(runbook.diagnosis_steps)}")
        print(f"  Mitigation steps: {len(runbook.mitigation_steps)}")
        print(f"  Verification steps: {len(runbook.verification_steps)}")
        print(f"  Prevention steps: {len(runbook.prevention_steps)}")

        print("\nAll commands:")
        for cmd in runbook.get_commands():
            print(f"  $ {cmd}")

        # Test ingestion
        ingestor = create_runbook_ingestor("./test_chroma_db_runbooks")
        ingestor.ingest_runbook(runbook)

        # Search
        print("\n=== Search for 'connection pool rollback' ===")
        results = ingestor.search_runbooks("connection pool rollback", service="java-service")
        for r in results:
            print(f"  Score: {r['score']:.3f} | {r['document']['metadata'].get('runbook_id')} | {r['document']['content'][:150]}...")

        ingestor.vector_store.close()

    print("\nDemo complete!")