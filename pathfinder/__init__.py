"""Pathfinder — walk the path from a data change to everything it touches.

Pathfinder is a pull-request agent for data teams. On any PR that changes a
data model, it reads DataHub's cross-stack lineage graph (tables -> dashboards
-> ML features -> ML models -> deployments), decides whether the change is
breaking, tells you exactly what breaks and who owns it, drafts a
backward-compatible fix, and writes the assessment back into the catalog so the
next person (or agent) inherits the knowledge.
"""

__version__ = "0.1.0"
