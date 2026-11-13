"""Validated, additive edgeR designs built from the existing contrast editor."""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
from sqlalchemy.orm import Session

from ..db.models import SampleStage

VARIABLE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
SAMPLE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,180}$")


def contrast_context(db: Session, user_id: int, contrast_ids: list[int] | None = None) -> dict:
    rows = db.query(SampleStage).filter(
        SampleStage.user_id == user_id, SampleStage.stage_id == 8,
        SampleStage.status == "Contrast",
    ).all()
    selected = set(contrast_ids) if contrast_ids is not None else None
    if selected is not None and (not selected or not selected <= {row.id for row in rows}):
        raise ValueError("Selected contrast does not belong to this user")
    groups: dict[str, str] = {}
    contrasts = []
    for row in rows:
        if selected is not None and row.id not in selected:
            continue
        try:
            left, right = row.name.split("*", 1)
            sides = []
            for side in (left, right):
                match = re.fullmatch(r"([^()]+)\(([^()]+)\)", side.strip())
                if not match:
                    raise ValueError("Invalid contrast format")
                group = match.group(1).strip()
                samples = [x.strip() for x in match.group(2).split(";") if x.strip()]
                if not group or not samples:
                    raise ValueError("Contrast has no group or samples")
                if any(not SAMPLE_NAME.fullmatch(sample) for sample in samples) or any(
                    character in group for character in "\t\r\n"
                ):
                    raise ValueError("Invalid sample or group name")
                for sample in samples:
                    if sample in groups and groups[sample] != group:
                        raise ValueError(f"Sample {sample} belongs to multiple groups")
                    groups[sample] = group
                sides.append({"group": group, "samples": samples})
            if sides[0]["group"] == sides[1]["group"]:
                raise ValueError("A contrast must compare different groups")
            contrasts.append({"id": row.id, "name": row.name, "positive": sides[0], "negative": sides[1]})
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"Invalid contrast {row.id}: {exc}") from exc
    return {"samples": groups, "contrasts": contrasts}


def validate_design(db: Session, user_id: int, config: dict) -> dict:
    ids = config.get("contrast_ids") or []
    if not isinstance(ids, list) or not all(isinstance(x, int) for x in ids):
        raise ValueError("Select at least one contrast")
    context = contrast_context(db, user_id, ids)
    samples = sorted(context["samples"])
    if len(samples) < 3:
        raise ValueError("At least three samples are required to estimate dispersion")
    counts = Counter(context["samples"].values())
    if any(count < 2 for count in counts.values()):
        raise ValueError("Each group needs at least two biological samples")
    columns = []
    names = []
    for group in sorted(counts):
        columns.append([1.0 if context["samples"][sample] == group else 0.0 for sample in samples])
        names.append(group)
    variables = config.get("variables") or []
    if not isinstance(variables, list) or len(variables) > 12:
        raise ValueError("Invalid variable list")
    seen = {"group"}
    clean_variables = []
    for variable in variables:
        if not isinstance(variable, dict):
            raise ValueError("Invalid variable")
        name = str(variable.get("name") or "").strip()
        if not VARIABLE_NAME.fullmatch(name) or name.lower() in seen:
            raise ValueError(f"Invalid or duplicate variable name: {name}")
        seen.add(name.lower())
        kind = variable.get("kind")
        values = variable.get("values") or {}
        if kind not in ("categorical", "numeric") or not isinstance(values, dict):
            raise ValueError(f"Invalid type or values for {name}")
        if set(values) != set(samples):
            raise ValueError(f"Provide one {name} value for every selected sample")
        if kind == "categorical":
            labels = [str(values[sample]).strip() for sample in samples]
            if any(not label or len(label) > 80 or any(c in label for c in "\t\r\n") for label in labels):
                raise ValueError(f"Missing or invalid {name} value")
            levels = sorted(set(labels))
            if len(levels) < 2:
                raise ValueError(f"{name} needs at least two distinct values")
            for level in levels[1:]:
                columns.append([1.0 if label == level else 0.0 for label in labels])
                names.append(f"{name}:{level}")
            normalized = dict(zip(samples, labels))
        else:
            try:
                numbers = [float(values[sample]) for sample in samples]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must contain numeric values") from exc
            if not all(math.isfinite(number) for number in numbers):
                raise ValueError(f"{name} must contain finite values")
            if len(set(numbers)) < 2:
                raise ValueError(f"{name} needs varying values")
            columns.append(numbers)
            names.append(name)
            normalized = dict(zip(samples, numbers))
        clean_variables.append({"name": name, "kind": kind, "values": normalized})
    matrix = np.asarray(columns, dtype=float).T
    rank = int(np.linalg.matrix_rank(matrix))
    if rank < matrix.shape[1]:
        raise ValueError("Variables are confounded; the design matrix is not full rank")
    residual_df = len(samples) - rank
    if residual_df < 1:
        raise ValueError("The model has no residual degrees of freedom")
    formula = "~0+group" + "".join("+" + variable["name"] for variable in clean_variables)
    return {"formula": formula, "samples": context["samples"],
            "contrasts": context["contrasts"], "variables": clean_variables,
            "columns": names, "rank": rank, "residual_df": residual_df}
