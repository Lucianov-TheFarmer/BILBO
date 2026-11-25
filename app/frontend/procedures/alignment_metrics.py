"""Read the per-sample mapping summary produced by STAR."""

from __future__ import annotations


_COUNTS = {
    "Number of input reads": "input_reads",
    "Uniquely mapped reads number": "unique_reads",
    "Number of reads mapped to multiple loci": "multiple_loci",
    "Number of reads mapped to too many loci": "too_many_loci",
    "Number of reads unmapped: too many mismatches": "unmapped_mismatches",
    "Number of reads unmapped: too short": "unmapped_short",
    "Number of reads unmapped: other": "unmapped_other",
    "Number of chimeric reads": "chimeric_reads",
    "Number of splices: Total": "splices",
}


def parse_star_final_log(content: str) -> dict[str, int | float]:
    """Return STAR's mutually exclusive mapping categories and a few details."""
    values: dict[str, int | float] = {}
    for line in content.splitlines():
        if "|" not in line:
            continue
        label, raw_value = (part.strip() for part in line.split("|", 1))
        field = _COUNTS.get(label)
        if field:
            values[field] = int(raw_value.replace(",", ""))
        elif label == "Mismatch rate per base, %":
            values["mismatch_rate"] = float(raw_value.removesuffix("%"))

    required = ("input_reads", "unique_reads", "multiple_loci", "too_many_loci",
                "unmapped_mismatches", "unmapped_short", "unmapped_other")
    if any(field not in values for field in required):
        raise ValueError("STAR Log.final.out is missing mapping counts")
    values["mapped_reads"] = values["unique_reads"] + values["multiple_loci"]
    values["unmapped_reads"] = (values["unmapped_mismatches"] +
                                values["unmapped_short"] + values["unmapped_other"])
    return values
