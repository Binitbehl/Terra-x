# TERRA-X
A spatiotemporal intelligence platform for Earth systems research.

**Research question:** Can we integrate different sources of Earth observation
data to understand and predict environmental changes?

## Status
Phase 1: learning foundations and setting up the pipeline.

## Setup
python -m venv .venv
(activate it)
pip install -r requirements.txt

## Structure
- data/      raw and processed data (not tracked by git)
- src/       ingestion, processing, features, models, evaluation
- notebooks/ exploration
- sql/       database schemas and queries
- reports/   write-ups and figures