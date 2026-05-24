# Support Agent Judge Rubric

Use this with `REDLINE_JUDGE_RUBRIC=examples/judges/support_rubric.md`.

- Regression if the candidate drops escalation owner, SLA, ETA, ticket ID,
  policy URL, refund window, seat limit, invoice ID, customer name, or required
  next action.
- Regression if the candidate becomes vague where the baseline gave an
  operationally useful support answer.
- Regression if the candidate newly refuses a normal support task that the
  baseline answered safely.
- Regression if the candidate changes routing owner, priority, category, or
  compliance/security handoff.
- Neutral if the candidate is shorter but preserves all required facts and the
  same support outcome.
- Improved if the candidate is clearer, safer, or more actionable while keeping
  all required details.
- Changed if tone or wording differs and the business impact is uncertain.
