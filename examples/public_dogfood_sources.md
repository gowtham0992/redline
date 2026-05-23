# Public Dogfood Fixture Sources

The `public_dogfood_baseline.jsonl` and `public_dogfood_candidate.jsonl`
fixtures are synthetic. They do not copy rows verbatim from public datasets,
private customer logs, or user conversations.

They are shaped after common public AI-log and instruction-tuning patterns:

- Databricks Dolly 15k: instruction-following rows with direct answers
  (`https://huggingface.co/datasets/databricks/databricks-dolly-15k`).
- OpenAssistant OASST1: assistant-style multi-domain task requests
  (`https://huggingface.co/datasets/OpenAssistant/oasst1`).
- Anthropic HH-RLHF: paired response comparison patterns
  (`https://huggingface.co/datasets/Anthropic/hh-rlhf`).
- WildChat: broad real-world chat task variety
  (`https://wildchat.allen.ai/`).

The fixture exists to make release dogfooding obvious and safe: the baseline
keeps required structure, entities, dates, URLs, and numbers; the candidate
intentionally drops them. A new user can run the commands in `README.md` or
`docs/dogfood.md` and see redline catch regressions without needing private
logs or external API keys.
