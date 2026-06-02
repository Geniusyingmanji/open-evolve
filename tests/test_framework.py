import tempfile
import unittest
from pathlib import Path

from open_evolve.benchmarks.local_command import LocalCommandBenchmarkAdapter
from open_evolve.benchmarks.config_loader import load_candidate_draft, load_task_config
from open_evolve.benchmarks.toy_numeric import ToyNumericBenchmark
from open_evolve.core.artifact_store import FileArtifactStore
from open_evolve.core.archive import CandidateArchive
from open_evolve.core.feedback_compute import estimate_effective_feedback_compute
from open_evolve.core.llm_operators import AzureCodeEditOperator
from open_evolve.core.memory import VerifiedMemoryStore
from open_evolve.core.operators import (
    FileAppendOperator,
    FileStringReplaceOperator,
    JsonFieldStepOperator,
    OperatorLibrary,
    RegexFloatJitterOperator,
    RegexNumberJitterOperator,
)
from open_evolve.core.process_evaluator import evaluate_process_quality
from open_evolve.core.search_controller import ArchiveSearchController, GreedySearchController, SearchConfig
from open_evolve.core.trace_recorder import TraceRecorder
from open_evolve.core.types import Candidate, CandidateDraft, Task
from open_evolve.harness.governance import HarnessPromotionEvidence, evaluate_promotion
from open_evolve.harness.harness_spec import HarnessSpec
from open_evolve.harness.mutation import mutate_policy
from open_evolve.harness.registry import HarnessRegistry
from open_evolve.experiments.harness_ablation import HarnessAblationRunner
from open_evolve.experiments.reporting import write_ablation_json, write_ablation_markdown
from open_evolve.models.azure_openai import AzureOpenAIConfig, AzureOpenAIResponsesClient
from open_evolve.benchmarks._subprocess_json import extract_prefixed_json


class FrameworkTests(unittest.TestCase):
    def test_toy_search_reaches_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = ToyNumericBenchmark(target=10)
            task = benchmark.load_task("toy")
            trace = TraceRecorder(root / "trace.jsonl")
            controller = GreedySearchController(
                adapter=benchmark,
                operators=OperatorLibrary([JsonFieldStepOperator("x", [-5, -2, -1, 1, 2, 5])]),
                store=FileArtifactStore(root / "runs"),
                config=SearchConfig(max_iterations=4, max_evaluations=40, seed=0),
                trace=trace,
            )
            result = controller.run(task, run_id="test_run")
            self.assertIsNotNone(result.best)
            self.assertEqual(result.best.artifact["x"], 10)
            self.assertEqual(result.best.score.objective, 0.0)
            self.assertTrue((root / "runs" / "test_run" / "summary.json").exists())

    def test_archive_search_reaches_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = ToyNumericBenchmark(target=10)
            task = benchmark.load_task("toy")
            controller = ArchiveSearchController(
                adapter=benchmark,
                operators=OperatorLibrary([JsonFieldStepOperator("x", [-5, -2, -1, 1, 2, 5])]),
                store=FileArtifactStore(root / "runs"),
                config=SearchConfig(max_iterations=4, max_evaluations=40, parent_pool_size=2, seed=0),
            )
            result = controller.run(task, run_id="archive_run")
            self.assertIsNotNone(result.best)
            self.assertEqual(result.best.artifact["x"], 10)

    def test_trace_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = TraceRecorder(Path(tmp) / "trace.jsonl")
            trace.record(kind="action", message="edit", tool="edit")
            trace.record(
                kind="feedback",
                message="score improved",
                feedback_valid=True,
                feedback_informative=True,
                feedback_retained=True,
            )
            trace.record(kind="action", message="verify", tool="verify")
            efc = estimate_effective_feedback_compute(trace.events)
            process = evaluate_process_quality(trace.events)
            self.assertEqual(efc.feedback_events, 1)
            self.assertEqual(efc.effective_feedback_ratio, 1.0)
            self.assertGreaterEqual(process.score, 0.7)
            self.assertEqual(process.stage_counts["verification"], 1)

    def test_harness_registry_mutation_and_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = HarnessRegistry(Path(tmp))
            spec = HarnessSpec.default("toy")
            registry.register(spec)
            mutated = mutate_policy(spec, "feedback_policy", "efc_gate", True, new_version="0.1.1")
            registry.register(mutated, status="candidate")
            loaded = registry.load(mutated.name, "0.1.1")
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded["feedback_policy"]["efc_gate"])

            evidence = HarnessPromotionEvidence(improved_tasks=["toy"], replay_passed=True, process_quality_delta=0.1)
            decision = evaluate_promotion(mutated, evidence)
            self.assertTrue(decision.promote)

    def test_verified_memory_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = VerifiedMemoryStore(Path(tmp))
            store.add(
                task_family="toy",
                summary="Increasing x toward target improved score.",
                evidence={"replay": True},
                tags=["toy", "numeric"],
                verified=True,
            )
            records = list(store.query("toy"))
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].verified)

    def test_candidate_archive_cells_and_duplicates(self):
        task = ToyNumericBenchmark(target=10).load_task("toy")
        c1 = Candidate.from_draft(task, CandidateDraft(artifact={"x": 1}, operator_id="step"))
        c1.score = ToyNumericBenchmark(target=10).evaluate(task, c1).score
        c2 = Candidate.from_draft(task, CandidateDraft(artifact={"x": 8}, operator_id="step"))
        c2.score = ToyNumericBenchmark(target=10).evaluate(task, c2).score
        c3 = Candidate.from_draft(task, CandidateDraft(artifact={"x": 8}, operator_id="step"))
        c3.score = ToyNumericBenchmark(target=10).evaluate(task, c3).score

        archive = CandidateArchive(maximize=True)
        self.assertTrue(archive.add(c1))
        self.assertTrue(archive.add(c2))
        self.assertFalse(archive.add(c3))
        self.assertEqual(len(archive), 2)
        self.assertEqual(archive.best().artifact["x"], 8)
        self.assertEqual(len(archive.diverse_parents(limit=1)), 1)

    def test_file_operators(self):
        task = Task(id="files", family="local", objective="", initial_artifact={"files": {"a.py": "x = 1\n"}})
        parent = Candidate.from_draft(task, CandidateDraft(artifact=task.initial_artifact))
        replace = FileStringReplaceOperator("a.py", [("1", "2")])
        append = FileAppendOperator("a.py", ["print(x)\n"])
        replace_draft = replace.propose(task, parent, __import__("random").Random(0))[0]
        append_draft = append.propose(task, parent, __import__("random").Random(0))[0]
        self.assertEqual(replace_draft.artifact["files"]["a.py"], "x = 2\n")
        self.assertTrue(append_draft.artifact["files"]["a.py"].endswith("print(x)\n"))

    def test_regex_number_jitter_operator(self):
        task = Task(id="code", family="local", objective="", initial_artifact={"code": "cout << 15000 << 25000;\n"})
        parent = Candidate.from_draft(task, CandidateDraft(artifact=task.initial_artifact))
        op = RegexNumberJitterOperator(samples=2, changes_per_sample=1, jitter=10, min_abs_value=1000)
        drafts = op.propose(task, parent, __import__("random").Random(0))
        self.assertEqual(len(drafts), 2)
        self.assertNotEqual(drafts[0].artifact["code"], task.initial_artifact["code"])

    def test_regex_float_jitter_operator(self):
        task = Task(id="code", family="local", objective="", initial_artifact={"code": "x = 5.2; y = 1e-3;\n"})
        parent = Candidate.from_draft(task, CandidateDraft(artifact=task.initial_artifact))
        op = RegexFloatJitterOperator(samples=2, changes_per_sample=1, relative_jitter=0.1, min_abs_value=1e-4)
        drafts = op.propose(task, parent, __import__("random").Random(0))
        self.assertEqual(len(drafts), 2)
        self.assertNotEqual(drafts[0].artifact["code"], task.initial_artifact["code"])

    def test_harness_ablation_runner(self):
        spec = HarnessSpec.default("toy")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def run_fn(harness):
                task = ToyNumericBenchmark(target=1).load_task("toy")
                controller = GreedySearchController(
                    adapter=ToyNumericBenchmark(target=1),
                    operators=OperatorLibrary([JsonFieldStepOperator("x", [1])]),
                    store=FileArtifactStore(root / harness.name / "runs"),
                    config=SearchConfig(max_iterations=1, max_evaluations=5),
                )
                return controller.run(task, run_id=harness.name).summary

            results = HarnessAblationRunner([spec], run_fn).run()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].summary.best_score.objective, 0.0)
            json_path = write_ablation_json(results, root / "report.json")
            md_path = write_ablation_markdown(results, root / "report.md")
            self.assertTrue(json_path.exists())
            self.assertIn("Harness Ablation Report", md_path.read_text(encoding="utf-8"))

    def test_local_command_benchmark_adapter(self):
        task = Task(
            id="cmd",
            family="local_command",
            objective="Read solution.json and write score.json.",
            initial_artifact={"files": {"solution.json": '{"x": 3}'}},
            metadata={
                "eval_command": ["python3", "evaluate.py"],
                "score_file": "score.json",
                "static_files": {
                    "evaluate.py": (
                        "import json\n"
                        "x = json.load(open('solution.json'))['x']\n"
                        "json.dump({'objective': -abs(x-5), 'metrics': {'x': x}}, open('score.json', 'w'))\n"
                    )
                },
            },
        )
        adapter = LocalCommandBenchmarkAdapter({"cmd": task})
        candidate = Candidate.from_draft(task, CandidateDraft(artifact={"files": {"solution.json": '{"x": 5}'}}))
        result = adapter.evaluate(task, candidate)
        self.assertIsNone(result.error)
        self.assertEqual(result.score.objective, 0.0)

    def test_config_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_path = root / "task.json"
            cand_path = root / "candidate.json"
            task_path.write_text(
                '{"id": "t", "objective": "demo", "initial_artifact": {"files": {}}, "budget": {"max_iterations": 3}}',
                encoding="utf-8",
            )
            cand_path.write_text('{"artifact": {"files": {"a.txt": "hello"}}, "operator_id": "manual"}', encoding="utf-8")
            task = load_task_config(task_path)
            draft = load_candidate_draft(cand_path)
            self.assertEqual(task.id, "t")
            self.assertEqual(task.budget.max_iterations, 3)
            self.assertEqual(draft.artifact["files"]["a.txt"], "hello")

    def test_azure_openai_client_payload_and_text_extraction(self):
        config = AzureOpenAIConfig(
            base_url="https://example.openai.azure.com/openai/v1",
            model="gpt-5.5",
            api_version="preview",
        )
        client = AzureOpenAIResponsesClient(config=config, token="Bearer local-token")
        payload = client.build_response_payload(
            prompt="hello",
            system="system",
            max_output_tokens=7,
            temperature=0.2,
        )
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["input"], "hello")
        self.assertEqual(payload["instructions"], "system")
        self.assertEqual(payload["max_output_tokens"], 7)
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(client.responses_url(), "https://example.openai.azure.com/openai/v1/responses?api-version=preview")
        self.assertEqual(client.token(), "local-token")
        response = {"output": [{"content": [{"text": "OPEN_"}, {"text": "EVOLVE_OK"}]}]}
        self.assertEqual(client.extract_text(response), "OPEN_EVOLVE_OK")

    def test_llm_code_edit_response_parsing(self):
        plan, code = AzureCodeEditOperator._parse_response(
            '```json\n{"plan": "try faster loop", "code": "int main(){return 0;}"}\n```'
        )
        self.assertEqual(plan, "try faster loop")
        self.assertEqual(code, "int main(){return 0;}")

        plan, code = AzureCodeEditOperator._parse_response("```cpp\nint main(){return 1;}\n```")
        self.assertIn("fenced", plan)
        self.assertEqual(code, "int main(){return 1;}")

    def test_prefixed_json_extraction(self):
        parsed = extract_prefixed_json('noise\nOPEN_EVOLVE_X {"a": 1}\n', "OPEN_EVOLVE_X ")
        self.assertEqual(parsed, {"a": 1})


if __name__ == "__main__":
    unittest.main()
