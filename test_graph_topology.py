r"""
Offline LangGraph workflow topology tests for src/review_graph.py.

Verifies the five-node sequential DAG structure without invoking any node
functions or making any Gemini / GitHub API calls.

Run:
    .venv\Scripts\python.exe test_graph_topology.py
"""
import os
import sys

# ---------------------------------------------------------------------------
# Provide sentinel values so Config does not raise on missing env vars.
# These strings are never sent to any external service.
# ---------------------------------------------------------------------------
os.environ.setdefault("GEMINI_API_KEY", "offline-test-sentinel")
os.environ.setdefault("GITHUB_TOKEN", "offline-test-sentinel")

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langgraph.graph import END, START
from langgraph.graph.state import CompiledStateGraph
from langchain_core.runnables.graph import Graph as DrawableGraph

from src.agent_state import AgentState
from src.review_graph import create_review_graph

# ---------------------------------------------------------------------------
# Constants -- ground-truth expected topology
# ---------------------------------------------------------------------------

# Internal LangGraph sentinel node IDs (set by the framework, not user code).
_START_ID: str = "__start__"
_END_ID: str = "__end__"

# The five application-defined workflow nodes, in declared order.
EXPECTED_NODE_IDS: list[str] = [
    "analyze_changes",
    "review_security",
    "review_error_handling",
    "review_code_quality",
    "generate_final_review",
]

# All expected directed edges as (source_id, target_id) pairs,
# including the START and END sentinel links.
EXPECTED_EDGES: list[tuple[str, str]] = [
    (_START_ID, "analyze_changes"),
    ("analyze_changes", "review_security"),
    ("review_security", "review_error_handling"),
    ("review_error_handling", "review_code_quality"),
    ("review_code_quality", "generate_final_review"),
    ("generate_final_review", _END_ID),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

failures: list[str] = []


def ok(description: str) -> None:
    print(f"  [OK  ] {description}")


def fail(description: str) -> None:
    print(f"  [FAIL] {description}")
    failures.append(description)


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

print("=" * 58)
print(" GRAPH TOPOLOGY TESTS (offline)")
print("=" * 58)

# ------------------------------------------------------------------
# Test 1: create_review_graph() returns the expected compiled type
# ------------------------------------------------------------------
print()
print("=== 1. Graph creation and type ===")

graph = create_review_graph()

if isinstance(graph, CompiledStateGraph):
    ok(f"create_review_graph() returned CompiledStateGraph")
else:
    fail(
        f"create_review_graph() returned {type(graph).__name__!r},"
        " expected CompiledStateGraph"
    )

# ------------------------------------------------------------------
# Test 2: g.nodes contains exactly the five application nodes
#         (CompiledStateGraph.nodes is the Pregel runtime dict;
#          it includes '__start__' added by the framework but NOT '__end__')
# ------------------------------------------------------------------
print()
print("=== 2. Compiled graph nodes (runtime dict) ===")

runtime_node_keys: set[str] = set(graph.nodes.keys())
runtime_app_nodes: set[str] = runtime_node_keys - {_START_ID}

if runtime_app_nodes == set(EXPECTED_NODE_IDS):
    ok(f"Exactly five application nodes present: {sorted(runtime_app_nodes)}")
else:
    missing = set(EXPECTED_NODE_IDS) - runtime_app_nodes
    extra = runtime_app_nodes - set(EXPECTED_NODE_IDS)
    if missing:
        fail(f"Missing application nodes: {sorted(missing)}")
    if extra:
        fail(f"Unexpected extra application nodes: {sorted(extra)}")

# Individual node presence assertions
for node_id in EXPECTED_NODE_IDS:
    if node_id in graph.nodes:
        ok(f"Node present: '{node_id}'")
    else:
        fail(f"Node missing: '{node_id}'")

# ------------------------------------------------------------------
# Test 3: get_graph() returns a DrawableGraph and contains all nodes
#         including the __start__ and __end__ sentinels
# ------------------------------------------------------------------
print()
print("=== 3. DrawableGraph (get_graph) node catalogue ===")

drawable: DrawableGraph = graph.get_graph()

if isinstance(drawable, DrawableGraph):
    ok("get_graph() returned langchain_core DrawableGraph")
else:
    fail(
        f"get_graph() returned {type(drawable).__name__!r},"
        " expected DrawableGraph"
    )

drawable_node_ids: set[str] = set(drawable.nodes.keys())

all_expected_ids: set[str] = set(EXPECTED_NODE_IDS) | {_START_ID, _END_ID}
if all_expected_ids.issubset(drawable_node_ids):
    ok(f"DrawableGraph contains all expected node IDs including sentinels")
else:
    missing_ids = all_expected_ids - drawable_node_ids
    fail(f"DrawableGraph missing node IDs: {sorted(missing_ids)}")

# ------------------------------------------------------------------
# Test 4: Edge topology -- every expected edge is present
# ------------------------------------------------------------------
print()
print("=== 4. Edge topology ===")

actual_edges: set[tuple[str, str]] = {
    (e.source, e.target) for e in drawable.edges
}

for src, tgt in EXPECTED_EDGES:
    if (src, tgt) in actual_edges:
        ok(f"Edge present: '{src}' -> '{tgt}'")
    else:
        fail(f"Edge MISSING: '{src}' -> '{tgt}'")

# No unexpected edges beyond the expected set
unexpected_edges = actual_edges - set(EXPECTED_EDGES)
if not unexpected_edges:
    ok("No unexpected extra edges detected")
else:
    for src, tgt in sorted(unexpected_edges):
        fail(f"Unexpected edge found: '{src}' -> '{tgt}'")

# ------------------------------------------------------------------
# Test 5: No edges are marked conditional (all edges are deterministic)
# ------------------------------------------------------------------
print()
print("=== 5. All edges are unconditional (deterministic sequence) ===")

conditional_edges = [e for e in drawable.edges if e.conditional]
if not conditional_edges:
    ok("All edges are non-conditional (deterministic sequential workflow)")
else:
    for e in conditional_edges:
        fail(f"Unexpected conditional edge: '{e.source}' -> '{e.target}'")

# ------------------------------------------------------------------
# Test 6: Entry point -- START sentinel links to 'analyze_changes'
# ------------------------------------------------------------------
print()
print("=== 6. Entry point (START -> first node) ===")

start_targets = {e.target for e in drawable.edges if e.source == _START_ID}
if start_targets == {"analyze_changes"}:
    ok(f"START (__start__) links exclusively to 'analyze_changes'")
else:
    fail(
        f"START links to {sorted(start_targets)!r},"
        " expected {{'analyze_changes'}}"
    )

# ------------------------------------------------------------------
# Test 7: Exit point -- 'generate_final_review' links to END sentinel
# ------------------------------------------------------------------
print()
print("=== 7. Exit point (last node -> END) ===")

last_node_targets = {
    e.target for e in drawable.edges if e.source == "generate_final_review"
}
if last_node_targets == {_END_ID}:
    ok(f"'generate_final_review' links exclusively to END (__end__)")
else:
    fail(
        f"'generate_final_review' links to {sorted(last_node_targets)!r},"
        f" expected {{'{_END_ID}'}}"
    )

# ------------------------------------------------------------------
# Test 8: No node has more than one outgoing edge (strictly linear chain)
# ------------------------------------------------------------------
print()
print("=== 8. Linear chain -- no node fans out to multiple targets ===")

from collections import defaultdict

out_degree: dict[str, set[str]] = defaultdict(set)
for e in drawable.edges:
    out_degree[e.source].add(e.target)

all_linear = True
for node_id, targets in out_degree.items():
    if len(targets) > 1:
        fail(
            f"Node '{node_id}' has {len(targets)} outgoing edges"
            f" (targets: {sorted(targets)}) -- expected exactly 1"
        )
        all_linear = False

if all_linear:
    ok("Every node has exactly one outgoing edge (strictly linear chain)")

# ------------------------------------------------------------------
# Test 9: AgentState TypedDict has all required keys
# ------------------------------------------------------------------
print()
print("=== 9. AgentState TypedDict keys ===")

required_state_keys: set[str] = {
    "diff",
    "context",
    "change_analysis",
    "security_review",
    "error_handling_review",
    "quality_review",
    "final_review",
}

actual_state_keys: set[str] = set(AgentState.__annotations__.keys())

if actual_state_keys == required_state_keys:
    ok(f"AgentState has exactly the expected keys: {sorted(actual_state_keys)}")
else:
    missing_keys = required_state_keys - actual_state_keys
    extra_keys = actual_state_keys - required_state_keys
    if missing_keys:
        fail(f"AgentState missing keys: {sorted(missing_keys)}")
    if extra_keys:
        fail(f"AgentState has unexpected extra keys: {sorted(extra_keys)}")

# ------------------------------------------------------------------
# Test 10: Validate graph accepts a well-formed initial state dict
#          using the compiled graph's input schema -- no invocation.
# ------------------------------------------------------------------
print()
print("=== 10. Compiled graph input schema accepts AgentState structure ===")

try:
    schema = graph.get_input_schema()
    top_fields = set(schema.model_fields.keys())

    # LangGraph (>=0.2) wraps AgentState inside a LangGraphInput model whose
    # sole top-level field is 'root: AgentState'.  Unwrap one level so we can
    # verify that the AgentState field names are present.
    if top_fields == {"root"}:
        inner_type = schema.model_fields["root"].annotation
        # inner_type is the AgentState TypedDict; read its annotations.
        inner_fields = set(getattr(inner_type, "__annotations__", {}).keys())
        if "diff" in inner_fields:
            ok(
                f"Input schema wraps AgentState under 'root'; "
                f"inner fields: {sorted(inner_fields)}"
            )
        else:
            fail(
                f"AgentState wrapper found but 'diff' missing; "
                f"inner fields: {sorted(inner_fields)}"
            )
    elif "diff" in top_fields:
        # Flat schema -- 'diff' is directly at the top level.
        ok(f"Input schema contains 'diff' field directly (fields: {sorted(top_fields)})")
    else:
        fail(
            f"Input schema has unexpected structure; "
            f"top-level fields: {sorted(top_fields)}"
        )
except Exception as exc:
    fail(f"get_input_schema() raised {type(exc).__name__}: {exc}")

# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

print()
if failures:
    print("=" * 58)
    print(f"FAILED -- {len(failures)} assertion(s) failed:")
    for i, msg in enumerate(failures, 1):
        print(f"  {i}. {msg}")
    print("=" * 58)
    sys.exit(1)
else:
    total = (
        1   # type check
        + 1 + len(EXPECTED_NODE_IDS)  # runtime node checks
        + 2                           # drawable type + sentinel coverage
        + len(EXPECTED_EDGES) + 1     # edges + no-extra
        + 1                           # all unconditional
        + 1                           # entry point
        + 1                           # exit point
        + 1                           # linear chain
        + 1                           # AgentState keys
        + 1                           # input schema
    )
    print("=" * 58)
    print(f"All {total} topology assertions passed.")
    print("=" * 58)
    sys.exit(0)
