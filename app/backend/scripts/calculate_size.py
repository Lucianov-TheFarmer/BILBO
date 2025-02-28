import os
import sys

def calculate_size(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}", file=sys.stderr)
        return None
    size_bytes = os.path.getsize(file_path)
    size_mb = size_bytes / (1024 * 1024)
    size_gb = size_bytes / (1024 * 1024 * 1024)
    if size_gb >= 1:
        return f"{size_gb:.2f} GB"
    else:
        return f"{size_mb:.2f} MB"

if __name__ == "__main__":
    sra_code = sys.argv[1]
    user_id = sys.argv[2]
    file_1_path = f"../users/{user_id}/samples/{sra_code}/{sra_code}_1.fastq"
    file_2_path = f"../users/{user_id}/samples/{sra_code}/{sra_code}_2.fastq"
    
    size_1 = calculate_size(file_1_path)
    size_2 = calculate_size(file_2_path)
    
    if size_1 is None or size_2 is None:
        print("Error calculating size", file=sys.stderr)
        sys.exit(1)
    
    print(f"{size_1},{size_2}")