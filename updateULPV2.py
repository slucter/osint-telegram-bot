import re
import sys
import argparse
from datetime import datetime
import random
import string
from elasticsearch import Elasticsearch
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Elasticsearch configuration
ES_HOST = os.getenv('ES_HOST', '')
ES_USERNAME = os.getenv('ES_USERNAME', '')
ES_PASSWORD = os.getenv('ES_PASSWORD', '')
ES_INDEX = os.getenv('ES_INDEX', '')

# Initialize Elasticsearch client
es = Elasticsearch(
    [ES_HOST],
    basic_auth=(ES_USERNAME, ES_PASSWORD),
    verify_certs=False
)

# Regex pattern untuk URL yang lebih akurat
URL_PATTERN = r'(?P<url>(?:https?|android)://[^\s:]+(?::\d+)?(?:/[^\s:]*)?|(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?::\d+)?(?:/[^\s:]*)?)'

def generate_mongo_id(length=15):
    """Generate random alphanumeric string of specified length"""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def push_to_elasticsearch(entry):
    """Push entry to Elasticsearch"""
    try:
        # Prepare document
        doc = {
            'url': entry['url'],
            'username': entry['username'],
            'password': entry['password'],
            'source_file': entry['filename'],
            'line_number': entry['line_number'],
            'timestamp': entry['timestamp'],
            'mongo_id': entry['mongo_id']
        }
        
        # Index document
        response = es.index(
            index=ES_INDEX,
            document=doc
        )
        
        if response['result'] == 'created':
            return True, "Successfully indexed"
        else:
            return False, f"Failed to index: {response['result']}"
            
    except Exception as e:
        return False, f"Error pushing to Elasticsearch: {str(e)}"

def parse_credentials(line, line_number, filename):
    line = line.strip()
    if not line:
        return None

    # Cari semua URL dalam line
    url_matches = list(re.finditer(URL_PATTERN, line))
    if not url_matches:
        return None

    # Ambil URL pertama
    url_match = url_matches[0]
    url = url_match.group('url')
    url_start, url_end = url_match.span()

    # Pisahkan bagian sebelum dan setelah URL
    before_url = line[:url_start]
    after_url = line[url_end:]

    # Case 1: Format URL:USER:PASS
    if url_start == 0 and after_url.startswith(':'):
        parts = after_url[1:].split(':')
        if len(parts) >= 2:
            username = parts[0].strip()
            password = parts[1].strip()
            if username and password:
                return {
                    'url': url,
                    'username': username,
                    'password': password,
                    'line_number': line_number,
                    'filename': filename,
                    'timestamp': datetime.now().isoformat(),
                    'mongo_id': generate_mongo_id()
                }

    # Case 2: Format USER:PASS:URL
    elif url_end == len(line) and before_url.endswith(':'):
        parts = before_url[:-1].split(':')
        if len(parts) >= 2:
            username = parts[-2].strip()
            password = parts[-1].strip()
            if username and password:
                return {
                    'url': url,
                    'username': username,
                    'password': password,
                    'line_number': line_number,
                    'filename': filename,
                    'timestamp': datetime.now().isoformat(),
                    'mongo_id': generate_mongo_id()
                }

    # Case 3: Format campuran atau tidak standar
    else:
        # Coba split seluruh line dengan ':'
        all_parts = line.split(':')
        
        # Cari URL dalam parts
        url_in_parts = None
        for part in all_parts:
            if re.fullmatch(URL_PATTERN, part):
                url_in_parts = part
                break
        
        if url_in_parts:
            url_index = all_parts.index(url_in_parts)
            # Jika URL di awal
            if url_index == 0 and len(all_parts) >= 3:
                username = all_parts[1].strip()
                password = all_parts[2].strip()
            # Jika URL di akhir
            elif url_index == len(all_parts)-1 and len(all_parts) >= 3:
                username = all_parts[-3].strip()
                password = all_parts[-2].strip()
            # Jika URL di tengah
            elif url_index > 0 and url_index < len(all_parts)-1 and len(all_parts) >= 4:
                username = all_parts[url_index-1].strip()
                password = all_parts[url_index+1].strip()
            else:
                return None
            
            if username and password and not any(x in username for x in ['://', '/']) and not any(x in password for x in ['://', '/']):
                return {
                    'url': url_in_parts,
                    'username': username,
                    'password': password,
                    'line_number': line_number,
                    'filename': filename,
                    'timestamp': datetime.now().isoformat(),
                    'mongo_id': generate_mongo_id()
                }

    return None

def print_entry(entry, count, es_status=None):
    print(f"""
================================================================================
📝 Valid Entry #{count}
================================================================================
🔗 URL: {entry['url']}
👤 Username: {entry['username']}
🔑 Password: {entry['password']}
📄 Source: {entry['filename']}
📌 Line: {entry['line_number']}
⏰ Timestamp: {entry['timestamp']}
🆔 Mongo ID: {entry['mongo_id']}
{'✅ Elasticsearch: ' + es_status if es_status else ''}
""")

def main():
    parser = argparse.ArgumentParser(description='Parse URL:USER:PASS from a file')
    parser.add_argument('file', help='Path to the file containing credentials')
    args = parser.parse_args()
    
    try:
        with open(args.file, 'r') as file:
            valid_count = 0
            for line_number, line in enumerate(file, start=1):
                entry = parse_credentials(line, line_number, args.file)
                if entry:
                    valid_count += 1
                    # Push to Elasticsearch
                    success, message = push_to_elasticsearch(entry)
                    print_entry(entry, valid_count, message if success else f"❌ {message}")
                    
            print(f"✅ Total valid entries found: {valid_count}")
            
    except FileNotFoundError:
        print(f"❌ Error: File '{args.file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()