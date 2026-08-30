import requests
import json
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects, RequestException
import sqlite3
import time
from conf import get_user_agent

# --- API and Connection Settings ---
print("=== OpenAlex Academic Data Pipeline ===")

# Initial user inputs
search_term = input("Enter the search term for OpenAlex API: ").strip()
start_page = int(input("Enter the starting page number (default 1): ").strip() or "1")
how_many_pages = int(input("Enter the number of pages to fetch: ").strip() or "1")

headers = { 'User-Agent': get_user_agent()}
url = "https://api.openalex.org"
parms = {
    'search': search_term,
    'per-page': 100 # Number of results per page
}

print('Initializing database and connecting to OpenAlex API...')

# --- Database Connection ---
conn = sqlite3.connect('openalex_data.db')
cur = conn.cursor()

# --- Database Schema Setup ---
cur.execute('''
CREATE TABLE IF NOT EXISTS works (
    id TEXT PRIMARY KEY,
    title TEXT,
    publication_date TEXT,
    doi TEXT,
    cited_by_count INTEGER,
    abstract_index TEXT,
    search_query TEXT
)''')

cur.execute('''
CREATE TABLE IF NOT EXISTS authors (
    id TEXT PRIMARY KEY,
    name TEXT
)''')

cur.execute('''
CREATE TABLE IF NOT EXISTS institutions (
    id TEXT PRIMARY KEY,
    name TEXT,
    country TEXT,
    region TEXT,
    city TEXT,
    latitude REAL,
    longitude REAL
)''')

cur.execute('''
CREATE TABLE IF NOT EXISTS concepts (
    id TEXT PRIMARY KEY,
    name TEXT,
    level TEXT
)''')

# --- Junction Tables for Relations and Knowledge Tree ---
cur.execute('''
CREATE TABLE IF NOT EXISTS work_references (
    parent_work_id TEXT,
    child_work_id TEXT,
    PRIMARY KEY (parent_work_id, child_work_id),
    FOREIGN KEY (parent_work_id) REFERENCES works(id),
    FOREIGN KEY (child_work_id) REFERENCES works(id)
)''')

# تم إضافة PRIMARY KEY لمنع تكرار المفاهيم لنفس البحث عند إعادة التشغيل
cur.execute('''
CREATE TABLE IF NOT EXISTS work_concepts (
    work_id TEXT,
    concept_id TEXT,
    score REAL,
    PRIMARY KEY (work_id, concept_id), 
    FOREIGN KEY (work_id) REFERENCES works(id),
    FOREIGN KEY (concept_id) REFERENCES concepts(id)
)''')

cur.execute('''
CREATE TABLE IF NOT EXISTS work_authors (
    work_id TEXT,
    author_id TEXT,
    ins_id TEXT,
    PRIMARY KEY (work_id, author_id, ins_id),
    FOREIGN KEY (work_id) REFERENCES works(id),
    FOREIGN KEY (author_id) REFERENCES authors(id),
    FOREIGN KEY (ins_id) REFERENCES institutions(id)
)''')

count = 0
current_page = start_page  # تعيين نقطة الانطلاق بناءً على إدخال المستخدم

# --- The Interactive Master ETL Loop ---
while True:
    print(f"\nFetching data for page {current_page} (Search: '{search_term}')...")
    parms['page'] = current_page
    
    try:
        # 1. Request data from the API server
        response = requests.get(url + '/works', params=parms, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        works = data.get('results', [])
        if not works:
            print("No more works found on the server for this search.")
            break
            
        # 2. Process each work item individually
        for work in works:
            work_id = work.get('id')
            title = work.get('title')
            publication_date = work.get('publication_date')
            doi = work.get('doi')
            cited_by_count = work.get('cited_by_count', 0)
            
            # Save abstract inverted index as JSON string for later parsing
            abstract_inverted_index = work.get('abstract_inverted_index')
            abstract_index_str = json.dumps(abstract_inverted_index) if abstract_inverted_index else None
            
            # Save basic work data including citations, abstract index, and the search query tag
            cur.execute('''
                INSERT OR IGNORE INTO works (id, title, publication_date, doi, cited_by_count, abstract_index, search_query) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (work_id, title, publication_date, doi, cited_by_count, abstract_index_str, search_term))
            
            # 3. Extract and save authors and institutions
            for authorship in work.get('authorships', []):
                author_info = authorship.get('author')
                if author_info:
                    author_id = author_info.get('id')
                    author_name = author_info.get('display_name')
                    if not author_id or author_id.strip() == "":
                        author_id = author_name if author_name else "Unknown Author"
                        
                    # Save author
                    cur.execute('''
                        INSERT OR IGNORE INTO authors (id, name) 
                        VALUES (?, ?)
                    ''', (author_id, author_name))
                    
                    # Extract associated institutions
                    for inst in authorship.get('institutions', []):
                        inst_id = inst.get('id')
                        inst_name = inst.get('display_name')
                        country = inst.get('country_code')
                        
                        # Extract geographical data
                        geo = inst.get('geo', {})
                        city = geo.get('city')
                        region = geo.get('region')
                        latitude = geo.get('latitude')
                        longitude = geo.get('longitude')
                        
                        # Save institution
                        cur.execute('''
                            INSERT OR IGNORE INTO institutions 
                            (id, name, country, region, city, latitude, longitude) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (inst_id, inst_name, country, region, city, latitude, longitude))
                        
                        # work_authors table
                        cur.execute('''
                                                INSERT OR IGNORE INTO work_authors (work_id, author_id, ins_id) 
                                                VALUES (?, ?, ?)
                                            ''', (work_id, author_id, inst_id))
            
            # 4. Extract and save physical concepts
            for concept in work.get('concepts', []):
                concept_id = concept.get('id')
                concept_name = concept.get('display_name')
                level = concept.get('level')
                score = concept.get('score')
                
                # Save concept
                cur.execute('''
                    INSERT OR IGNORE INTO concepts (id, name, level) 
                    VALUES (?, ?, ?)
                ''', (concept_id, concept_name, level))
                
                # Link work to concept with score
                cur.execute('''
                    INSERT OR IGNORE INTO work_concepts (work_id, concept_id, score) 
                    VALUES (?, ?, ?)
                ''', (work_id, concept_id, score))

            # 5. Extract references to build the knowledge tree
            for ref_id in work.get('referenced_works', []):
                cur.execute('''
                    INSERT OR IGNORE INTO work_references (parent_work_id, child_work_id) 
                    VALUES (?, ?)
                ''', (ref_id, work_id))

            count += 1
            
        # 6. Batch commit data to disk after finishing the page
        conn.commit()
        print(f"Checkpoint: Page {current_page} processed. Total works stored in database in this run: {count}")
            
        # Check if we have reached the requested number of pages for this batch
        how_many_pages -= 1
        if how_many_pages > 0:
            current_page += 1
            time.sleep(1)
            continue

        # --- Strict Triple-Step Control Flow ---
        print("\n--- Session Batch Complete ---")
        action = input("Type 'next' to continue or 'q' to quit: ").strip().lower()
        
        if action == 'q':
            print("Exiting program safely.")
            break
        elif action == 'next':
            # Step 1: Search term configuration
            term_input = input("Enter search term (type 'continue' for same search or enter a new name): ").strip()
            if term_input.lower() != 'continue' and term_input != "":
                search_term = term_input
                parms['search'] = search_term
                current_page = int(input("Enter starting page for this new search: ").strip() or "1")
            else:
                current_page += 1 # Continue to the next page for the same search term

            # Step 2: Number of pages configuration
            pages_input = input("Enter number of pages to fetch: ").strip()
            how_many_pages = int(pages_input) if pages_input.isdigit() else 1
        else:
            print("Invalid option. Exiting program.")
            break

        # Polite delay to prevent server blocking
        time.sleep(1)

    except ConnectionError:
        print("Error: Failed to connect to the server. Check your internet connection.")
        break
    except Timeout:
        print("Error: The connection request timed out.")
        break
    except TooManyRedirects:
        print("Error: Too many redirects encountered.")
        break
    except RequestException as e:
        print(f"An unexpected error occurred: {e}")
        break

# Close database connection cleanly
conn.close()
print(f"\nProcess finished. Total works processed in this session: {count}")
