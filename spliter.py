from datetime import datetime

# Nama-nama file
tanggal = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
output_file = f"results_output/valid/OUTPUT-{tanggal}.txt"
invalid_file = f"results_output/invalid/INVALID-{tanggal}.txt"

# Baca file input
with open('ULP.txt', 'r') as ulps:
    list_ulp = [ulp.strip() for ulp in ulps.readlines() if ulp.strip()]

# Simpan jumlah awal
jumlah_awal = len(list_ulp)

# Set untuk hasil unik dan list untuk invalid
result_set = set()
invalid_lines = []

def split_ulp(ulp):
    ulp = ulp.replace('https://', '').replace('http://', '').replace(' ', ':').replace('|', ':')
    parts = ulp.split(':')

    uname, pw = None, None

    try:
        if '@' in parts[0]:
            uname = parts[0]
            pw = parts[1]
        elif len(parts) == 3:
            uname = parts[1]
            pw = parts[2]
        elif len(parts) == 4:
            uname = parts[2]
            pw = parts[3]

        if uname and pw:
            result_set.add(f"{uname}:{pw}")
        else:
            raise ValueError("Format tidak dikenali")

    except Exception as e:
        invalid_lines.append(f"{ulp} --> Error: {e}")

if __name__ == '__main__':
    for ulp in list_ulp:
        split_ulp(ulp)

    # Tulis hasil valid ke file
    with open(output_file, 'w') as out:
        for item in sorted(result_set):
            out.write(item + "\n")

    # Tulis yang invalid ke file terpisah
    if invalid_lines:
        with open(invalid_file, 'w') as inv:
            for line in invalid_lines:
                inv.write(line + "\n")

    # Info ringkasan
    print("==== RINGKASAN ====")
    print(f"Total baris input     : {jumlah_awal}")
    print(f"Baris valid (unik)    : {len(result_set)}")
    print(f"Baris tidak valid     : {len(invalid_lines)}")
    print(f"Hasil disimpan di     : {output_file}")
    if invalid_lines:
        print(f"Baris error disimpan di: {invalid_file}")