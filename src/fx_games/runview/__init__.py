"""FX Games' reading of FX run folders: one run, projected to its run view.

FX writes a run folder (``plan.json``, ``events.jsonl``, placed files). This package reads one,
never writing into it, for the examples store and the tools that check runs: :func:`project_run`
projects it to one run view (``fx-games-run-view-v1``). FX's own viewer draws runs. This
package imports neither the engine nor its SDK.
"""

from fx_games.runview.folder import (
    EVENTS_FILE,
    FX_GRAPH_KIND,
    PLAN_FILE,
    RunFolderError,
    find_file,
    is_fx_run,
    is_stand_in,
    placed_path,
    project_file,
    read_events,
    read_plan,
    setting,
    store_of,
)
from fx_games.runview.model import (
    RUN_VIEW_KIND,
    RUN_VIEW_SCHEMA_VERSION,
    AuthoredInput,
    CacheDisposition,
    NodeCard,
    NodeState,
    Port,
    PortRef,
    Resource,
    RetryOwner,
    RunState,
    RunView,
    RunViewArtifact,
    RunViewGap,
    RunViewNode,
)
from fx_games.runview.project import project_run, verify_run

__all__ = [
    "EVENTS_FILE",
    "FX_GRAPH_KIND",
    "PLAN_FILE",
    "RUN_VIEW_KIND",
    "RUN_VIEW_SCHEMA_VERSION",
    "AuthoredInput",
    "CacheDisposition",
    "NodeCard",
    "NodeState",
    "Port",
    "PortRef",
    "Resource",
    "RetryOwner",
    "RunFolderError",
    "RunState",
    "RunView",
    "RunViewArtifact",
    "RunViewGap",
    "RunViewNode",
    "find_file",
    "is_fx_run",
    "is_stand_in",
    "placed_path",
    "project_file",
    "project_run",
    "read_events",
    "read_plan",
    "setting",
    "store_of",
    "verify_run",
]
