#!/usr/bin/env python3
"""
parse_costa.py — Convert activation_sequences_costa.py → dcat_p_lab YAML instances.

Reads every synthesis sequence from `activation_sequences_costa.py` and writes
one YAML file per sequence into `examples/sequences/` (or a custom directory).
Each file is a `LabSynthesisActivity` instance conforming to `dcat_p_lab.yaml`.

Usage
-----
    python scripts/parse_costa.py [--output-dir examples/sequences] [--max-seqs N]

Cleaning / normalisation applied
---------------------------------
- Value strings (e.g. "65 °C", "8 h", "500 rpm") are split into (value, QUDT unit).
- Unicode minus U+2212 (−) is normalised to ASCII hyphen before parsing.
- Qualitative temperature strings ("Cool", "Heat", "room temperature") → TemperatureTargetTypeEnum.
- atmosphere=[] + pressure='autogeneous' → atmosphere_type = autogeneous.
- Chemical atmosphere codes ("H2", "N2", "Ar") → AtmosphereTypeEnum values.
- Repeat(N): "N additional repeats" → RepetitionBlock wrapping preceding step,
  repetition_count = N + 1 (total executions).
- Non-numeric stirring_speed ("ultrassounds") → kept as raw description label.
- Non-numeric duration ("overnight") → kept as raw description label.
- Quantity lists with multiple entries (e.g. ['44.2 g', '0.2084 mmol']) produce
  one quantitative attribute per entry (has_mass + has_amount on the material).
- Unsupported actions ("Sieve") are skipped with a stderr warning.
"""

import re
import sys
import argparse
import importlib.util
from pathlib import Path
from typing import Any, Optional

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URI = "https://w3id.org/nfdi-de/dcat-ap-plus/labdata/example/"

# Qualitative temperature strings → TemperatureTargetTypeEnum value
QUALITATIVE_TEMPS: dict[str, str] = {
    "cool": "COOL",
    "heat": "HEAT",
    "room temperature": "ROOM_TEMPERATURE",
    "room_temperature": "ROOM_TEMPERATURE",
    "rt": "ROOM_TEMPERATURE",
    "reflux": "REFLUX",
    "ambient": "AMBIENT",
}

# Atmosphere abbreviations → AtmosphereTypeEnum value
ATMOSPHERE_MAP: dict[str, str] = {
    "h2": "hydrogen",
    "hydrogen": "hydrogen",
    "n2": "nitrogen",
    "nitrogen": "nitrogen",
    "ar": "argon",
    "argon": "argon",
    "o2": "oxygen",
    "oxygen": "oxygen",
    "air": "air",
    "inert": "inert",
    "vacuum": "vacuum",
    "autogeneous": "autogeneous",
    "autogenous": "autogeneous",   # common misspelling
}

# Unit string (lowercase) → QUDT unit URI fragment
# The full URI is https://qudt.org/vocab/unit/<fragment>
UNIT_MAP: dict[str, str] = {
    # Temperature
    "°c": "DEG_C",
    "c": "DEG_C",
    "k": "K",
    "°k": "K",
    "°f": "DEG_F",
    # Time
    "s": "SEC",
    "sec": "SEC",
    "second": "SEC",
    "seconds": "SEC",
    "min": "MIN",
    "minute": "MIN",
    "minutes": "MIN",
    "h": "HR",
    "hr": "HR",
    "hour": "HR",
    "hours": "HR",
    "day": "DAY",
    "days": "DAY",
    # Mass
    "µg": "MicroGM",
    "ug": "MicroGM",
    "mg": "MilliGM",
    "g": "GM",
    "kg": "KiloGM",
    # Volume
    "µl": "MicroL",
    "ul": "MicroL",
    "µml": "MicroL",
    "ml": "MilliL",
    "l": "L",
    # Amount of substance
    "nmol": "NanoMOL",
    "µmol": "MicroMOL",
    "umol": "MicroMOL",
    "mmol": "MilliMOL",
    "mol": "MOL",
    "kmol": "KiloMOL",
    # Concentration
    "m": "MOL-PER-L",                          # molarity
    "mm": "MilliMOL-PER-L",
    "µm": "MicroMOL-PER-L",
    "mol/ml": "MOL-PER-MilliL",
    "mol/l": "MOL-PER-L",
    "mmol/l": "MilliMOL-PER-L",
    "wt %": "Percent",
    "wt%": "Percent",
    "vol %": "Percent",
    "vol%": "Percent",
    "%": "Percent",
    # Stirring speed
    "rpm": "REV-PER-MIN",
    "rev/min": "REV-PER-MIN",
    # Flow rate
    "ml/min": "MilliL-PER-MIN",
    "ml min-1": "MilliL-PER-MIN",
    "ml min−1": "MilliL-PER-MIN",
    "l/min": "L-PER-MIN",
    "l/h": "L-PER-HR",
    # Heat ramp
    "°c/min": "DEG_C-PER-MIN",
    "°c min-1": "DEG_C-PER-MIN",
    "°c min−1": "DEG_C-PER-MIN",
    "k/min": "K-PER-MIN",
    "k min-1": "K-PER-MIN",
    # Pressure
    "bar": "BAR",
    "mbar": "MilliBAR",
    "pa": "PA",
    "kpa": "KiloPA",
    "mpa": "MegaPA",
    "atm": "ATM",
    "torr": "TORR",
}

# Lookup table: QUDT unit fragment → class name used for the QuantitativeAttribute
UNIT_TO_CLASS: dict[str, str] = {
    # Temperature
    "DEG_C": "Temperature", "K": "Temperature", "DEG_F": "Temperature",
    # Time
    "SEC": "Duration", "MIN": "Duration", "HR": "Duration", "DAY": "Duration",
    # Mass
    "MicroGM": "Mass", "MilliGM": "Mass", "GM": "Mass", "KiloGM": "Mass",
    # Volume
    "MicroL": "Volume", "MilliL": "Volume", "L": "Volume",
    # Amount
    "NanoMOL": "AmountOfSubstance", "MicroMOL": "AmountOfSubstance",
    "MilliMOL": "AmountOfSubstance", "MOL": "AmountOfSubstance", "KiloMOL": "AmountOfSubstance",
    # Concentration
    "MOL-PER-L": "Concentration", "MilliMOL-PER-L": "Concentration",
    "MicroMOL-PER-L": "Concentration", "MOL-PER-MilliL": "Concentration",
    "MilliMOL-PER-L": "Concentration", "Percent": "Concentration",
    # Stirring speed
    "REV-PER-MIN": "StirringSpeed",
    # Flow rate
    "MilliL-PER-MIN": "FlowRate", "L-PER-MIN": "FlowRate", "L-PER-HR": "FlowRate",
    # Heat ramp
    "DEG_C-PER-MIN": "HeatRamp", "K-PER-MIN": "HeatRamp",
    # Pressure
    "BAR": "Pressure", "MilliBAR": "Pressure", "PA": "Pressure",
    "KiloPA": "Pressure", "MegaPA": "Pressure", "ATM": "Pressure",
    "TORR": "Pressure",
}

QUDT_UNIT_BASE = "https://qudt.org/vocab/unit/"


# ---------------------------------------------------------------------------
# Value / unit parsing helpers
# ---------------------------------------------------------------------------

# Pre-compile regexes
_NUM_RE = re.compile(
    r"^([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(.*)$"
)
_RANGE_RE = re.compile(
    r"^([+-]?\d+(?:\.\d+)?)\s*[-–]\s*([+-]?\d+(?:\.\d+)?)\s*(.*)$"
)


def _clean(s: str) -> str:
    """Normalise Unicode minus and strip whitespace."""
    return s.replace("\u2212", "-").replace("\u2013", "-").strip()


def _qudt_uri(unit_fragment: str) -> str:
    return f"{QUDT_UNIT_BASE}{unit_fragment}"


def _resolve_unit(raw_unit: str) -> tuple[str, str]:
    """
    Map a raw unit string to (QUDT fragment, class name).
    Returns ('Unknown', 'QuantitativeAttribute') if unrecognised.
    """
    key = raw_unit.lower().strip()
    fragment = UNIT_MAP.get(key)
    if fragment is None:
        return raw_unit, "QuantitativeAttribute"
    cls = UNIT_TO_CLASS.get(fragment, "QuantitativeAttribute")
    return fragment, cls


def parse_value_unit(s: Any) -> Optional[tuple[float, str, str]]:
    """
    Parse a string like "65 °C" → (65.0, QUDT_URI, class_name).
    Handles ranges like "1.5-1.8" by taking the midpoint.
    Returns None if not parseable.
    """
    if not s or not isinstance(s, str):
        return None
    s = _clean(s)

    # Try range pattern first (e.g. '1.5-1.8')
    m = _RANGE_RE.match(s)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        value = (lo + hi) / 2.0
        raw_unit = m.group(3).strip()
        fragment, cls = _resolve_unit(raw_unit)
        return value, _qudt_uri(fragment), cls

    # Single value
    m = _NUM_RE.match(s)
    if not m:
        return None
    value = float(m.group(1))
    raw_unit = m.group(2).strip()
    fragment, cls = _resolve_unit(raw_unit)
    return value, _qudt_uri(fragment), cls


def make_quant(value: float, unit_uri: str, cls: str) -> dict:
    """Produce a QuantitativeAttribute sub-instance dict."""
    return {
        "type": cls,
        "value": value,
        "unit": {"id": unit_uri},
    }


# ---------------------------------------------------------------------------
# Domain-specific parsers
# ---------------------------------------------------------------------------

def parse_temperature(temp: Any) -> tuple[Optional[dict], Optional[str]]:
    """
    Returns (has_target_temperature dict, temperature_target_type string).
    Exactly one of the two will be non-None.
    """
    if not temp or not isinstance(temp, str):
        return None, None
    key = _clean(temp).lower()
    if key in QUALITATIVE_TEMPS:
        return None, QUALITATIVE_TEMPS[key]
    parsed = parse_value_unit(temp)
    if parsed:
        value, uri, cls = parsed
        return make_quant(value, uri, "Temperature"), None
    return None, None


def parse_duration(dur: Any) -> Optional[dict]:
    """Parse a duration string → Duration dict (or label-only dict if non-numeric)."""
    if not dur or not isinstance(dur, str):
        return None
    if _clean(dur).lower() in ("overnight", "o/n", "overnight."):
        return {"type": "Duration", "description": dur}
    parsed = parse_value_unit(dur)
    if parsed:
        value, uri, _ = parsed
        return make_quant(value, uri, "Duration")
    return None


def parse_stirring_speed(speed: Any) -> Optional[dict]:
    """Parse stirring speed → StirringSpeed dict (or label-only dict if non-numeric)."""
    if not speed or not isinstance(speed, str):
        return None
    parsed = parse_value_unit(speed)
    if parsed:
        value, uri, _ = parsed
        return make_quant(value, uri, "StirringSpeed")
    # Non-numeric method description (e.g. "ultrassounds")
    return {"type": "StirringSpeed", "description": _clean(speed)}


def parse_heat_ramp(ramp: Any) -> Optional[dict]:
    """Parse a heat-ramp string → HeatRamp dict."""
    if not ramp or not isinstance(ramp, str):
        return None
    parsed = parse_value_unit(_clean(ramp))
    if parsed:
        value, uri, _ = parsed
        return make_quant(value, uri, "HeatRamp")
    return None


def parse_pressure(pres: Any) -> tuple[Optional[dict], Optional[str]]:
    """
    Returns (Pressure QuantitativeAttribute, extra_atmosphere_type_string).
    'autogeneous' in the pressure field → atmosphere type, not a numeric pressure.
    """
    if not pres or not isinstance(pres, str):
        return None, None
    key = _clean(pres).lower()
    if key in ("autogeneous", "autogenous"):
        return None, "autogeneous"
    parsed = parse_value_unit(pres)
    if parsed:
        value, uri, _ = parsed
        return make_quant(value, uri, "Pressure"), None
    return None, None


def normalize_atmosphere(atm: Any) -> Optional[str]:
    """Normalise atmosphere value → AtmosphereTypeEnum string or None."""
    if atm is None or atm == [] or atm == "":
        return None
    if isinstance(atm, str):
        return ATMOSPHERE_MAP.get(atm.lower().strip(), atm.lower().strip())
    return None


def parse_flow_rate(fr: Any) -> Optional[dict]:
    """Parse a flow-rate string → FlowRate dict."""
    if not fr or not isinstance(fr, str):
        return None
    parsed = parse_value_unit(_clean(fr))
    if parsed:
        value, uri, _ = parsed
        return make_quant(value, uri, "FlowRate")
    return None


def parse_quantity_list(qty_list: list) -> list[dict]:
    """
    Parse a quantity list (e.g. ['44.2 g', '0.2084 mmol']) into a list of
    QuantitativeAttribute dicts, one per parseable entry.
    """
    result = []
    for q in qty_list or []:
        if not q:
            continue
        parsed = parse_value_unit(q)
        if parsed:
            value, uri, cls = parsed
            result.append(make_quant(value, uri, cls))
    return result


def parse_ph(ph: Any) -> Optional[dict]:
    """Parse a pH value (string or range) → PHValue dict."""
    if not ph:
        return None
    parsed = parse_value_unit(str(ph))
    if parsed:
        value, _, _ = parsed
        # pH is dimensionless; QUDT uses PH unit
        return make_quant(value, "https://qudt.org/vocab/unit/PH", "PHValue")
    # Could not parse — try extracting leading number
    m = re.match(r"([+-]?\d+(?:\.\d+)?)", str(ph))
    if m:
        return make_quant(float(m.group(1)), "https://qudt.org/vocab/unit/PH", "PHValue")
    return None


def parse_concentration(conc_list: list) -> Optional[dict]:
    """Parse the first parseable concentration string in a list."""
    for c in conc_list or []:
        if not c:
            continue
        parsed = parse_value_unit(str(c))
        if parsed:
            value, uri, _ = parsed
            return make_quant(value, uri, "Concentration")
    return None


def build_material(mat: dict, mat_id: str) -> Optional[dict]:
    """
    Build a MaterialSample dict from a raw material dict:
        {'name': ..., 'quantity': [...], 'concentration': [...]}
    """
    if not mat or not isinstance(mat, dict):
        return None
    node: dict[str, Any] = {
        "id": mat_id,
        "type": "MaterialSample",
        "title": mat.get("name") or "unnamed material",
    }
    qtys = parse_quantity_list(mat.get("quantity", []))
    for q in qtys:
        cls = q["type"]
        if cls == "Mass" and "has_mass" not in node:
            node["has_mass"] = q
        elif cls == "Volume" and "has_volume" not in node:
            node["has_volume"] = q
        elif cls == "AmountOfSubstance" and "has_amount" not in node:
            node["has_amount"] = q
        # If we already have that slot, add it under an alias to avoid data loss
        elif cls == "Mass":
            node.setdefault("_extra_mass", []).append(q)
        elif cls == "Volume":
            node.setdefault("_extra_volume", []).append(q)
    conc = parse_concentration(mat.get("concentration", []))
    if conc:
        node["has_concentration"] = conc
    return node


# ---------------------------------------------------------------------------
# ID generation helpers
# ---------------------------------------------------------------------------

def _seq_uri(seq_num: int) -> str:
    return f"{BASE_URI}seq_{seq_num:04d}"


def _step_uri(seq_num: int, step_num: int) -> str:
    return f"{_seq_uri(seq_num)}/step_{step_num:03d}"


def _mat_uri(seq_num: int, step_num: int) -> str:
    return f"{_seq_uri(seq_num)}/mat_{step_num:03d}"


def _block_uri(seq_num: int, block_num: int) -> str:
    return f"{_seq_uri(seq_num)}/repeat_{block_num:03d}"


# ---------------------------------------------------------------------------
# Single-action → step node
# ---------------------------------------------------------------------------

def convert_action(
    action: dict,
    seq_num: int,
    step_counter: int,
) -> Optional[dict]:
    """
    Convert one raw action dict to a step node dict.

    Returns None for 'Repeat' (handled by the caller) and unsupported actions.
    The returned node does NOT yet have `had_input_activity` or
    `has_successor_step` — those are added in a second pass.
    """
    act: str = action.get("action", "")
    content: dict = action.get("content") or {}
    sid = _step_uri(seq_num, step_counter)

    if act == "NewSolution":
        node: dict = {"id": sid, "type": "SolutionPreparationStep"}
        sol = content.get("solution")
        if isinstance(sol, dict) and sol.get("name"):
            node["title"] = sol["name"]
        return node

    elif act == "Add":
        node = {"id": sid, "type": "MaterialAdditionStep"}
        mat = build_material(content.get("material"), _mat_uri(seq_num, step_counter))
        if mat:
            node["has_added_material"] = mat
        if content.get("dropwise") is True:
            node["added_dropwise"] = True
        dur = parse_duration(content.get("duration"))
        if dur:
            node["has_step_duration"] = dur
        ph = parse_ph(content.get("ph"))
        if ph:
            node["has_ph_value"] = ph
        return node

    elif act == "Stir":
        node = {"id": sid, "type": "StirringStep"}
        dur = parse_duration(content.get("duration"))
        if dur:
            node["has_step_duration"] = dur
        speed = parse_stirring_speed(content.get("stirring_speed"))
        if speed:
            node["has_stirring_speed"] = speed
        return node

    elif act == "ChangeTemperature":
        node = {"id": sid, "type": "TemperatureChangeStep"}
        temp_q, temp_type = parse_temperature(content.get("temperature"))
        if temp_q:
            node["has_target_temperature"] = temp_q
        if temp_type:
            node["temperature_target_type"] = temp_type
        if content.get("microwave") is True:
            node["uses_microwave"] = True
        ramp = parse_heat_ramp(content.get("heat_ramp"))
        if ramp:
            node["has_heat_ramp"] = ramp
        return node

    elif act == "SetAtmosphere":
        node = {"id": sid, "type": "AtmosphereSettingStep"}
        atm = normalize_atmosphere(content.get("atmosphere"))
        pres_q, autogen = parse_pressure(content.get("pressure"))
        # Merge: explicit atmosphere takes priority; 'autogeneous' from pressure field is fallback
        final_atm = atm or autogen
        if final_atm:
            node["has_atmosphere_type"] = final_atm
        if pres_q:
            node["has_pressure"] = pres_q
        fr = parse_flow_rate(content.get("flow_rate"))
        if fr:
            node["has_flow_rate"] = fr
        return node

    elif act == "Wait":
        node = {"id": sid, "type": "WaitingStep"}
        dur = parse_duration(content.get("duration"))
        if dur:
            node["has_step_duration"] = dur
        return node

    elif act == "Separate":
        node = {"id": sid, "type": "SeparationStep"}
        phase = content.get("phase_to_keep")
        if phase:
            node["phase_to_keep"] = str(phase)
        method = content.get("method")
        if method:
            # Bind to SeparationMethodEnum value (plain string for YAML)
            node["uses_separation_method"] = method
        return node

    elif act == "Wash":
        node = {"id": sid, "type": "WashingStep"}
        mat = build_material(content.get("material"), _mat_uri(seq_num, step_counter))
        if mat:
            node["uses_washing_material"] = mat
        method = content.get("method")
        if method:
            node["uses_washing_method"] = method
        return node

    elif act == "Grind":
        return {"id": sid, "type": "GrindingStep"}

    elif act == "Repeat":
        # Caller handles this — should never reach here
        return None

    else:
        print(
            f"  [WARN] seq {seq_num:04d}: unsupported action '{act}' at counter "
            f"{step_counter} — skipped",
            file=sys.stderr,
        )
        return None


# ---------------------------------------------------------------------------
# Sequence → LabSynthesisActivity
# ---------------------------------------------------------------------------

def convert_sequence(sequence: list[dict], seq_num: int) -> dict:
    """
    Convert a raw action sequence to a LabSynthesisActivity dict.

    Handles:
    - Building step nodes
    - RepetitionBlock construction (Repeat action wraps preceding step)
    - Linear had_input_activity / has_successor_step assignment
    - RepetitionBlock inner-step pointer propagation
    """
    # ── 1. Build a flat list of step/block dicts ───────────────────────────
    steps_flat: list[dict] = []
    step_counter = 0
    repeat_block_counter = 0

    for raw_action in sequence:
        act = raw_action.get("action", "")

        if act == "Repeat":
            amount_str = (raw_action.get("content") or {}).get("amount", "1")
            try:
                additional = int(amount_str)
            except (ValueError, TypeError):
                additional = 1
            total_count = additional + 1  # schema convention: total executions

            if not steps_flat:
                print(
                    f"  [WARN] seq {seq_num:04d}: Repeat with no preceding step — skipped",
                    file=sys.stderr,
                )
                continue

            # Pop the preceding step and wrap it in a RepetitionBlock
            prev_step = steps_flat.pop()
            repeat_block_counter += 1
            block: dict = {
                "id": _block_uri(seq_num, repeat_block_counter),
                "type": "RepetitionBlock",
                "repetition_count": total_count,
                "has_part": [prev_step],
            }
            steps_flat.append(block)
            continue

        step_counter += 1
        node = convert_action(raw_action, seq_num, step_counter)
        if node is not None:
            steps_flat.append(node)

    # ── 2. Assign backward and forward pointers (linear chain) ────────────
    n = len(steps_flat)
    for i, node in enumerate(steps_flat):
        prev_id: Optional[str] = steps_flat[i - 1]["id"] if i > 0 else None
        next_id: Optional[str] = steps_flat[i + 1]["id"] if i < n - 1 else None

        if prev_id:
            node["had_input_activity"] = prev_id
        if next_id:
            node["has_successor_step"] = [next_id]

        # RepetitionBlock: propagate pointers to inner steps as well
        if node["type"] == "RepetitionBlock":
            inner: list[dict] = node.get("has_part", [])
            ni = len(inner)
            for j, inner_step in enumerate(inner):
                # Backward: preceding outer step (or previous inner step)
                if j == 0:
                    inner_prev = prev_id
                else:
                    inner_prev = inner[j - 1]["id"]
                # Forward: next inner step (or first step after the block)
                if j < ni - 1:
                    inner_next = inner[j + 1]["id"]
                else:
                    inner_next = next_id

                if inner_prev:
                    inner_step["had_input_activity"] = inner_prev
                if inner_next:
                    inner_step["has_successor_step"] = [inner_next]

            # The preceding outer step should also point to the first inner step
            # (so queries on inner step type don't require wrapper traversal)
            if i > 0 and inner:
                pred = steps_flat[i - 1]
                first_inner_id = inner[0]["id"]
                succ = pred.setdefault("has_successor_step", [])
                if first_inner_id not in succ:
                    succ.append(first_inner_id)

    # ── 3. Assemble the LabSynthesisActivity ──────────────────────────────
    return {
        "id": _seq_uri(seq_num),
        "type": "LabSynthesisActivity",
        "title": f"Synthesis Sequence {seq_num:04d}",
        "has_synthesis_step": steps_flat,
    }


# ---------------------------------------------------------------------------
# YAML serialisation helpers
# ---------------------------------------------------------------------------

class _LiteralStr(str):
    """Marker for YAML block scalar strings."""


def _literal_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


def _build_dumper() -> type:
    dumper = yaml.Dumper
    dumper.add_representer(_LiteralStr, _literal_representer)
    return dumper


def to_yaml(data: dict) -> str:
    """Serialise to YAML with sane defaults."""
    return yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        width=120,
    )


# ---------------------------------------------------------------------------
# Loading the source data file
# ---------------------------------------------------------------------------

def load_sequences(source_path: Path) -> list[list[dict]]:
    """
    Load `action_sequences` from `activation_sequences_costa.py`.

    The file defines a bare tuple/list of sequences (not a module with exports),
    so we exec() it in an isolated namespace.
    """
    namespace: dict = {}
    source_code = source_path.read_text(encoding="utf-8")

    # The file contains:
    #   action_sequences = ([...], [...], ...)   ← tuple of lists
    #   Mappings = (...)
    #   [...]                                    ← standalone list (extra examples)
    #
    # We exec() it and then pull out `action_sequences`.
    # The trailing standalone list at the end of the file has no variable name,
    # so it just becomes a discarded expression — that's fine.
    exec(compile(source_code, str(source_path), "exec"), namespace)

    seqs = namespace.get("action_sequences")
    if seqs is None:
        raise RuntimeError(
            "Could not find `action_sequences` in the source file. "
            "Check the variable name."
        )
    # Wrap in list if it's a tuple/generator
    return list(seqs)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert activation_sequences_costa.py to dcat_p_lab YAML instances."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).parent.parent / "activation_sequences_costa.py",
        help="Path to activation_sequences_costa.py (default: repo root)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "examples" / "sequences",
        help="Directory to write YAML files (default: examples/sequences/)",
    )
    parser.add_argument(
        "--max-seqs",
        type=int,
        default=None,
        help="Only convert the first N sequences (default: all)",
    )
    parser.add_argument(
        "--seq-offset",
        type=int,
        default=1,
        help="Starting sequence number (default: 1)",
    )
    args = parser.parse_args()

    # Validate source
    if not args.source.exists():
        print(f"ERROR: Source file not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    # Load sequences
    print(f"Loading sequences from {args.source} …")
    sequences = load_sequences(args.source)
    print(f"  Found {len(sequences)} sequences.")

    if args.max_seqs is not None:
        sequences = sequences[: args.max_seqs]
        print(f"  Limiting to first {args.max_seqs} sequences.")

    # Prepare output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Convert and write
    ok = 0
    errors = 0
    for i, seq in enumerate(sequences):
        seq_num = i + args.seq_offset
        out_path = args.output_dir / f"seq_{seq_num:04d}.yaml"
        try:
            activity = convert_sequence(seq, seq_num)
            out_path.write_text(to_yaml(activity), encoding="utf-8")
            step_count = len(activity.get("has_synthesis_step", []))
            print(f"  seq_{seq_num:04d}.yaml  ({step_count} top-level steps)")
            ok += 1
        except Exception as exc:
            print(
                f"  [ERROR] seq_{seq_num:04d}: {exc}",
                file=sys.stderr,
            )
            errors += 1

    print(f"\nDone: {ok} written, {errors} errors -> {args.output_dir}")


if __name__ == "__main__":
    main()
