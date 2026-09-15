# Trade space

`pareto.py` compares recommendation-eligible candidates using higher supplied
synthetic success and lower complete population exposure. It uses no weights or
optimization dependency. `representatives.py` assigns the descriptive
`earliest_viable`, `highest_success`, and `lowest_exposure` categories without
choosing a final action.

Probability differences no greater than `1e-12` are equivalent. Exposure uses
`max(1e-9 people, 1e-12 * max(abs(a), abs(b)))`. Equivalent candidates remain
Pareto-efficient unless dominated by another candidate. Pairwise equivalent IDs
are retained as deterministic evidence rather than forcing a ranking.

