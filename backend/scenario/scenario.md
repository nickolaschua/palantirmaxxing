# Scenario assumptions

`synthetic_success.py` implements the externally assumed monotonic profile
`clip(p0 - alpha*t, minimum, maximum)`. `supplied_footprints.py` implements the
MVP fixed-radius circular footprint rule. Neither module predicts real
interceptor performance or physical consequences.

Both functions return stable domain records consumed by orchestration. A later
validated success or footprint provider can replace these functions without
changing PEC or the trade-space algorithms.

