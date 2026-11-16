"""Regression checks for DEG protein selection and preservation of existing GO."""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend" / "scripts"))

from annotate_deg_by_homology import annotate  # noqa: E402
from extract_deg_proteins import extract  # noqa: E402


class GoHomologyTest(unittest.TestCase):
    def test_gene_ids_resolve_through_transcripts_and_protein_ids(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            root = Path(temp)
            workbook, gff, proteins, selected = (
                root / "deg.xlsx", root / "genes.gff3", root / "proteins.fa", root / "selected.fa")
            pd.DataFrame({"gene_id": ["ABC", "GENE1"]}).to_excel(workbook, index=False)
            gff.write_text(
                'chr1\t.\tmRNA\t1\t90\t.\t+\t.\tID=rna-T1;Parent=gene-ABC\n'
                'chr1\t.\tCDS\t1\t30\t.\t+\t0\tParent=rna-T1;protein_id=XP_1\n'
                'chr1\t.\tmRNA\t1\t90\t.\t+\t.\tID=rna-T2;Parent=gene-ABC\n'
                'chr1\t.\tCDS\t1\t45\t.\t+\t0\tParent=rna-T2;protein_id=XP_2\n'
                'chr1\t.\ttranscript\t1\t80\t.\t+\t.\tgene_id "GENE1"; transcript_id "TX1";\n',
                encoding="utf-8",
            )
            proteins.write_text(">XP_1\nMAAA\n>XP_2\nMAAAAA\n>TX1\nMQQQ\n", encoding="utf-8")
            result = extract(workbook, proteins, selected, gff)
            self.assertEqual(result["source_ids"], {"ABC": "XP_2", "GENE1": "TX1"})
            self.assertIn(">ABC source=XP_2\nMAAAAA\n", selected.read_text())

    def test_existing_go_and_function_survive_homology_annotation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            root = Path(temp)
            source, output = root / "input.xlsx", root / "output.xlsx"
            pd.DataFrame({"gene_id": ["A", "B"], "Uniprot BP": ["old [GO:0008150]", ""],
                          "Uniprot Function": ["Existing function", ""]}).to_excel(source, index=False)
            reference = {"Gene Ontology (biological process)": "new [GO:0009987]",
                         "Gene Names": "NEW", "Protein names": "Full protein name",
                         "Function [CC]": "FUNCTION: Catalyzes a test reaction.",
                         "Organism": "Plant"}
            hits = {gene: {"source": reference, "accession": "P12345", "identity": 80,
                           "coverage": .9, "evalue": 1e-50} for gene in ("A", "B")}
            extraction = {"source_ids": {"A": "TX_A", "B": "TX_B"}, "found": 2}
            result = annotate(source, output, hits, {"A", "B"}, set(),
                              {"A": "MAAA", "B": "MBBB"}, extraction, {}, "test")
            frame = pd.read_excel(output)
            self.assertEqual(frame.loc[0, "Uniprot BP"], "old [GO:0008150]")
            self.assertEqual(frame.loc[0, "Uniprot Function"], "Existing function")
            self.assertEqual(frame.loc[0, "Homology status"], "existing_go")
            self.assertEqual(frame.loc[1, "Homology status"], "go_inferred")
            self.assertEqual(frame.loc[1, "Uniprot protein name"], "Full protein name")
            self.assertEqual(frame.loc[1, "Uniprot Function"], "FUNCTION: Catalyzes a test reaction.")
            self.assertEqual(frame.loc[1, "Uniprot function source"], "UniProt FUNCTION comment")
            self.assertEqual(result["go_annotated"], 2)


if __name__ == "__main__":
    unittest.main()
