"""LLM-backed mutation operators."""

from __future__ import annotations

import json
import random
import re
import time
from typing import Optional, Sequence

from open_evolve.core.operators import Operator
from open_evolve.core.types import Candidate, CandidateDraft, Task
from open_evolve.models.azure_openai import AzureOpenAIResponsesClient


class AzureCodeEditOperator(Operator):
    """Ask Azure OpenAI to revise one source file in a candidate artifact."""

    def __init__(
        self,
        client: Optional[AzureOpenAIResponsesClient] = None,
        path: Optional[str] = None,
        samples: int = 1,
        max_output_tokens: int = 4096,
        request_retries: int = 2,
        retry_delay_seconds: float = 5.0,
        operator_id: str = "azure_code_edit",
    ) -> None:
        self.client = client or AzureOpenAIResponsesClient.from_env()
        self.path = path
        self.samples = int(samples)
        self.max_output_tokens = int(max_output_tokens)
        self.request_retries = max(1, int(request_retries))
        self.retry_delay_seconds = float(retry_delay_seconds)
        self.id = operator_id

    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> Sequence[CandidateDraft]:
        path, code = self._select_file(task, parent)
        if not path or not code:
            return []

        feedback = self._feedback(parent)
        context = str(task.metadata.get("agent_context") or task.metadata.get("statement") or "")[:20000]
        drafts = []
        for sample_idx in range(max(1, self.samples)):
            prompt = self._prompt(task=task, path=path, code=code, feedback=feedback, context=context, sample_idx=sample_idx)
            text = self._complete(prompt)
            if not text.strip():
                continue
            plan, new_code = self._parse_response(text)
            if not new_code.strip() or new_code.strip() == code.strip():
                continue
            artifact = json.loads(json.dumps(parent.artifact))
            if "files" in artifact and isinstance(artifact["files"], dict):
                artifact["files"][path] = new_code
            else:
                artifact["code"] = new_code
            drafts.append(
                CandidateDraft(
                    artifact=artifact,
                    parent_ids=[parent.id],
                    operator_id=self.id,
                    plan=plan or "LLM code revision for %s." % path,
                    metadata={"path": path, "sample_idx": sample_idx, "parent_score": parent.score.objective if parent.score else None},
                )
            )
        return drafts

    def _complete(self, prompt: str) -> str:
        last_error = ""
        for attempt in range(self.request_retries):
            try:
                return self.client.complete_text(
                    prompt=prompt,
                    system=(
                        "You are optimizing benchmark code. Return only the complete replacement "
                        "source file. Do not include explanations."
                    ),
                    max_output_tokens=self.max_output_tokens,
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt + 1 < self.request_retries:
                    time.sleep(self.retry_delay_seconds)
        return ""

    def _select_file(self, task: Task, parent: Candidate) -> tuple[str, str]:
        files = parent.artifact.get("files")
        preferred = self.path or str(task.metadata.get("candidate_destination_rel") or task.metadata.get("initial_program_rel") or "")
        if isinstance(files, dict):
            if preferred and isinstance(files.get(preferred), str):
                return preferred, files[preferred]
            if len(files) == 1:
                key, value = next(iter(files.items()))
                return str(key), str(value)
        code = parent.artifact.get("code")
        if isinstance(code, str):
            return preferred or "solution.cpp", code
        return "", ""

    @staticmethod
    def _feedback(parent: Candidate) -> str:
        if parent.score is None:
            return "No score yet."
        payload = {
            "objective": parent.score.objective,
            "feasible": parent.score.feasible,
            "metrics": parent.score.metrics,
            "cost": parent.score.cost,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)[:20000]

    @staticmethod
    def _prompt(task: Task, path: str, code: str, feedback: str, context: str, sample_idx: int) -> str:
        return (
            "Benchmark family: %s\n"
            "Task id: %s\n"
            "Objective: %s\n"
            "File to replace: %s\n"
            "Variant index: %d\n\n"
            "Task context:\n%s\n\n"
            "Latest evaluation feedback:\n%s\n\n"
            "Current source:\n```text\n%s\n```\n\n"
            "Produce one conservative improvement. Preserve required entrypoints, file schema, "
            "and benchmark constraints. Output only the complete replacement source file."
        ) % (task.family, task.id, task.objective, path, sample_idx, context, feedback, code)

    @staticmethod
    def _parse_response(text: str) -> tuple[str, str]:
        stripped = text.strip()
        parsed = None
        candidates = [stripped]
        json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
        if json_block:
            candidates.insert(0, json_block.group(1))
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except Exception:
                continue
            if isinstance(value, dict) and isinstance(value.get("code"), str):
                parsed = value
                break
        if parsed is not None:
            return str(parsed.get("plan") or ""), str(parsed["code"])

        code_block = re.search(r"```(?:[A-Za-z0-9_+.-]+)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        if code_block:
            return "LLM returned fenced source.", code_block.group(1)
        return "LLM returned raw source.", stripped
