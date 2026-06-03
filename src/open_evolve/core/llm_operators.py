"""LLM-backed mutation operators."""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import tempfile
import time
from pathlib import Path
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


class CodexCliEditOperator(Operator):
    """Use Codex CLI as an agentic code-edit harness for one source file."""

    def __init__(
        self,
        codex_bin: Optional[str] = None,
        profile: Optional[str] = None,
        path: Optional[str] = None,
        samples: int = 1,
        timeout_seconds: float = 300.0,
        sandbox: str = "workspace-write",
        max_context_chars: int = 80000,
        extra_instructions: str = "",
        operator_id: str = "codex_cli_edit",
    ) -> None:
        self.codex_bin = codex_bin or self._default_codex_bin()
        self.profile = profile if profile is not None else os.environ.get("OPEN_EVOLVE_CODEX_PROFILE", "azure_uami")
        self.path = path
        self.samples = int(samples)
        self.timeout_seconds = float(timeout_seconds)
        self.sandbox = sandbox
        self.max_context_chars = int(max_context_chars)
        self.extra_instructions = extra_instructions
        self.id = operator_id

    def propose(self, task: Task, parent: Candidate, rng: random.Random) -> Sequence[CandidateDraft]:
        path, code = self._select_file(task, parent)
        if not path or not code:
            return []

        context = str(task.metadata.get("agent_context") or task.metadata.get("statement") or "")[: self.max_context_chars]
        feedback = AzureCodeEditOperator._feedback(parent)
        drafts = []
        for sample_idx in range(max(1, self.samples)):
            with tempfile.TemporaryDirectory(prefix="open_evolve_codex_") as tmp:
                workspace = Path(tmp)
                rel_path = self._safe_rel_path(path)
                target = workspace / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(code, encoding="utf-8")
                (workspace / "TASK_CONTEXT.md").write_text(context, encoding="utf-8")
                (workspace / "EVAL_FEEDBACK.json").write_text(feedback + "\n", encoding="utf-8")

                prompt = self._prompt(task, rel_path.as_posix(), sample_idx)
                final_text, stdout, stderr, returncode = self._run_codex(workspace, prompt)
                if returncode != 0 or not target.exists():
                    continue
                new_code = target.read_text(encoding="utf-8", errors="replace")
                if not new_code.strip() or new_code.strip() == code.strip():
                    continue
                plan = self._plan_from_final_text(final_text) or "Codex CLI edited %s." % path
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
                        plan=plan,
                        metadata={
                            "path": path,
                            "sample_idx": sample_idx,
                            "codex_returncode": returncode,
                            "codex_final": final_text[:2000],
                            "codex_stdout_tail": stdout[-2000:],
                            "codex_stderr_tail": stderr[-2000:],
                        },
                    )
                )
        return drafts

    @staticmethod
    def _default_codex_bin() -> str:
        configured = os.environ.get("OPEN_EVOLVE_CODEX_BIN")
        if configured:
            return configured
        helper = Path("/home/azureuser/zicong/OpenAgentScaler/scripts/codex-azure-mi")
        if helper.exists():
            return str(helper)
        return "codex"

    def _run_codex(self, workspace: Path, prompt: str) -> tuple[str, str, str, int]:
        cmd = [self.codex_bin]
        if self.profile and self.profile.lower() not in {"none", "null", "false"}:
            cmd.extend(["-p", self.profile])
        cmd.extend(
            [
                "exec",
                "--json",
                "--ephemeral",
                "--skip-git-repo-check",
                "-C",
                str(workspace),
                "--sandbox",
                self.sandbox,
                "-c",
                'approval_policy="never"',
                prompt,
            ]
        )
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._process_text(exc.stdout)
            stderr = self._process_text(exc.stderr)
            stderr = (stderr + "\n" if stderr else "") + "Codex CLI timed out after %.1f seconds." % self.timeout_seconds
            return "", stdout, stderr, 124
        return self._last_agent_message(proc.stdout), proc.stdout, proc.stderr, proc.returncode

    @staticmethod
    def _process_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    @staticmethod
    def _last_agent_message(stdout: str) -> str:
        last = ""
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except Exception:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if isinstance(item, dict) and item.get("type") == "agent_message":
                last = str(item.get("text") or "")
        return last

    @staticmethod
    def _plan_from_final_text(text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return ""
        try:
            payload = json.loads(stripped)
        except Exception:
            return stripped[:500]
        if isinstance(payload, dict):
            return str(payload.get("plan") or payload.get("summary") or "")[:500]
        return stripped[:500]

    @staticmethod
    def _safe_rel_path(path: str) -> Path:
        rel = Path(path)
        if rel.is_absolute() or ".." in rel.parts:
            return Path(rel.name or "solution.py")
        return rel

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
            return preferred or "solution.py", code
        return "", ""

    def _prompt(self, task: Task, path: str, sample_idx: int) -> str:
        extra = ("\n\nExtra instructions:\n%s" % self.extra_instructions.strip()) if self.extra_instructions.strip() else ""
        return (
            "You are a Codex code-edit harness inside an optimization loop.\n"
            "Working directory contains:\n"
            "- {path}: the candidate source file to edit in place\n"
            "- TASK_CONTEXT.md: benchmark context and constraints\n"
            "- EVAL_FEEDBACK.json: latest evaluation score and metrics\n\n"
            "Use only files in the current working directory. TASK_CONTEXT.md already contains the "
            "benchmark docs and constraints needed for this edit. Do not search or read paths outside "
            "the working directory, and do not run commands such as `find /`, `grep -R /`, or `locate`.\n\n"
            "Task id: {task_id}\n"
            "Benchmark family: {family}\n"
            "Objective: {objective}\n"
            "Variant index: {sample_idx}\n\n"
            "Edit only {path}. Preserve required entrypoints, file schema, and benchmark constraints. "
            "Make one conservative improvement that is likely to increase objective while staying valid. "
            "Do not modify evaluator files or hidden benchmark assumptions. "
            "When done, reply with one JSON object such as {{\"plan\":\"short description\",\"changed\":true}}."
            "{extra}"
        ).format(
            path=path,
            task_id=task.id,
            family=task.family,
            objective=task.objective,
            sample_idx=sample_idx,
            extra=extra,
        )
