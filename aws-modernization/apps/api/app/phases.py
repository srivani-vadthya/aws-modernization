PHASES = [
    {"id": "intake", "label": "Intake", "group": "reverse"},
    {"id": "discovery", "label": "Discovery", "group": "reverse"},
    {"id": "graph", "label": "Knowledge graph", "group": "reverse"},
    {"id": "scope", "label": "Scope", "group": "reverse"},
    {"id": "semantic-ir", "label": "Semantic IR", "group": "reverse"},
    {"id": "requirements", "label": "Requirements", "group": "forward"},
    {"id": "backlog", "label": "Backlog", "group": "forward"},
    {"id": "modernize", "label": "Technology", "group": "forward"},
    {"id": "tests", "label": "Tests", "group": "forward"},
    {"id": "failures", "label": "Failure analysis", "group": "forward"},
    {"id": "artifacts", "label": "Final artifacts", "group": "forward"},
]

PHASE_IDS = [p["id"] for p in PHASES]
