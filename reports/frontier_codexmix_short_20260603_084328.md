# Frontier Codex-Mixed Short Run

Date: 2026-06-03

Run workspace:
`.open_evolve/frontier_codexmix_short_20260603_084328`

Commit:
`a2ee3ce`

## Setup

- Operator: `codex-mixed`
- Search: archive
- Codex timeout: 120 seconds
- Jitter: 4 samples, 2 changes, `auto` source region
- Seeds:
  - BatteryProfile: prior local best `119.34226133140375`
  - PIDTuning: prior local best `0.12098462436940914`
  - HighReliableSimulation: prior local campaign best source

The Codex harness was hardened before this run so timeout returns no draft
instead of aborting the search. When Codex timed out, the run still evaluated
float-jitter candidates.

## Results

| Task | Evals | Previous local best | New best | Valid | Public SOTA |
|---|---:|---:|---:|---:|---:|
| EnergyStorage/BatteryFastChargingProfile | 8 | 119.3422613314 | 119.3422613314 | 1.0 | 121.9913650228 |
| Robotics/PIDTuning | 8 | 0.1209846244 | 0.1211966216 | 1.0 | 0.1639 |
| WirelessChannelSimulation/HighReliableSimulation | 6 | 799.1678623615 | 897.0560315580 | 1.0 | 544.7187 |

## Notes

- BatteryProfile did not improve; the current best appears locally saturated for
  small constant perturbations.
- PIDTuning improved slightly, from `0.1209846244` to `0.1211966216`
  (`+0.175%` over the prior local best), but remains below official SOTA.
- HighReliableSimulation improved strongly under local rerun/noise and jitter,
  reaching `897.0560316`, `+64.68%` over the public raw SOTA record.
