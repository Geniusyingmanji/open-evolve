# Frontier SOTA Lookup

Date: 2026-06-03

## Sources

- Local Frontier-Engineering clone: `/data/zyf/benchmarks/Frontier-Engineering`, commit `9cad9fe`.
- Main branch README links to the public leaderboard, but does not include numeric leaderboard YAML/JSON files.
- `baseline_archive/` contains published best code artifacts by experiment / algorithm / model / task; it does not contain per-task numeric SOTA tables.
- Public leaderboard data is available from the site linked in the README:
  - `https://lab.einsia.ai/frontier-eng/data/tasks_index.yaml`
  - `https://lab.einsia.ai/frontier-eng/data/overall-model.yaml`
  - `https://lab.einsia.ai/frontier-eng/data/overall-framework.yaml`
  - `https://lab.einsia.ai/frontier-eng/data/problems/<TaskName>.yaml`

The per-task `data/problems/*.yaml` files are the most direct SOTA source:
`statistics.raw_score.baseline`, `statistics.raw_score.max`, and participant
rows with `raw_score` / `normalized_score` / `experiment_type`.

## Comparison With Local Open-Evolve Results

Higher raw score is better for the tasks below, including structural tasks where
scores are negative.

| Task | Official raw SOTA | Top participant | Official baseline | Local best | Status |
|---|---:|---|---:|---:|---|
| WirelessChannelSimulation/HighReliableSimulation | 544.7187 | GPT-OSS + ABMCTS | 192.5193 | 897.0560316 | Above SOTA by +64.68% |
| EnergyStorage/BatteryFastChargingProfile | 121.991365 | GPT-5.4 | 71.2806 | 119.3422613 | Below SOTA by 2.6491 raw |
| EnergyStorage/BatteryFastChargingSPMe | 122.9430436 | GPT-5.4 | 66.1636 | 80.88928455 | Below SOTA by 42.0538 raw |
| Robotics/PIDTuning | 0.1639 | Claude Opus 4.6 + ShinkaiEvolve | 0.0366 | 0.1211966216 | Below SOTA by 0.0427 raw |
| Robotics/DynamicObstacleAvoidanceNavigation | 0.0862 | GPT-OSS + ABMCTS | 0.0722 | 0.07317073171 | Below SOTA by 0.0130 raw |
| Robotics/UAVInspectionCoverageWithWind | 55.9109 | Grok 4.20 | 28.8519 | 31.16662479 | Below SOTA by 24.7443 raw |
| StructuralOptimization/ISCSO2015 | -968.4567 | Claude Opus 4.6 | -5401.589 | -5144.478595 | Above baseline, far below SOTA |
| StructuralOptimization/ISCSO2023 | -16477799.48 | Claude Opus 4.6 | -77813242.9 | -77813242.9 | Baseline-level, below SOTA |
| StructuralOptimization/TopologyOptimization | -183.0907 | GPT-OSS + OpenEvolve | -195.9153 | -195.9092812 | Slightly above baseline, below SOTA |

## Interpretation

- Most current local Frontier gains are against shipped baselines, not official SOTA.
- The clear exception is `WirelessChannelSimulation/HighReliableSimulation`, where
  local GPT-5.5/OpenEvolve runs beat the public raw SOTA record.
- Some locally discovered/runnable tasks, such as `ParticlePhysics/MuonTomography`,
  `PyMOTOSIMPCompliance`, `DawnAircraftDesignOptimization`, `DiffSimThermalControl`,
  `DuckDBWorkloadOptimization`, and `EV2GymSmartCharging`, are not present in the
  public 47-task leaderboard data pulled above, so they should be reported only as
  baseline improvements unless a separate public SOTA source is found.
