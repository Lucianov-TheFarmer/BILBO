from db.database import SessionLocal
from db.models import SampleStage

# Substitua por seus dados reais
rows = [
    # id, sample_id, stage_id, name, sra_code, size, status, user_id
    (198, 1, 6, "A1_rmdup_counts_picard.txt", "A1", "530 KB", "Completed", 1),
    (199, 1, 6, "A2_rmdup_counts_picard.txt", "A2", "530 KB", "Completed", 1),
    (200, 1, 6, "A3_rmdup_counts_picard.txt", "A3", "530 KB", "Completed", 1),
    (201, 1, 6, "A4_rmdup_counts_picard.txt", "A4", "530 KB", "Completed", 1),
    (202, 1, 6, "A5_rmdup_counts_picard.txt", "A5", "530 KB", "Completed", 1),
    (203, 1, 6, "A6_rmdup_counts_picard.txt", "A6", "530 KB", "Completed", 1),
    (204, 1, 6, "A7_rmdup_counts_picard.txt", "A7", "530 KB", "Completed", 1),
    (205, 1, 6, "A8_rmdup_counts_picard.txt", "A8", "530 KB", "Completed", 1),
    (206, 1, 6, "A9_rmdup_counts_picard.txt", "A9", "530 KB", "Completed", 1),
    (207, 1, 6, "A10_rmdup_counts_picard.txt", "A10", "530 KB", "Completed", 1),
    (208, 1, 6, "A11_rmdup_counts_picard.txt", "A11", "530 KB", "Completed", 1),
    (209, 1, 6, "A12_rmdup_counts_picard.txt", "A12", "530 KB", "Completed", 1),
    (210, 1, 6, "A13_rmdup_counts_picard.txt", "A13", "530 KB", "Completed", 1),
    (211, 1, 6, "A14_rmdup_counts_picard.txt", "A14", "530 KB", "Completed", 1),
    (212, 1, 6, "A15_rmdup_counts_picard.txt", "A15", "530 KB", "Completed", 1),
    (213, 1, 6, "A16_rmdup_counts_picard.txt", "A16", "530 KB", "Completed", 1),
    (214, 1, 6, "A17_rmdup_counts_picard.txt", "A17", "530 KB", "Completed", 1),
    (215, 1, 6, "A18_rmdup_counts_picard.txt", "A18", "530 KB", "Completed", 1),
    (216, 1, 6, "A19_rmdup_counts_picard.txt", "A19", "530 KB", "Completed", 1),
    (217, 1, 6, "A20_rmdup_counts_picard.txt", "A20", "530 KB", "Completed", 1),
    (218, 1, 6, "A21_rmdup_counts_picard.txt", "A21", "530 KB", "Completed", 1),
    (219, 1, 6, "A22_rmdup_counts_picard.txt", "A22", "530 KB", "Completed", 1),
    (220, 1, 6, "A23_rmdup_counts_picard.txt", "A23", "530 KB", "Completed", 1),
    (221, 1, 6, "A24_rmdup_counts_picard.txt", "A24", "530 KB", "Completed", 1),
    (222, 1, 6, "A25_rmdup_counts_picard.txt", "A25", "530 KB", "Completed", 1),
    (223, 1, 6, "A26_rmdup_counts_picard.txt", "A26", "530 KB", "Completed", 1),
    (224, 1, 6, "A27_rmdup_counts_picard.txt", "A27", "530 KB", "Completed", 1),
    (225, 1, 6, "A28_rmdup_counts_picard.txt", "A28", "530 KB", "Completed", 1),
    (226, 1, 6, "A29_rmdup_counts_picard.txt", "A29", "530 KB", "Completed", 1),
    (227, 1, 6, "A30_rmdup_counts_picard.txt", "A30", "530 KB", "Completed", 1),
    (228, 1, 6, "A31_rmdup_counts_picard.txt", "A31", "530 KB", "Completed", 1),
    (229, 1, 6, "A32_rmdup_counts_picard.txt", "A32", "530 KB", "Completed", 1),
    (230, 1, 6, "A33_rmdup_counts_picard.txt", "A33", "530 KB", "Completed", 1),
    (231, 1, 6, "A34_rmdup_counts_picard.txt", "A34", "530 KB", "Completed", 1),
    (232, 1, 6, "A35_rmdup_counts_picard.txt", "A35", "530 KB", "Completed", 1),
    (233, 1, 6, "A36_rmdup_counts_picard.txt", "A36", "530 KB", "Completed", 1),
    (234, 1, 6, "A37_rmdup_counts_picard.txt", "A37", "530 KB", "Completed", 1),
    (235, 1, 6, "A38_rmdup_counts_picard.txt", "A38", "530 KB", "Completed", 1),
    (236, 1, 6, "A39_rmdup_counts_picard.txt", "A39", "530 KB", "Completed", 1),
    (237, 1, 6, "A40_rmdup_counts_picard.txt", "A40", "530 KB", "Completed", 1),
    (238, 1, 6, "A41_rmdup_counts_picard.txt", "A41", "530 KB", "Completed", 1),
    (239, 1, 6, "A42_rmdup_counts_picard.txt", "A42", "530 KB", "Completed", 1),
    (240, 1, 6, "A43_rmdup_counts_picard.txt", "A43", "530 KB", "Completed", 1),
    (241, 1, 6, "A44_rmdup_counts_picard.txt", "A44", "530 KB", "Completed", 1),
    (242, 1, 6, "A45_rmdup_counts_picard.txt", "A45", "530 KB", "Completed", 1),
    (243, 1, 6, "A46_rmdup_counts_picard.txt", "A46", "530 KB", "Completed", 1),
    (244, 1, 6, "A47_rmdup_counts_picard.txt", "A47", "530 KB", "Completed", 1),
    (245, 1, 6, "A48_rmdup_counts_picard.txt", "A48", "530 KB", "Completed", 1),
]

def main():
    session = SessionLocal()
    objs = [
        SampleStage(
            id=row[0],
            stage_id=row[2],
            name=row[3],
            sra_code=row[4],
            size=row[5],
            status=row[6],
            user_id=row[7],
        )
        for row in rows
    ]
    session.bulk_save_objects(objs)
    session.commit()
    session.close()
    print(f"{len(objs)} registros inseridos com sucesso.")

if __name__ == "__main__":
    main()
