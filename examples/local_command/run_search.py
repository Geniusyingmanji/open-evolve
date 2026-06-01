from pathlib import Path

from open_evolve.benchmarks.config_loader import load_task_config
from open_evolve.benchmarks.local_command import LocalCommandBenchmarkAdapter
from open_evolve.core.artifact_store import FileArtifactStore
from open_evolve.core.operators import FileStringReplaceOperator, OperatorLibrary
from open_evolve.core.search_controller import GreedySearchController, SearchConfig
from open_evolve.core.trace_recorder import TraceRecorder
from open_evolve.core.types import json_dumps


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    task = load_task_config(root / "examples" / "local_command" / "task.json")
    workspace = root / ".open_evolve" / "local_command_search"
    controller = GreedySearchController(
        adapter=LocalCommandBenchmarkAdapter({task.id: task}),
        operators=OperatorLibrary(
            [
                FileStringReplaceOperator("solution.json", [("0", "2"), ("0", "5"), ("2", "5")]),
            ]
        ),
        store=FileArtifactStore(workspace / "runs"),
        config=SearchConfig(max_iterations=3, max_evaluations=20, seed=0),
        trace=TraceRecorder(workspace / "traces" / "search_trace.jsonl"),
    )
    result = controller.run(task, run_id="local_command_search")
    print(json_dumps({"best_artifact": result.best.artifact, "summary": result.summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
