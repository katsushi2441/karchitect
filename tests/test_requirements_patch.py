from app.engine import apply_requirements_patch
from app.models import (
    ArchitectureChoice,
    ArchitecturePatch,
    DataEntity,
    Requirements,
    RequirementsPatch,
)


def test_patch_preserves_unchanged_sections():
    previous = Requirements(
        project_name="既存",
        purpose="既存の目的",
        data_entities=[DataEntity(name="顧客")],
        revision=3,
    )

    updated = apply_requirements_patch(previous, RequirementsPatch(summary="新しい概要"))

    assert updated.summary == "新しい概要"
    assert updated.project_name == "既存"
    assert updated.purpose == "既存の目的"
    assert updated.data_entities[0].name == "顧客"
    assert updated.revision == 4


def test_empty_patch_cannot_erase_existing_content():
    previous = Requirements(purpose="残す", target_users=["担当者"])

    updated = apply_requirements_patch(
        previous,
        RequirementsPatch(purpose="", target_users=[]),
    )

    assert updated.purpose == "残す"
    assert updated.target_users == ["担当者"]


def test_architecture_patch_changes_only_named_field():
    previous = Requirements(
        architecture=ArchitectureChoice(backend="FastAPI", database="SQLite")
    )

    updated = apply_requirements_patch(
        previous,
        RequirementsPatch(architecture=ArchitecturePatch(database="PostgreSQL")),
    )

    assert updated.architecture.backend == "FastAPI"
    assert updated.architecture.database == "PostgreSQL"


def test_raw_notes_are_appended_once():
    previous = Requirements(raw_notes=["既存"])
    patch = RequirementsPatch(raw_notes_append=["既存", " 新規 "])

    updated = apply_requirements_patch(previous, patch)

    assert updated.raw_notes == ["既存", "新規"]
