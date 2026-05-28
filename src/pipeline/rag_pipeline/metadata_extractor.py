"""
Enhanced Metadata Extraction for Production RAG Pipeline
Implements comprehensive metadata extraction for precision retrieval
"""

import re
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ChunkMetadata:
    """Comprehensive metadata for retrieval safety and precision"""
    # Core identifiers
    doc_id: str
    chunk_id: str
    
    # Document information
    doc_title: str
    doc_type: str
    source_type: str
    source_path: str
    
    # Hierarchy
    section_title: str
    section_path: str
    
    # Domain classification
    domain: str
    
    # Optional/defaulted fields
    subsection_title: str = ""
    hierarchy_depth: int = 0
    subdomain: str = ""
    topic: str = ""
    subtopic: str = ""
    
    # Content quality
    keywords: List[str] = None
    named_entities: List[str] = None
    abbreviations: Dict[str, str] = None
    
    # Scope and safety
    negative_scope_tags: List[str] = None
    distractor_guard_metadata: Dict[str, Any] = None
    semantic_scope: str = ""
    
    # Authority and reliability
    authority_level: str = "informational"  # critical, high, medium, low
    source_reliability_score: float = 0.5
    confidence_level: float = 0.0
    
    # Temporal
    version: str = ""
    effective_date: str = ""
    status: str = "active"
    
    # Context
    audience: str = "technical"
    language: str = "en"
    related_topics: List[str] = None
    
    # Evidence quality
    is_contradictory: bool = False
    contradicting_topics: List[str] = None
    
    # Lifecycle
    lifecycle_stage: str = "current"
    product_module: str = ""
    region_or_standard: str = "global"
    
    # Summary for retrieval
    canonical_summary: str = ""
    retrieval_intent_tags: List[str] = None
    
    def __post_init__(self):
        """Initialize list/dict defaults"""
        if self.keywords is None:
            self.keywords = []
        if self.named_entities is None:
            self.named_entities = []
        if self.abbreviations is None:
            self.abbreviations = {}
        if self.negative_scope_tags is None:
            self.negative_scope_tags = []
        if self.related_topics is None:
            self.related_topics = []
        if self.retrieval_intent_tags is None:
            self.retrieval_intent_tags = []
        if self.contradicting_topics is None:
            self.contradicting_topics = []
        if self.distractor_guard_metadata is None:
            self.distractor_guard_metadata = {
                "possible_confusions": [],
                "retrieval_guard_terms": [],
                "exclusion_indicators": []
            }


class MetadataExtractor:
    """
    Extracts rich metadata from documents and chunks.
    Focuses on precision, retrieval safety, and hard distractor prevention.
    """
    
    AUTOSAR_DOMAINS = {
        "architecture": ["goals", "layers", "stack", "methodology"],
        "software": ["transferability", "modules", "components", "libraries"],
        "standardization": ["product", "lifecycle", "requirements", "interfaces"],
        "implementation": ["tools", "ui", "workflow", "process"],
        "communication": ["ipc", "network", "signal", "routing"],
        "security": ["safety", "protection", "authentication", "verification"],
    }
    
    HARD_DISTRACTORS = {
        "general_automotive": ["vehicle", "automotive", "car", "transmission", "engine"],
        "infotainment": ["infotainment", "gpu", "graphics", "display", "hmi"],
        "linux": ["linux", "unix", "posix", "kernel", "operating system"],
        "middleware": ["middleware", "message bus", "rpc", "corba", "soap"],
        "cloud": ["cloud", "iot", "connectivity", "mobile", "network services"],
    }
    
    def __init__(self, doc_title: str = "", doc_path: str = "", domain: str = "AUTOSAR"):
        self.doc_title = doc_title
        self.doc_path = doc_path
        self.domain = domain
        self.sections = []
        self.abbreviation_map = {}
        self._build_abbreviation_map()
    
    def _build_abbreviation_map(self):
        """Build common abbreviations for the domain"""
        self.abbreviation_map = {
            "ECU": "Electronic Control Unit",
            "AUTOSAR": "Automotive Open System Architecture",
            "SWC": "Software Component",
            "RTE": "Runtime Environment",
            "COM": "Communication Manager",
            "DEM": "Diagnostic Event Manager",
            "NM": "Network Management",
            "DCMOTOR": "DC Motor",
            "API": "Application Programming Interface",
            "SW": "Software",
            "HW": "Hardware",
            "OS": "Operating System",
            "IoT": "Internet of Things",
            "IPC": "Inter-Process Communication",
        }
    
    def extract_sections(self, text: str) -> List[Tuple[str, int]]:
        """Extract section hierarchy from text"""
        sections = []
        for match in re.finditer(r'^(#{1,6})\s+(.+)$', text, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            sections.append((title, level))
        return sections
    
    def extract_section_context(self, text: str, chunk_start: int) -> Tuple[str, str, str]:
        """Extract current section context for a position in text"""
        section_title = ""
        subsection_title = ""
        section_path = ""
        
        lines_before = text[:chunk_start].split('\n')
        current_level = 999
        
        for line in reversed(lines_before):
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                
                if level == 1:
                    section_title = title
                    section_path = title
                elif level == 2 and not subsection_title:
                    subsection_title = title
                    section_path = f"{section_title} > {title}"
        
        return section_title, subsection_title, section_path
    
    def extract_named_entities(self, text: str) -> List[str]:
        """Extract named entities and proper nouns"""
        entities = set()
        
        # ECU/Component names (CamelCase)
        for match in re.finditer(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text):
            entities.add(match.group())
        
        # All-caps terms (likely technical terms or acronyms)
        for match in re.finditer(r'\b([A-Z]{2,})\b', text):
            term = match.group(1)
            if len(term) <= 5 and term in self.abbreviation_map:
                entities.add(term)
        
        # Architecture/software concepts
        patterns = [
            r'AUTOSAR\s+(?:stack|architecture|methodology)',
            r'Software\s+(?:Component|Module|Library)',
            r'Runtime\s+Environment',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                entities.add(match.group())
        
        return list(entities)[:20]  # Top 20 entities
    
    def extract_keywords(self, text: str, top_n: int = 15) -> List[str]:
        """Extract domain-specific keywords"""
        from collections import Counter
        
        # Split into words and filter
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were',
            'in', 'on', 'at', 'to', 'of', 'for', 'with', 'by', 'as', 'be',
            'this', 'that', 'these', 'those', 'it', 'if', 'not', 'all',
            'have', 'has', 'should', 'may', 'can', 'must', 'will', 'would',
            'could', 'should', 'do', 'does', 'did', 'been', 'being',
        }
        
        filtered_words = [w for w in words if len(w) > 3 and w not in stop_words]
        
        # Count frequencies
        freq = Counter(filtered_words)
        keywords = [word for word, _ in freq.most_common(top_n)]
        
        return keywords
    
    def detect_abbreviations_in_chunk(self, text: str) -> Dict[str, str]:
        """Detect abbreviations used in chunk"""
        found_abbr = {}
        
        for abbr, full in self.abbreviation_map.items():
            if abbr in text:
                found_abbr[abbr] = full
        
        return found_abbr
    
    def detect_hard_distractors(self, text: str) -> Dict[str, List[str]]:
        """Detect hard distractor terms that should be excluded"""
        distractor_map = {
            "off_topic": [],
            "partial_match": [],
            "likely_confusion": [],
        }
        
        for category, terms in self.HARD_DISTRACTORS.items():
            for term in terms:
                if re.search(r'\b' + term + r'\b', text, re.IGNORECASE):
                    if category in ["infotainment", "linux", "cloud"]:
                        distractor_map["off_topic"].append(term)
                    elif category == "middleware":
                        distractor_map["partial_match"].append(term)
                    else:
                        distractor_map["likely_confusion"].append(term)
        
        return distractor_map
    
    def generate_negative_scope_tags(self, text: str, domain: str = "AUTOSAR") -> List[str]:
        """Generate explicit scope exclusions"""
        tags = []
        
        if "infotainment" in text.lower() or "gpu" in text.lower():
            tags.append("NOT_for_infotainment_systems")
        
        if "linux" in text.lower() or "unix" in text.lower():
            tags.append("NOT_OS_dependent")
        
        if "cloud" in text.lower() or "iot" in text.lower():
            tags.append("NOT_cloud_architecture")
        
        if "middleware" in text.lower():
            tags.append("NOT_generic_middleware")
        
        return tags
    
    def create_distractor_guard(self, text: str) -> Dict[str, Any]:
        """Create metadata guard against hard distractors"""
        distractors = self.detect_hard_distractors(text)
        
        return {
            "possible_confusions": [
                "general automotive middleware",
                "embedded Linux architecture",
                "vehicle infotainment systems",
                "generic middleware patterns",
                "cloud-based vehicle services",
            ],
            "retrieval_guard_terms": [
                "ECU standardization",
                "software transferability",
                "product life cycle",
                "AUTOSAR compliance",
                "standardized interfaces",
            ],
            "exclusion_indicators": distractors.get("off_topic", []),
            "distractor_count": sum(len(v) for v in distractors.values()),
        }
    
    def generate_canonical_summary(self, text: str, title: str = "") -> str:
        """Generate concise, retrieval-focused summary"""
        # Extract first 2-3 meaningful sentences
        sentences = re.split(r'[.!?]+', text.strip())
        summary_sentences = []
        
        for sent in sentences[:3]:
            sent = sent.strip()
            if len(sent) > 20 and len(summary_sentences) < 3:
                summary_sentences.append(sent)
        
        summary = ". ".join(summary_sentences)
        if title:
            summary = f"{title}: {summary}"
        
        return summary[:200]  # Truncate to 200 chars
    
    def generate_retrieval_intent_tags(self, text: str) -> List[str]:
        """Generate tags for retrieval intent matching"""
        tags = []
        
        # Question about goals/purposes
        if re.search(r'(goal|purpose|objective|aim|target)', text, re.IGNORECASE):
            tags.append("goal_or_purpose")
        
        # Architecture/structure
        if re.search(r'(architecture|structure|layer|component|module)', text, re.IGNORECASE):
            tags.append("architecture")
        
        # Process/workflow
        if re.search(r'(process|workflow|step|procedure|method)', text, re.IGNORECASE):
            tags.append("process_workflow")
        
        # Requirements/specification
        if re.search(r'(requirement|specification|constraint|must|should)', text, re.IGNORECASE):
            tags.append("requirement")
        
        # Example/demonstration
        if re.search(r'(example|instance|demonstrate|show|illustrate)', text, re.IGNORECASE):
            tags.append("example")
        
        # Definition
        if re.search(r'(define|definition|is|means|refers to)', text, re.IGNORECASE):
            tags.append("definition")
        
        # Benefit/advantage
        if re.search(r'(benefit|advantage|improve|increase|reduce)', text, re.IGNORECASE):
            tags.append("benefit_or_advantage")
        
        # Standardization/compliance
        if re.search(r'(standard|standardize|comply|compliance)', text, re.IGNORECASE):
            tags.append("standardization")
        
        return tags
    
    def create_metadata(
        self,
        chunk_text: str,
        chunk_id: str,
        section_title: str = "",
        subsection_title: str = "",
        authority_level: str = "high",
        confidence: float = 0.8
    ) -> ChunkMetadata:
        """Create comprehensive metadata for a chunk"""
        
        # Extract section path
        section_path = section_title
        if subsection_title:
            section_path = f"{section_title} > {subsection_title}"
        
        # Extract content-based metadata
        keywords = self.extract_keywords(chunk_text)
        named_entities = self.extract_named_entities(chunk_text)
        abbreviations = self.detect_abbreviations_in_chunk(chunk_text)
        negative_scope = self.generate_negative_scope_tags(chunk_text)
        distractor_guard = self.create_distractor_guard(chunk_text)
        canonical_summary = self.generate_canonical_summary(chunk_text, section_title)
        retrieval_tags = self.generate_retrieval_intent_tags(chunk_text)
        
        # Determine domain/topic
        topic = "AUTOSAR"
        subtopic = "general"
        for domain, topics in self.AUTOSAR_DOMAINS.items():
            for t in topics:
                if t in chunk_text.lower():
                    topic = domain
                    subtopic = t
                    break
        
        return ChunkMetadata(
            doc_id="autosar_doc_001",
            chunk_id=chunk_id,
            doc_title=self.doc_title or "AUTOSAR Document",
            doc_type="technical_specification",
            source_type="pdf",
            source_path=self.doc_path or "unknown",
            section_title=section_title,
            section_path=section_path,
            subsection_title=subsection_title,
            domain="AUTOSAR",
            topic=topic,
            subtopic=subtopic,
            keywords=keywords,
            named_entities=named_entities,
            abbreviations=abbreviations,
            negative_scope_tags=negative_scope,
            distractor_guard_metadata=distractor_guard,
            authority_level=authority_level,
            source_reliability_score=0.95,
            confidence_level=confidence,
            semantic_scope=f"Covers {topic}:{subtopic} in {section_title}",
            canonical_summary=canonical_summary,
            retrieval_intent_tags=retrieval_tags,
        )
    
    def to_dict(self, metadata: ChunkMetadata) -> Dict[str, Any]:
        """Convert metadata to dictionary"""
        return asdict(metadata)
