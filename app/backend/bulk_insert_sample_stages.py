from db.database import SessionLocal
from db.models import SampleStage

# Substitua por seus dados reais
rows = [
    # id, sample_id, stage_id, name, sra_code, size, status, user_id
    (198, 1, 6, "WaT_AC_5.tsv", "WaT_AC_5", "530 KB", "Completed", 1),
    (199, 1, 6, "WaT_CA_1.tsv", "WaT_CA_1", "530 KB", "Completed", 1),
    (200, 1, 6, "WaT_CA_2.tsv", "WaT_CA_2", "530 KB", "Completed", 1),
    (201, 1, 6, "WaT_CA_3.tsv", "WaT_CA_3", "530 KB", "Completed", 1),
    (202, 1, 6, "WaT_CA_4.tsv", "WaT_CA_4", "530 KB", "Completed", 1),
    (203, 1, 6, "WaT_CA_5.tsv", "WaT_CA_5", "530 KB", "Completed", 1),
    (204, 1, 6, "OpT_CA_4.tsv", "OpT_CA_4", "530 KB", "Completed", 1),
    (205, 1, 6, "OpT_CA_5.tsv", "OpT_CA_5", "530 KB", "Completed", 1),
    (206, 1, 6, "WaT_AC_1.tsv", "WaT_AC_1", "530 KB", "Completed", 1),
    (207, 1, 6, "WaT_AC_2.tsv", "WaT_AC_2", "530 KB", "Completed", 1),
    (208, 1, 6, "WaT_AC_3.tsv", "WaT_AC_3", "530 KB", "Completed", 1),
    (209, 1, 6, "WaT_AC_4.tsv", "WaT_AC_4", "530 KB", "Completed", 1),
    (210, 1, 6, "OpT_AC_1.tsv", "OpT_AC_1", "530 KB", "Completed", 1),
    (211, 1, 6, "OpT_AC_2.tsv", "OpT_AC_2", "530 KB", "Completed", 1),
    (212, 1, 6, "OpT_AC_3.tsv", "OpT_AC_3", "530 KB", "Completed", 1),
    (213, 1, 6, "OpT_AC_4.tsv", "OpT_AC_4", "530 KB", "Completed", 1),
    (214, 1, 6, "OpT_AC_5.tsv", "OpT_AC_5", "530 KB", "Completed", 1),
    (215, 1, 6, "OpT_CA_1.tsv", "OpT_CA_1", "530 KB", "Completed", 1),
    (216, 1, 6, "OpT_CA_2.tsv", "OpT_CA_2", "530 KB", "Completed", 1),
    (217, 1, 6, "OpT_CA_3.tsv", "OpT_CA_3", "530 KB", "Completed", 1),
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
