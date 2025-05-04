import sys
from collections import Counter, defaultdict

def parse_gff(gff_file):
    features = Counter()
    attributes = defaultdict(Counter)

    with open(gff_file, 'r') as file:
        for line in file:
            if line.startswith("#") or not line.strip():
                continue

            parts = line.strip().split("\t")
            if len(parts) < 9:
                continue

            feature = parts[2]
            features[feature] += 1

            attr_field = parts[8]
            for attr in attr_field.split(";"):
                if "=" in attr:
                    key, value = attr.split("=", 1)
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

def main():
    if len(sys.argv) != 2:
        print("Uso: python analyze_gff.py <arquivo.gff>")
        sys.exit(1)

    gff_file = sys.argv[1]
    features, attributes = parse_gff(gff_file)
    display_results(features, attributes)

if __name__ == "__main__":
    main()
