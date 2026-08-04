import sys
import os
import re
from collections import Counter, defaultdict


def parse_attributes(attr_field):
    """Parse attributes from GFF or GTF attribute field into key->value pairs."""
    attrs = []
    # Split on semicolon, but keep quoted values intact
    for raw in attr_field.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        # GFF format: key=value
        if "=" in raw:
            key, value = raw.split("=", 1)
            attrs.append((key.strip(), value.strip().strip('"')))
        else:
            # GTF format: key "value"; or key "value" key2 "value2";
            m = re.match(r'^(\S+)\s+"([^"]+)"', raw)
            if m:
                key = m.group(1)
                value = m.group(2)
                attrs.append((key.strip(), value.strip()))
            else:
                # fallback: split by whitespace
                parts = raw.split()
                if len(parts) >= 2:
                    key = parts[0]
                    value = parts[1].strip('"')
                    attrs.append((key.strip(), value.strip()))
    return attrs


def parse_gff(gff_file):
    features = Counter()
    attributes = defaultdict(Counter)

    with open(gff_file, "r") as file:
        for line in file:
            if line.startswith("#") or not line.strip():
                continue

            parts = line.strip().split("\t")
            if len(parts) < 9:
                continue

            feature = parts[2]
            features[feature] += 1

            attr_field = parts[8]
            for key, value in parse_attributes(attr_field):
                attributes[key][value] += 1

    return features, attributes


def display_results(features, attributes):
    print("\nFrequência de Features (-t):\n")
    for feature, count in features.items():
        print(f"{feature}: {count}")

    print("\nAtributos disponíveis para -i e exemplos:\n")
    for attr, values in attributes.items():
        example_values = list(values.keys())[:1]
        print(f"{attr}: {len(values)} valores únicos (Ex.: {', '.join(example_values)})")
    print("\n")


def find_gff_or_gtf(path):
    """Given a path to a file or directory, return an existing GFF/GTF file path or None."""
    # If it's a file and exists, return it
    if os.path.isfile(path):
        return path

    # If it's a directory, check for genomic.gff then genomic.gtf
    if os.path.isdir(path):
        gff = os.path.join(path, "genomic.gff")
        gff3 = os.path.join(path, "genomic.gff3")
        gtf = os.path.join(path, "genomic.gtf")
        if os.path.isfile(gff3):
            return gff3
        if os.path.isfile(gff):
            return gff
        if os.path.isfile(gtf):
            return gtf

    # If path has extension .gff or .gtf but doesn't exist, try swapping
    base, ext = os.path.splitext(path)
    if ext.lower() == ".gff":
        alt = base + ".gtf"
        if os.path.isfile(alt):
            return alt
    if ext.lower() == ".gtf":
        alt = base + ".gff"
        if os.path.isfile(alt):
            return alt

    return None


def main():
    if len(sys.argv) != 2:
        print("Uso: python analyze_gff.py <arquivo.gff|arquivo.gff3|arquivo.gtf|diretorio_do_genoma>")
        sys.exit(1)

    input_path = sys.argv[1]
    gff_file = find_gff_or_gtf(input_path)
    if not gff_file:
        print(f"Erro: nenhum arquivo GFF/GTF encontrado para '{input_path}'")
        sys.exit(2)

    features, attributes = parse_gff(gff_file)
    display_results(features, attributes)


if __name__ == "__main__":
    main()
