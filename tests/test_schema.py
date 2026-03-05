"""Tests for the dcat_p_lab schema and generated Python datamodel.

This module covers:
- Schema file presence
- Key class definitions in the schema (via SchemaView)
- Python datamodel import and basic instantiation
- Enum membership
"""

import importlib
from pathlib import Path

import pytest

# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = REPO_ROOT / "src" / "dcat_p_lab" / "schema" / "dcat_p_lab.yaml"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _schema_view():
    """Load and return a SchemaView for the main schema.

    Raises ``pytest.skip`` if the remote parent schema cannot be fetched so
    that offline runs do not fail for network-related reasons.
    """
    from linkml_runtime.utils.schemaview import SchemaView  # noqa: PLC0415

    try:
        sv = SchemaView(str(SCHEMA_PATH))
        # Force loading of imports to detect network failures early.
        _ = sv.all_classes()
        return sv
    except Exception as exc:  # noqa: BLE001
        if "urlopen" in str(exc).lower() or "httperror" in str(exc).lower() or "connection" in str(exc).lower():
            pytest.skip(f"Remote schema import unavailable: {exc}")
        raise


# ── Schema file tests ─────────────────────────────────────────────────────────

class TestSchemaFileExists:
    """The main schema YAML file must exist on disk."""

    def test_schema_yaml_exists(self):
        assert SCHEMA_PATH.exists(), f"Schema not found at {SCHEMA_PATH}"

    def test_schema_is_yaml(self):
        assert SCHEMA_PATH.suffix == ".yaml"

    def test_schema_nonempty(self):
        assert SCHEMA_PATH.stat().st_size > 0


# ── SchemaView tests ─────────────────────────────────────────────────────────

class TestSchemaStructure:
    """Key structural properties of the schema as seen by SchemaView."""

    def test_schema_name(self):
        sv = _schema_view()
        assert sv.schema.name == "dcat-p-lab"

    def test_lab_synthesis_activity_defined(self):
        sv = _schema_view()
        assert "LabSynthesisActivity" in sv.all_classes()

    def test_lab_synthesis_step_is_abstract(self):
        sv = _schema_view()
        cls = sv.get_class("LabSynthesisStep")
        assert cls is not None
        assert cls.abstract is True

    def test_all_concrete_step_classes_present(self):
        sv = _schema_view()
        expected = [
            "SolutionPreparationStep",
            "MaterialAdditionStep",
            "StirringStep",
            "TemperatureChangeStep",
            "AtmosphereSettingStep",
            "WaitingStep",
            "SeparationStep",
            "WashingStep",
            "GrindingStep",
            "RepetitionBlock",
        ]
        all_classes = sv.all_classes()
        missing = [c for c in expected if c not in all_classes]
        assert not missing, f"Missing classes in schema: {missing}"

    def test_quantitative_attribute_subclasses(self):
        sv = _schema_view()
        quant_classes = ["Duration", "StirringSpeed", "FlowRate", "HeatRamp"]
        all_classes = sv.all_classes()
        missing = [c for c in quant_classes if c not in all_classes]
        assert not missing, f"Missing QuantitativeAttribute subclasses: {missing}"

    def test_intermediate_solution_defined(self):
        sv = _schema_view()
        assert "IntermediateSolution" in sv.all_classes()

    def test_laboratory_defined(self):
        sv = _schema_view()
        assert "Laboratory" in sv.all_classes()

    def test_enums_present(self):
        sv = _schema_view()
        all_enums = sv.all_enums()
        required_enums = [
            "SeparationMethodEnum",
            "AtmosphereTypeEnum",
            "TemperatureTargetTypeEnum",
        ]
        missing = [e for e in required_enums if e not in all_enums]
        assert not missing, f"Missing enums: {missing}"

    def test_separation_method_enum_values(self):
        sv = _schema_view()
        enum = sv.get_enum("SeparationMethodEnum")
        assert enum is not None
        values = list(enum.permissible_values.keys())
        assert "filtration" in values
        assert "centrifugation" in values
        assert "evaporation" in values

    def test_atmosphere_type_enum_values(self):
        sv = _schema_view()
        enum = sv.get_enum("AtmosphereTypeEnum")
        assert enum is not None
        values = list(enum.permissible_values.keys())
        assert "nitrogen" in values
        assert "argon" in values
        assert "vacuum" in values

    def test_temperature_target_enum_values(self):
        sv = _schema_view()
        enum = sv.get_enum("TemperatureTargetTypeEnum")
        assert enum is not None
        values = list(enum.permissible_values.keys())
        assert "COOL" in values
        assert "HEAT" in values
        assert "REFLUX" in values
        assert "ROOM_TEMPERATURE" in values


# ── Python datamodel import tests ─────────────────────────────────────────────

class TestDatamodelImport:
    """The generated Python datamodel must be importable and functional."""

    def test_module_importable(self):
        mod = importlib.import_module("dcat_p_lab.datamodel.dcat_p_lab")
        assert mod is not None

    def test_lab_synthesis_activity_importable(self):
        from dcat_p_lab.datamodel.dcat_p_lab import LabSynthesisActivity  # noqa: PLC0415
        assert LabSynthesisActivity is not None

    def test_step_classes_importable(self):
        from dcat_p_lab.datamodel import dcat_p_lab as dm  # noqa: PLC0415
        for cls_name in [
            "LabSynthesisStep",
            "SolutionPreparationStep",
            "MaterialAdditionStep",
            "StirringStep",
            "TemperatureChangeStep",
            "AtmosphereSettingStep",
            "WaitingStep",
            "SeparationStep",
            "WashingStep",
            "GrindingStep",
            "RepetitionBlock",
        ]:
            cls = getattr(dm, cls_name, None)
            assert cls is not None, f"Class {cls_name} not found in datamodel"

    def test_quantitative_classes_importable(self):
        from dcat_p_lab.datamodel import dcat_p_lab as dm  # noqa: PLC0415
        for cls_name in ["Duration", "StirringSpeed", "FlowRate", "HeatRamp"]:
            cls = getattr(dm, cls_name, None)
            assert cls is not None, f"Class {cls_name} not found in datamodel"

    def test_enum_classes_importable(self):
        from dcat_p_lab.datamodel import dcat_p_lab as dm  # noqa: PLC0415
        for enum_name in [
            "SeparationMethodEnum",
            "AtmosphereTypeEnum",
            "TemperatureTargetTypeEnum",
        ]:
            enum_cls = getattr(dm, enum_name, None)
            assert enum_cls is not None, f"Enum {enum_name} not found in datamodel"


# ── Object instantiation tests ────────────────────────────────────────────────

class TestInstantiation:
    """Verify that key objects can be created programmatically."""

    def test_waiting_step_minimal(self):
        from dcat_p_lab.datamodel.dcat_p_lab import WaitingStep  # noqa: PLC0415
        step = WaitingStep(id="https://example.org/step/wait-001")
        assert str(step.id) == "https://example.org/step/wait-001"

    def test_stirring_step_minimal(self):
        from dcat_p_lab.datamodel.dcat_p_lab import StirringStep  # noqa: PLC0415
        step = StirringStep(id="https://example.org/step/stir-001")
        assert step is not None

    def test_material_addition_step_minimal(self):
        from dcat_p_lab.datamodel.dcat_p_lab import MaterialAdditionStep  # noqa: PLC0415
        step = MaterialAdditionStep(id="https://example.org/step/add-001")
        assert step is not None

    def test_temperature_change_step_minimal(self):
        from dcat_p_lab.datamodel.dcat_p_lab import TemperatureChangeStep  # noqa: PLC0415
        step = TemperatureChangeStep(id="https://example.org/step/temp-001")
        assert step is not None

    def test_repetition_block_with_count(self):
        from dcat_p_lab.datamodel.dcat_p_lab import RepetitionBlock  # noqa: PLC0415
        block = RepetitionBlock(
            id="https://example.org/block/repeat-001",
            repetition_count=4,
        )
        assert block.repetition_count == 4

    def test_lab_synthesis_activity_minimal(self):
        from dcat_p_lab.datamodel.dcat_p_lab import LabSynthesisActivity  # noqa: PLC0415
        activity = LabSynthesisActivity(id="https://example.org/activity/act-001")
        assert str(activity.id) == "https://example.org/activity/act-001"

    def test_lab_synthesis_activity_with_title(self):
        from dcat_p_lab.datamodel.dcat_p_lab import LabSynthesisActivity  # noqa: PLC0415
        activity = LabSynthesisActivity(
            id="https://example.org/activity/act-002",
            title="Test synthesis",
        )
        # title is multivalued in the parent schema; the datamodel stores it as a list.
        title_value = activity.title
        if isinstance(title_value, list):
            assert "Test synthesis" in title_value
        else:
            assert title_value == "Test synthesis"

    def test_duration_object(self):
        from dcat_p_lab.datamodel.dcat_p_lab import Duration  # noqa: PLC0415
        dur = Duration(
            value=30.0,
            has_quantity_type="http://qudt.org/vocab/quantitykind/Time",
            unit="https://qudt.org/vocab/unit/MIN",
        )
        assert dur.value == 30.0
        assert "qudt.org" in str(dur.unit)

    def test_waiting_step_with_duration(self):
        from dcat_p_lab.datamodel.dcat_p_lab import Duration, WaitingStep  # noqa: PLC0415
        dur = Duration(
            value=8.0,
            has_quantity_type="http://qudt.org/vocab/quantitykind/Time",
            unit="https://qudt.org/vocab/unit/HR",
        )
        step = WaitingStep(
            id="https://example.org/step/wait-dur-001",
            has_step_duration=[dur],
        )
        assert len(step.has_step_duration) == 1
        assert step.has_step_duration[0].value == 8.0


# ── Example file tests ───────────────────────────────────────────────────────

class TestExampleFiles:
    """Check that the pre-generated sequence examples exist and are non-empty."""

    EXAMPLES_DIR = REPO_ROOT / "examples" / "sequences"

    def test_examples_directory_exists(self):
        assert self.EXAMPLES_DIR.exists()

    def test_at_least_one_sequence_example(self):
        yamls = list(self.EXAMPLES_DIR.glob("seq_*.yaml"))
        assert len(yamls) > 0, "No seq_*.yaml files found in examples/sequences/"

    def test_sequence_example_seq_0001_exists(self):
        seq_file = self.EXAMPLES_DIR / "seq_0001.yaml"
        assert seq_file.exists()
        assert seq_file.stat().st_size > 0

    def test_all_examples_are_nonempty(self):
        yamls = list(self.EXAMPLES_DIR.glob("seq_*.yaml"))
        empty = [f for f in yamls if f.stat().st_size == 0]
        assert not empty, f"Empty example files found: {empty}"
