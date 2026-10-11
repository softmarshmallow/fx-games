from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from demo_game_collection.identities import current_versions


def _load_docs_checker() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts/check_docs.py"
    spec = importlib.util.spec_from_file_location("stage_gen_docs_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_repository_documentation_and_publication_contract() -> None:
    repository_root = Path(__file__).parents[2]
    result = _load_docs_checker().run_docs_check(repository_root)
    assert result.failures == ()
    assert result.markdown_count > 0
    assert result.text_count > 0
    # The soundtrack loop and the concept cover. Documentation media is not a
    # publication root, so nothing under docs/ is counted here.
    assert result.media_count == 2


def _minimal_repository(root: Path) -> None:
    """The files the docs gate reads unconditionally, all empty."""
    for relative in (
        ".env.example",
        "README.md",
        "docs/generated-media-publication.md",
        "godot/games/_shared/docs/game-package.md",
        "docs/spec/agent-prompts.md",
        "docs/site.md",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (root / "docs/generated-media-inventory.json").write_text(
        '{"schemaVersion": 1, "roots": [], "media": []}', encoding="utf-8"
    )


def test_character_library_documentation_rejects_missing_links(tmp_path: Path) -> None:
    _minimal_repository(tmp_path)
    character = tmp_path / "library/characters/example"
    character.mkdir(parents=True)
    (character / "sd_3d.glb").write_bytes(b"link target only")
    (character / "README.md").write_text(
        "[Model](sd_3d.glb)\n[Record](sd_3d.json)\n", encoding="utf-8"
    )

    result = _load_docs_checker().run_docs_check(tmp_path)

    assert [failure for failure in result.failures if failure.startswith("library/")] == [
        "library/characters/example/README.md: missing link sd_3d.json"
    ]


def test_retired_terms_are_read_in_site_strings_but_not_comments(tmp_path: Path) -> None:
    workflow = tmp_path / "src/stage_gen/workflows/example"
    workflow.mkdir(parents=True)
    (workflow / "page.mdx").write_text("A workflow.\n", encoding="utf-8")
    components = tmp_path / "web/site/components"
    components.mkdir(parents=True)
    (components / "Header.tsx").write_text(
        "// The port of the retired showcase's header.\n"
        "/* The showcase\n   had none. */\n"
        'export const link = "https://example.test/showcase/";\n'
        "export const Header = () => <h1>Showcase</h1>;\n",
        encoding="utf-8",
    )

    failures = _load_docs_checker().check_retired_terms(tmp_path)

    # A URL's "//" opens no comment, so the string it sits in is read too.
    assert failures == [
        "web/site/components/Header.tsx:4: retired term 'showcase'",
        "web/site/components/Header.tsx:5: retired term 'Showcase'",
    ]


def test_a_user_skill_names_nothing_in_this_repository(tmp_path: Path) -> None:
    skill = tmp_path / "skills/example"
    (skill / "agents").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: game-concept-studio\n---\n"
        "Draw with `grida-fx run workflows/concept-image.yaml`.\n"
        "Read `docs/models/providers.md`, then run `stage-gen-concept check`.\n"
        "Import stage_gen.media.\n",
        encoding="utf-8",
    )
    (skill / "agents/openai.yaml").write_text(
        'default_prompt: "Follow `.agents/skills/asset-pipeline/SKILL.md`"\n', encoding="utf-8"
    )

    failures = _load_docs_checker().check_user_skills(tmp_path)

    # The skill's own name and the folder it writes in the user's project are not repository names.
    assert failures == [
        "skills/example/SKILL.md:5: a user skill names this repository "
        "(`docs/models/providers.md`)",
        "skills/example/SKILL.md:5: a user skill names this repository (stage-gen)",
        "skills/example/SKILL.md:6: a user skill names this repository (stage_gen)",
        "skills/example/agents/openai.yaml:1: a user skill names this repository "
        "(`.agents/skills/asset-pipeline/SKILL.md`)",
    ]


def test_web_text_walk_reads_git_files_and_web_code_may_not_spawn(tmp_path: Path) -> None:
    """The web walk is git's list, so ignored build output is never scanned, and web code
    that can start a process fails the gate."""
    _minimal_repository(tmp_path)
    stale = "const gateway = 'https://ai-gateway.vercel.sh';\n"
    (tmp_path / ".gitignore").write_text(".next\n", encoding="utf-8")
    for relative in ("web/site/.next/server/page.js", "web/site/lib/contracts/stale.ts"):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(stale, encoding="utf-8")
    (tmp_path / "web/site/lib/launch.ts").write_text(
        'import { spawn } from "node:child_process";\n', encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    result = _load_docs_checker().run_docs_check(tmp_path)

    assert sorted(failure for failure in result.failures if failure.startswith("web")) == [
        "web/site/lib/contracts/stale.ts: legacy gateway URL",
        "web/site/lib/launch.ts: web code must not spawn a generation process",
    ]


def test_every_spec_names_a_true_checker(tmp_path: Path) -> None:
    """A spec says what checks it, and the checker must exist and name the spec back."""

    checker = _load_docs_checker()
    spec_dir = tmp_path / "docs/spec/game"
    spec_dir.mkdir(parents=True)
    tests_dir = tmp_path / "tests/contract"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_true.py").write_text('SPEC = "spec/game/true.md"\n', encoding="utf-8")
    (tests_dir / "test_silent.py").write_text("x = 1\n", encoding="utf-8")

    def spec(name: str, claim: str) -> None:
        (spec_dir / f"{name}.md").write_text(
            f"# {name}\n\n> **Checked by:** {claim}\n\nBody.\n", encoding="utf-8"
        )

    spec("true", "`tests/contract/test_true.py`.")
    spec("honest", "none.")
    spec("missing", "`tests/contract/test_absent.py`.")
    spec("borrowed", "`tests/contract/test_silent.py`.")
    spec("source", "`src/stage_gen/fs.py`.")
    (spec_dir / "silent.md").write_text("# silent\n\nNo line at all.\n", encoding="utf-8")

    failures = checker.check_spec_checkers(tmp_path)
    assert failures == [
        "docs/spec/game/borrowed.md: Checked by names `tests/contract/test_silent.py`, "
        "which never names the spec",
        "docs/spec/game/missing.md: Checked by names missing test `tests/contract/test_absent.py`",
        "docs/spec/game/silent.md: no `> **Checked by:**` line",
        "docs/spec/game/source.md: Checked by names a non-test `src/stage_gen/fs.py`",
    ]


def test_repository_storage_policy_uses_live_enforced_limits() -> None:
    repository_root = Path(__file__).parents[2]
    policy = (repository_root / "docs/repository-storage.md").read_text(encoding="utf-8")

    assert re.search(r"\bapproximately\s+\d+(?:\.\d+)?\s+MiB\b", policy) is None
    for limit in (
        "audio: 20 MiB",
        "image: 5 MiB",
        "model: 10 MiB",
        "video: 25 MiB",
        "combined: 125 MiB",
    ):
        assert limit in policy
    assert "uv run python scripts/check_docs.py" in policy
    assert (
        "tests/contract/test_packaged_resources.py::"
        "test_repository_media_obeys_git_size_and_location_policy"
    ) in policy


def _current(family: str) -> str:
    """The identity a document must name, at whatever version the code declares."""

    (version,) = current_versions()[family]
    return f"{family}-v{version}"


def test_character_profile_workflow_is_discoverable_and_version_accurate() -> None:
    repository_root = Path(__file__).parents[2]
    readme = (repository_root / "README.md").read_text(encoding="utf-8")
    architecture = (repository_root / "ARCHITECTURE.md").read_text(encoding="utf-8")
    library = (repository_root / "docs/character-library.md").read_text(encoding="utf-8")
    docs_index = (repository_root / "docs/README.md").read_text(encoding="utf-8")

    for required in (
        "demo-games character-profile validate",
        "demo-games character-profile digest",
        "godot/games/the_grain/inputs",
        "--package-root",
        _current("dialogue-scene-bundle"),
    ):
        assert required in readme or required in library or required in docs_index
    assert "At committed HEAD it is not a provider-backed" not in architecture
    assert "successful scrolling-preview run also writes manifest schema v2" not in readme
    assert "strict v2 lower_snake_case `dialogue-scene` recipe" not in docs_index


def test_image_repeat_contract_is_scoped() -> None:
    repository_root = Path(__file__).parents[2]
    image_repeat = (repository_root / "docs/image-repeat.md").read_text(encoding="utf-8")
    for required in (
        "one image in, one image proven to repeat on a declared axis out",
        "exactly three unmarked, pixel-identical copies",
        "Two-axis tileability is a non-goal",
    ):
        assert required in image_repeat


def test_terrain_atlas_documentation_matches_runtime_contract() -> None:
    repository_root = Path(__file__).parents[2]
    contract = (repository_root / "docs/spec/terrain-atlas.md").read_text(encoding="utf-8")
    normalized = " ".join(contract.split())

    for required in (
        "terrain-atlas-3x3-minimal-v1",
        "47 reachable 3x3-minimal",
        "all eight neighbors",
        "Dynamic engine tilemaps require `direct_pass`",
        "Collision comes from occupancy, not alpha",
    ):
        assert required in normalized


def test_game_contract_authorities_are_discoverable_and_match_the_live_models() -> None:
    """The retained design and executable game formats remain distinct and discoverable.

    Modelled on the character-profile discoverability test above, and extended with the checks
    that keep the prepared package-root schema from drifting from its live model and exact current
    identities.
    """

    repository_root = Path(__file__).parents[2]
    readme = (repository_root / "README.md").read_text(encoding="utf-8")
    master_doc = (repository_root / "godot/games/_shared/docs/game-contract.md").read_text(
        encoding="utf-8"
    )
    schema_doc = (
        repository_root / "godot/games/_shared/docs/formats/authored-contract-schema.md"
    ).read_text(encoding="utf-8")
    sequence_doc = (
        repository_root / "godot/games/_shared/docs/formats/dialogue-and-cutscene-sequences.md"
    ).read_text(encoding="utf-8")
    taxonomy_doc = (
        repository_root / "godot/games/_shared/docs/formats/view-and-style-taxonomy.md"
    ).read_text(encoding="utf-8")
    package_doc = (repository_root / "godot/games/_shared/docs/game-package.md").read_text(
        encoding="utf-8"
    )
    docs_index = (repository_root / "docs/README.md").read_text(encoding="utf-8")
    discoverable_docs = (readme, master_doc, schema_doc, sequence_doc, package_doc, docs_index)

    for required in (
        "demo-games package validate",
        "demo-games package digest",
        "python -m grida.fx plan pipeline/workflow.py:build",
        "godot/games/bellweather/inputs/default",
        "godot/games/iron_petal_unit/inputs",
        _current("game-contract"),
        _current("prepared-game-runtime"),
    ):
        assert any(required in document for document in discoverable_docs)

    for required in (
        "formats/authored-contract-schema.md",
        "formats/view-and-style-taxonomy.md",
        "formats/dialogue-and-cutscene-sequences.md",
        "Visible gameplay requires visual coverage",
        "player `hurt` motion coverage",
        "Sequence control is explicit",
    ):
        assert required in master_doc

    for required in (
        "semantic control-flow graph",
        "orthogonal presentation program",
        "A **cutscene**",
        "control leases",
        "The current prepared scenario and runtime shapes remain valid",
    ):
        assert required in sequence_doc

    # Proposed vocabulary must not advertise itself as an implemented public format.
    assert "proposed TO-BE for the vocabulary" in taxonomy_doc
    assert "`side_view_2d` remains the only accepted projection" in taxonomy_doc
    assert "The public asset SDK and new games do not require this authoring format" in taxonomy_doc

    from demo_game_tools.input_formats.game_contract import (
        PREPARED_GAME_CONTRACT_SCHEMA_VERSION,
        PreparedGameContract,
    )

    # Every current package-root field appears in the worked shape. A field added to the model
    # without appearing in the executable-schema authority fails here.
    for field in PreparedGameContract.model_fields:
        assert field in schema_doc
    assert f"schema_version = {PREPARED_GAME_CONTRACT_SCHEMA_VERSION}" in schema_doc
    assert f'kind = "game-contract-v{PREPARED_GAME_CONTRACT_SCHEMA_VERSION}"' in schema_doc
    assert "side_view_2d" in schema_doc
    assert "ui.toml" in schema_doc
    assert "maps/<map_id>.toml" in schema_doc
