# Local Model Training

The local training and fine-tuning flow is intentionally treated as a trust
boundary.

## Provenance Contract

- `src/rag/training.py` writes `*.metadata.json` sidecars next to the exported
  `finetuning_data_*.jsonl` files.
- `src/rag/finetune.py` requires those provenance files by default through
  `TRAINING_REQUIRE_DATASET_PROVENANCE=true`.
- the sidecar records where the dataset came from, how many records it contains,
  and that operator review is expected before the data is used to produce a
  model artifact

If you import datasets from outside the normal training export flow, generate a
matching provenance sidecar first or the fine-tuning loader will reject the
dataset.

## Feedback Overrides

The training pipeline can override heuristic labels using:

- honeypot hit logs
- CAPTCHA success logs

Those overrides are now surfaced in the audit trail, including conflicts where
the same IP appears in both feedback sources. Treat those conflicts as review
items before promoting the resulting dataset or model.

## Trust Boundary

- log files, honeypot events, and CAPTCHA feedback are untrusted inputs
- generated JSONL exports are derived artifacts, not authoritative truth
- trained local model files should only be produced from reviewed datasets in a
  trusted `models/` directory

For production releases, keep provenance enforcement enabled and review both the
dataset sidecars and the audit/security-event export before fine-tuning.
