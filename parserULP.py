import os
import sys
import re
from datetime import datetime
from pathlib import Path

def parse_password_file(file_path, search_terms):
    """Parse a password file and extract credentials"""
    entries = []
    current_entry = {}
    key_mappings = {
        'url': 'URL',
        'host': 'URL',
        'user': 'USER',
        'login': 'USER',
        'pass': 'PASS',
        'password': 'PASS'
    }
    found_lines = 0
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            
            # Count lines containing search terms
            if search_terms and any(term.lower() in line.lower() for term in search_terms):
                found_lines += 1
            
            # Skip empty lines and software info lines
            if not line or line.lower().startswith('soft:'):
                # Save completed entry before resetting
                if all(k in current_entry for k in ['URL', 'USER', 'PASS']):
                    entries.append(f"{current_entry['URL']}:{current_entry['USER']}:{current_entry['PASS']}")
                current_entry = {}
                continue
                
            # Parse key-value pairs
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key in key_mappings:
                    current_entry[key_mappings[key]] = value
    
    # Add the last entry if it wasn't added yet
    if all(k in current_entry for k in ['URL', 'USER', 'PASS']):
        entries.append(f"{current_entry['URL']}:{current_entry['USER']}:{current_entry['PASS']}")
    
    return entries, found_lines

def search_password_files(target_folder, search_terms):
    """Recursively search for password files and parse them"""
    all_entries = []
    total_files = 0
    total_matching_lines = 0
    target_files = {'All Passwords.txt', 'passwords.txt'}  # Case-sensitive check
    
    for root, _, files in os.walk(target_folder):
        for file in files:
            if file in target_files:  # Exact match required
                file_path = Path(root) / file
                try:
                    entries, found_lines = parse_password_file(file_path, search_terms)
                    if entries:
                        print(f"🔍 Found {len(entries)} credentials in {file_path}")
                        all_entries.extend(entries)
                        total_files += 1
                        total_matching_lines += found_lines
                except Exception as e:
                    print(f"❌ Error processing {file_path}: {str(e)}")
    
    return all_entries, total_files, total_matching_lines

def main():
    if len(sys.argv) != 2:
        print("Usage: python ulp_parser.py <target_folder>")
        print("Enter search terms (press Enter twice to finish):")
        sys.exit(1)
    
    # Get search terms from STDIN
    search_terms = []
    print("Enter search terms (press Enter twice to finish):")
    while True:
        line = sys.stdin.readline().strip()
        if not line:
            if not search_terms:
                continue
            else:
                break
        search_terms.append(line)
    
    target_folder = sys.argv[1]
    if not os.path.isdir(target_folder):
        print(f"❌ Error: {target_folder} is not a valid directory")
        sys.exit(1)
    
    # Create output directory
    output_dir = "output_ulp_parser"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    output_file = f"{output_dir}/yougotit-{timestamp}.txt"
    
    print(f"\n🚀 Starting search in {target_folder}...")
    entries, total_files, total_matching_lines = search_password_files(target_folder, search_terms)
    
    if entries:
        # Remove duplicates while preserving order
        seen = set()
        unique_entries = [x for x in entries if not (x in seen or seen.add(x))]
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(unique_entries))
        
        print("\n📊 Results Summary:")
        print(f"• Scanned {total_files} password files")
        print(f"• Found {len(unique_entries)} unique URL:USER:PASS entries")
        print(f"• {total_matching_lines} lines matched your search terms")
        print(f"💾 Results saved to {output_file}")
    else:
        print("\n🔎 No credentials found in the specified folder structure.")

if __name__ == "__main__":
    main()