"""Candidate mutation operators."""

from __future__ import annotations

import copy
import random
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence, Tuple

from open_evolve.core.types import Candidate, CandidateDraft, Task


class Operator(ABC):
    id = "operator"

    @abstractmethod
    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> Sequence[CandidateDraft]:
        raise NotImplementedError


class JsonFieldStepOperator(Operator):
    """Generate variants by adding fixed steps to an integer JSON field."""

    def __init__(self, field: str, steps: Sequence[int], operator_id: str = "json_field_step") -> None:
        self.field = field
        self.steps = list(steps)
        self.id = operator_id

    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> Sequence[CandidateDraft]:
        value = parent.artifact.get(self.field)
        if not isinstance(value, int):
            return []
        drafts: List[CandidateDraft] = []
        for step in self.steps:
            artifact = copy.deepcopy(parent.artifact)
            artifact[self.field] = value + step
            drafts.append(
                CandidateDraft(
                    artifact=artifact,
                    parent_ids=[parent.id],
                    operator_id=self.id,
                    plan="Set %s = %s + (%s)." % (self.field, value, step),
                    metadata={"field": self.field, "step": step},
                )
            )
        return drafts


class RandomJsonFieldOperator(Operator):
    """Randomly sample an integer field within a configured range."""

    def __init__(self, field: str, lower: int, upper: int, samples: int = 4, operator_id: str = "random_json_field") -> None:
        self.field = field
        self.lower = lower
        self.upper = upper
        self.samples = samples
        self.id = operator_id

    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> Sequence[CandidateDraft]:
        drafts: List[CandidateDraft] = []
        for _ in range(self.samples):
            artifact = copy.deepcopy(parent.artifact)
            artifact[self.field] = rng.randint(self.lower, self.upper)
            drafts.append(
                CandidateDraft(
                    artifact=artifact,
                    parent_ids=[parent.id],
                    operator_id=self.id,
                    plan="Randomly resample %s." % self.field,
                    metadata={"field": self.field, "lower": self.lower, "upper": self.upper},
                )
            )
        return drafts


class FileStringReplaceOperator(Operator):
    """Generate file-artifact variants by replacing text in one file."""

    def __init__(self, path: str, replacements: Sequence[Tuple[str, str]], operator_id: str = "file_string_replace") -> None:
        self.path = path
        self.replacements = list(replacements)
        self.id = operator_id

    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> Sequence[CandidateDraft]:
        files = parent.artifact.get("files")
        if not isinstance(files, dict) or self.path not in files:
            return []
        content = str(files[self.path])
        drafts: List[CandidateDraft] = []
        for old, new in self.replacements:
            if old not in content:
                continue
            artifact = copy.deepcopy(parent.artifact)
            artifact["files"][self.path] = content.replace(old, new)
            drafts.append(
                CandidateDraft(
                    artifact=artifact,
                    parent_ids=[parent.id],
                    operator_id=self.id,
                    plan="Replace %r with %r in %s." % (old, new, self.path),
                    metadata={"path": self.path, "old": old, "new": new},
                )
            )
        return drafts


class FileAppendOperator(Operator):
    """Append candidate text snippets to one file."""

    def __init__(self, path: str, snippets: Sequence[str], operator_id: str = "file_append") -> None:
        self.path = path
        self.snippets = list(snippets)
        self.id = operator_id

    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> Sequence[CandidateDraft]:
        files = parent.artifact.get("files")
        if not isinstance(files, dict) or self.path not in files:
            return []
        content = str(files[self.path])
        drafts: List[CandidateDraft] = []
        for snippet in self.snippets:
            artifact = copy.deepcopy(parent.artifact)
            artifact["files"][self.path] = content + snippet
            drafts.append(
                CandidateDraft(
                    artifact=artifact,
                    parent_ids=[parent.id],
                    operator_id=self.id,
                    plan="Append snippet to %s." % self.path,
                    metadata={"path": self.path},
                )
            )
        return drafts


class RegexNumberJitterOperator(Operator):
    """Jitter integer constants in a source artifact."""

    def __init__(
        self,
        path: Optional[str] = None,
        samples: int = 4,
        changes_per_sample: int = 2,
        jitter: int = 5000,
        lower: int = 0,
        upper: int = 100000,
        min_abs_value: int = 1000,
        operator_id: str = "regex_number_jitter",
    ) -> None:
        self.path = path
        self.samples = int(samples)
        self.changes_per_sample = int(changes_per_sample)
        self.jitter = int(jitter)
        self.lower = int(lower)
        self.upper = int(upper)
        self.min_abs_value = int(min_abs_value)
        self.id = operator_id

    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> Sequence[CandidateDraft]:
        path, content = self._select_source(parent)
        if not content:
            return []
        matches = [
            match
            for match in re.finditer(r"(?<![A-Za-z0-9_.])-?\d+(?![A-Za-z0-9_.])", content)
            if abs(int(match.group(0))) >= self.min_abs_value
        ]
        if not matches:
            return []

        drafts: List[CandidateDraft] = []
        for sample_idx in range(max(1, self.samples)):
            selected = rng.sample(matches, k=min(len(matches), max(1, self.changes_per_sample)))
            replacements = {}
            for match in selected:
                old_value = int(match.group(0))
                delta = rng.randint(-self.jitter, self.jitter)
                if delta == 0:
                    delta = self.jitter
                new_value = max(self.lower, min(self.upper, old_value + delta))
                replacements[(match.start(), match.end())] = str(new_value)

            new_content_parts = []
            cursor = 0
            for (start, end), value in sorted(replacements.items()):
                new_content_parts.append(content[cursor:start])
                new_content_parts.append(value)
                cursor = end
            new_content_parts.append(content[cursor:])
            new_content = "".join(new_content_parts)
            if new_content == content:
                continue

            artifact = copy.deepcopy(parent.artifact)
            if path:
                artifact.setdefault("files", {})[path] = new_content
            else:
                artifact["code"] = new_content
            drafts.append(
                CandidateDraft(
                    artifact=artifact,
                    parent_ids=[parent.id],
                    operator_id=self.id,
                    plan="Jitter integer constants in %s." % (path or "code"),
                    metadata={
                        "path": path,
                        "sample_idx": sample_idx,
                        "changes": len(replacements),
                        "jitter": self.jitter,
                    },
                )
            )
        return drafts

    def _select_source(self, parent: Candidate) -> tuple[Optional[str], str]:
        files = parent.artifact.get("files")
        if isinstance(files, dict):
            if self.path and isinstance(files.get(self.path), str):
                return self.path, files[self.path]
            if len(files) == 1:
                key, value = next(iter(files.items()))
                return str(key), str(value)
        code = parent.artifact.get("code")
        if isinstance(code, str):
            return None, code
        return None, ""


class RegexFloatJitterOperator(Operator):
    """Jitter floating-point constants in a source artifact."""

    _FLOAT_RE = re.compile(r"(?<![A-Za-z0-9_])(-?(?:\d+\.\d*|\.\d+|\d+[eE][+-]?\d+)(?:[eE][+-]?\d+)?)(?![A-Za-z0-9_])")

    def __init__(
        self,
        path: Optional[str] = None,
        samples: int = 4,
        changes_per_sample: int = 2,
        relative_jitter: float = 0.15,
        absolute_jitter: float = 0.0,
        min_abs_value: float = 1e-9,
        lower: Optional[float] = None,
        upper: Optional[float] = None,
        operator_id: str = "regex_float_jitter",
    ) -> None:
        self.path = path
        self.samples = int(samples)
        self.changes_per_sample = int(changes_per_sample)
        self.relative_jitter = float(relative_jitter)
        self.absolute_jitter = float(absolute_jitter)
        self.min_abs_value = float(min_abs_value)
        self.lower = lower
        self.upper = upper
        self.id = operator_id

    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> Sequence[CandidateDraft]:
        path, content = self._select_source(parent)
        if not content:
            return []
        matches = []
        for match in self._FLOAT_RE.finditer(content):
            try:
                value = float(match.group(0))
            except ValueError:
                continue
            if abs(value) >= self.min_abs_value:
                matches.append((match, value))
        if not matches:
            return []

        drafts: List[CandidateDraft] = []
        for sample_idx in range(max(1, self.samples)):
            selected = rng.sample(matches, k=min(len(matches), max(1, self.changes_per_sample)))
            replacements = {}
            for match, old_value in selected:
                scale = 1.0 + rng.uniform(-self.relative_jitter, self.relative_jitter)
                delta = rng.uniform(-self.absolute_jitter, self.absolute_jitter) if self.absolute_jitter else 0.0
                new_value = old_value * scale + delta
                if self.lower is not None:
                    new_value = max(float(self.lower), new_value)
                if self.upper is not None:
                    new_value = min(float(self.upper), new_value)
                replacements[(match.start(), match.end())] = "%.12g" % new_value

            new_content_parts = []
            cursor = 0
            for (start, end), value in sorted(replacements.items()):
                new_content_parts.append(content[cursor:start])
                new_content_parts.append(value)
                cursor = end
            new_content_parts.append(content[cursor:])
            new_content = "".join(new_content_parts)
            if new_content == content:
                continue

            artifact = copy.deepcopy(parent.artifact)
            if path:
                artifact.setdefault("files", {})[path] = new_content
            else:
                artifact["code"] = new_content
            drafts.append(
                CandidateDraft(
                    artifact=artifact,
                    parent_ids=[parent.id],
                    operator_id=self.id,
                    plan="Jitter floating-point constants in %s." % (path or "code"),
                    metadata={
                        "path": path,
                        "sample_idx": sample_idx,
                        "changes": len(replacements),
                        "relative_jitter": self.relative_jitter,
                        "absolute_jitter": self.absolute_jitter,
                    },
                )
            )
        return drafts

    def _select_source(self, parent: Candidate) -> tuple[Optional[str], str]:
        files = parent.artifact.get("files")
        if isinstance(files, dict):
            if self.path and isinstance(files.get(self.path), str):
                return self.path, files[self.path]
            if len(files) == 1:
                key, value = next(iter(files.items()))
                return str(key), str(value)
        code = parent.artifact.get("code")
        if isinstance(code, str):
            return None, code
        return None, ""


class OperatorLibrary:
    def __init__(self, operators: Sequence[Operator]) -> None:
        self.operators = list(operators)

    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> List[CandidateDraft]:
        drafts: List[CandidateDraft] = []
        for operator in self.operators:
            drafts.extend(operator.propose(task, parent, rng))
        return drafts
