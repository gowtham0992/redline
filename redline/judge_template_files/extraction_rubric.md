# Extraction And Structured Output Judge Rubric

Use this with `REDLINE_JUDGE_RUBRIC=examples/judges/extraction_rubric.md`.

- Regression if JSON becomes invalid, a JSON object becomes prose, an array
  becomes a comma-separated string, or a Markdown table/list/code block is lost
  when the prompt required that structure.
- Regression if any required key, column, tag, owner, category, or action item is
  missing, renamed incompatibly, or moved into free text.
- Regression if extracted values are less specific than the baseline, such as
  losing invoice IDs, dates, numbers, URLs, names, currency, percentages, or
  exact labels.
- Regression if the candidate adds unsupported fields that change downstream
  interpretation.
- Neutral if formatting is equivalent and all machine-readable fields preserve
  the same meaning.
- Improved if the candidate fixes malformed baseline structure while preserving
  all values required by the prompt.
- Changed if the structure is valid but field naming or value normalization needs
  product-owner review.
