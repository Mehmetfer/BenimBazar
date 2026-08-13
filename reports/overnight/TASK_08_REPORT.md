TASK: 08 — Borsa Botu Paper Decision Engine
STATUS: VERIFIED (paper only) — LIVE not opened
FILES CHANGED:
- borsa_bot/analytics/paper_feedback.py
- borsa_bot/strategy/service.py (wire calibration/lessons/strategy retire)
- profit/ev.py, profit/modes.py, portfolio/ledger.py, engines/orchestrator.py
- borsa_bot/tests/test_paper_decision_engine.py
ROOT CAUSE: CalibrationMonitor/post_trade/strategy ranking largely dead; losing strategies not gated; confidence NO-TRADE weak.
FIX: PaperDecisionFeedback on exits; shared CalibrationMonitor; retire/size-cut losing strategies; min AI confidence NO-TRADE; drift→DEFENSIVE; profit protection on monitor_exits; LIVE remains blocked.
TESTS BEFORE: borsa 71
TESTS AFTER: borsa 88 passed
NEW TESTS: test_paper_decision_engine.py (calibration, retire, NO-TRADE, DD, stops, limits, feedback wiring, backtest smoke)
REGRESSION: borsa 88; changex 252 unaffected
KNOWN LIMITATIONS: LIVE adapter still NOT implemented/blocked; SimulatedProvider paper only.
COMMIT: fa30ca1 Wire paper decision feedback: calibration, lessons, strategy risk gates
