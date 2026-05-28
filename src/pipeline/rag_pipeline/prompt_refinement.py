"""
Prompt Refinement Engine - maintains versioned internal answer-generation prompts
and supports iterative updates based on failure taxonomy.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import os

PROMPT_STORE = os.path.join(os.path.dirname(__file__), "prompt_versions.json")


@dataclass
class PromptVersion:
    version_id: str
    prompt_text: str
    created_at: str
    notes: Optional[str] = None


class PromptRefinementEngine:
    def __init__(self, default_prompt: Optional[str] = None):
        self.prompt_versions: List[PromptVersion] = []
        if not os.path.exists(PROMPT_STORE):
            # Create default prompt
            default_prompt = default_prompt or self._default_prompt()
            v = PromptVersion(version_id="v1", prompt_text=default_prompt, created_at=datetime.now().isoformat(), notes="Initial prompt")
            self.prompt_versions.append(v)
            self._persist()
        else:
            self._load()

    def _default_prompt(self) -> str:
        # Core rules as required in PART 6
        return (
            "You are a domain-grounded assistant. Answer only from the provided context. "
            "Do NOT use unrelated memory, prior examples, or stale topics. Do NOT switch domains. "
            "Do NOT hallucinate or invent facts. Do NOT make stronger claims than the evidence allows. "
            "If the context directly supports the answer, answer directly. "
            "If the context supports the answer through a short semantic restatement, answer using that grounded paraphrase. "
            "Only say 'insufficient context' if the answer cannot be supported even through a grounded semantic restatement. "
            "Prefer concise, evidence-bounded, domain-consistent answers. When you cite the source, include the chunk rank and a short excerpt."
        )

    def _persist(self):
        data = [v.__dict__ for v in self.prompt_versions]
        with open(PROMPT_STORE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load(self):
        with open(PROMPT_STORE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.prompt_versions = [PromptVersion(**d) for d in data]

    def get_current_prompt(self) -> str:
        return self.prompt_versions[-1].prompt_text

    def create_new_version(self, new_prompt_text: str, notes: Optional[str] = None) -> PromptVersion:
        v_id = f"v{len(self.prompt_versions)+1}"
        v = PromptVersion(version_id=v_id, prompt_text=new_prompt_text, created_at=datetime.now().isoformat(), notes=notes)
        self.prompt_versions.append(v)
        self._persist()
        return v

    def refine_prompt_from_failures(self, failures: List[Dict[str, Any]]) -> PromptVersion:
        """Generate a refined prompt based on observed failures. This is a deterministic rule-based refinement.

        For the initial implementation, we apply safe rules:
        - Increase emphasis on evidence-bounded paraphrase
        - Clarify abstention conditions
        - Add explicit domain consistency rule
        """
        base = self.get_current_prompt()
        additions = []
        for f in failures:
            cats = f.get("failure_taxonomy", [])
            if "kb_relevance_false_negative" in cats or "false_abstention" in cats:
                additions.append("If retrieved context includes semantically matching phrases or principle statements, allow a short grounded paraphrase instead of abstaining.")
            if "metric_inconsistency" in cats:
                additions.append("When lexical overlap is low but semantic similarity and reranker agree, prefer semantic evidence over lexical signals.")
            if "prompt_contamination" in cats:
                additions.append("Reject any prompt content or few-shot examples unrelated to the current domain.")

        if additions:
            new_prompt = base + "\n\n" + "\n".join(additions)
            v = self.create_new_version(new_prompt, notes="Refined based on failures: " + ",".join([str(f.get("failure_taxonomy","")) for f in failures]))
            return v

        # No changes
        return self.prompt_versions[-1]


# Provide a singleton engine for importers
_default_engine = PromptRefinementEngine()

def get_prompt_engine():
    return _default_engine
