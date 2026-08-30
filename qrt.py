import json
import re
import sqlite3
def clean_all_ids(cursor, connection):
    print("Cleaning all IDs in the database and resolving duplicates...")
    cursor.execute("PRAGMA foreign_keys = OFF;")
    pattern = re.compile(r'https://openalex.org/([A-Z]\d+)')
    
    def extract_id(val):
        if not val:
            return val
        match = pattern.search(val)
        return match.group(1).upper() if match else str(val).strip().upper()

    
    primary_tables = ['works', 'authors', 'concepts', 'institutions']
    for table in primary_tables:
        cursor.execute(f"SELECT id FROM {table}")
        for row in cursor.fetchall():
            old_id = row[0]
            new_id = extract_id(old_id)
            if new_id != old_id:
                try:
                    cursor.execute(f"UPDATE {table} SET id = ? WHERE id = ?", (new_id, old_id))
                except sqlite3.IntegrityError:
                    # المعرف القصير موجود مسبقاً، نقوم بحذف النسخة المكررة ذات الرابط الطويل
                    cursor.execute(f"DELETE FROM {table} WHERE id = ?", (old_id,))
    
    cursor.execute("SELECT parent_work_id, child_work_id FROM work_references")
    for row in cursor.fetchall():
        old_parent_id, old_child_id = row
        new_parent_id = extract_id(old_parent_id)
        new_child_id = extract_id(old_child_id)
        if new_parent_id != old_parent_id or new_child_id != old_child_id:
            cursor.execute("UPDATE OR IGNORE work_references SET parent_work_id = ?, child_work_id = ? WHERE parent_work_id = ? AND child_work_id = ?", (new_parent_id, new_child_id, old_parent_id, old_child_id))

    cursor.execute("SELECT work_id, author_id, ins_id FROM work_authors")
    for row in cursor.fetchall():
        old_work_id, old_author_id, old_ins_id = row
        new_work_id = extract_id(old_work_id)
        new_author_id = extract_id(old_author_id)
        new_ins_id = extract_id(old_ins_id)
        if new_work_id != old_work_id or new_author_id != old_author_id or new_ins_id != old_ins_id:
            cursor.execute("UPDATE OR IGNORE work_authors SET work_id = ?, author_id = ?, ins_id = ? WHERE work_id = ? AND author_id = ? AND ins_id = ?", (new_work_id, new_author_id, new_ins_id, old_work_id, old_author_id, old_ins_id))

    cursor.execute("SELECT work_id, concept_id, score FROM work_concepts")
    for row in cursor.fetchall():
        old_work_id, old_concept_id, score = row
        new_work_id = extract_id(old_work_id)
        new_concept_id = extract_id(old_concept_id)
        if new_work_id != old_work_id or new_concept_id != old_concept_id:
            cursor.execute("UPDATE OR IGNORE work_concepts SET work_id = ?, concept_id = ? WHERE work_id = ? AND concept_id = ?", (new_work_id, new_concept_id, old_work_id, old_concept_id))

    
    cursor.execute("DELETE FROM work_references WHERE parent_work_id LIKE 'http%' OR child_work_id LIKE 'http%'")
    cursor.execute("DELETE FROM work_authors WHERE work_id LIKE 'http%' OR author_id LIKE 'http%' OR ins_id LIKE 'http%'")
    cursor.execute("DELETE FROM work_concepts WHERE work_id LIKE 'http%' OR concept_id LIKE 'http%'")

    connection.commit()
    cursor.execute("PRAGMA foreign_keys = ON;")
    print("All IDs cleaned successfully and overlapping records removed.")

# for date formate in column publication_date in table works 
def clean_publication_dates(cursor, connection):
    print("Cleaning publication dates in the database...")
    cursor.execute("SELECT id, publication_date FROM works")
    rows = cursor.fetchall()
    update_count = 0
    for row in rows:
        work_id, raw_date = row
        if not raw_date:
            continue
        cleaned_date = raw_date.strip()
        if re.match(r'^\d{4}', cleaned_date):
            cleaned_date = cleaned_date + '-01-01'
        elif re.match(r'^\d{4}-\d{2}$', cleaned_date):
            cleaned_date = cleaned_date + '-01'
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', cleaned_date):
            pass
        else:
            year_match = re.search(r'(\d{4})', cleaned_date)
            if year_match:
                cleaned_date = year_match.group(1) + '-01-01'
            else:
                continue
        if cleaned_date != raw_date:
            cursor.execute("UPDATE works SET publication_date = ? WHERE id = ?", (cleaned_date, work_id))
            update_count += 1
    connection.commit()
    print(f"Publication dates cleaned successfully. Total records updated: {update_count}")
# encode text of abstract column in works from dict to string
def reconstruct_abstracts(cursor, connection):
    print("Reconstructing abstracts in the database...")
    try:
        cursor.execute("ALTER TABLE works ADD COLUMN abstract_text TEXT;")
    except sqlite3.OperationalError:
        pass
    cursor.execute("SELECT id, abstract_index FROM works WHERE abstract_index IS NOT NULL")
    rows = cursor.fetchall()
    update_count = 0
    for row in rows:
        work_id, index_str = row
        try:
            inverted_index = json.loads(index_str)
            if not inverted_index:
                continue
            word_positions=[]
            for word, positions in inverted_index.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort(key=lambda x: x[0])
            reconstructed_text = ' '.join(word for _, word in word_positions)
            cursor.execute("UPDATE works SET abstract_text = ? WHERE id = ?", (reconstructed_text, work_id))
            update_count += 1
        except json.JSONDecodeError:
            continue
    connection.commit()
    print(f"Abstracts reconstructed successfully. Total records updated: {update_count}")
# remove duplicates from all tables
def remove_duplicates(cursor, connection):
    print("Removing duplicates from all tables...")
    cursor.execute("PRAGMA foreign_keys = OFF;")
    # 1. work_references
    cursor.execute("CREATE TABLE work_references_temp (parent_work_id TEXT, child_work_id TEXT, PRIMARY KEY (parent_work_id, child_work_id), FOREIGN KEY (parent_work_id) REFERENCES works(id), FOREIGN KEY (child_work_id) REFERENCES works(id));")
    cursor.execute("INSERT OR IGNORE INTO work_references_temp SELECT DISTINCT parent_work_id, child_work_id FROM work_references;")
    cursor.execute("DROP TABLE work_references;")
    cursor.execute("ALTER TABLE work_references_temp RENAME TO work_references;")

    # 2. work_authors
    cursor.execute("CREATE TABLE work_authors_temp (work_id TEXT, author_id TEXT, ins_id TEXT, FOREIGN KEY (work_id) REFERENCES works(id), FOREIGN KEY (author_id) REFERENCES authors(id), FOREIGN KEY (ins_id) REFERENCES institutions(id));")
    cursor.execute("INSERT OR IGNORE INTO work_authors_temp SELECT DISTINCT work_id, author_id, ins_id FROM work_authors;")
    cursor.execute("DROP TABLE work_authors;")
    cursor.execute("ALTER TABLE work_authors_temp RENAME TO work_authors;")

    # 3. work_concepts
    cursor.execute("CREATE TABLE work_concepts_temp (work_id TEXT, concept_id TEXT, score REAL, PRIMARY KEY (work_id, concept_id), FOREIGN KEY (work_id) REFERENCES works(id), FOREIGN KEY (concept_id) REFERENCES concepts(id));")
    cursor.execute("INSERT OR IGNORE INTO work_concepts_temp SELECT DISTINCT work_id, concept_id, score FROM work_concepts;")
    cursor.execute("DROP TABLE work_concepts;")
    cursor.execute("ALTER TABLE work_concepts_temp RENAME TO work_concepts;")

    cursor.execute("PRAGMA foreign_keys = ON;")
    connection.commit()
    print("Duplicates removed successfully from all tables.")
# dealing with unknown authors' ids 
def handle_unknown_author_ids(cursor, connection):
    print("Handling unknown author IDs in the database safely...")
    cursor.execute("PRAGMA foreign_keys = OFF;")
    
    counter = 1
    def make_new_id(counter):
        while True:
            candidate = f"U{counter:04d}"
            cursor.execute("SELECT 1 FROM authors WHERE id = ?", (candidate,))
            found = cursor.fetchone()
            counter += 1
            if not found:
                return candidate

    cursor.execute("SELECT id, name FROM authors")
    all_rows = cursor.fetchall()
    handled_names = set()
    
    for row_id, row_name in all_rows:
        if row_id != row_name:
            continue
        if row_name in handled_names:
            continue
            
        real_id_found = None
        for other_row_id, other_row_name in all_rows:
            if other_row_name == row_name and other_row_id != row_id and other_row_id != other_row_name:
                real_id_found = other_row_id
                break
                
        if real_id_found:
            final_id = real_id_found
        else:
            final_id = make_new_id(counter)
            
        
        try:
            cursor.execute("UPDATE authors SET id = ? WHERE id = ?", (final_id, row_name))
            cursor.execute("UPDATE OR IGNORE work_authors SET author_id = ? WHERE author_id = ?", (final_id, row_name))
        except sqlite3.IntegrityError:
            
            cursor.execute("DELETE FROM authors WHERE id = ?", (row_name,))
            
        handled_names.add(row_name)
        
    cursor.execute("PRAGMA foreign_keys = ON;")
    connection.commit()
    print("Unknown author IDs handled successfully.")

# B-tree indexing for faster queries
def create_btree_indexes(cursor, connection):
    print("Creating B-tree indexes for faster queries...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts(name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_institutions_name ON institutions(name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_works_date ON works(publication_date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_works_query ON works(search_query);")
    connection.commit()
    print("B-tree indexes created successfully.")
# build bd_schema table 
def build_bd_schema(cursor, connection):
    print("Building bd_scheam table")
    cursor.execute("CREATE TABLE IF NOT EXISTS bd_schema (table_name TEXT , column_name TEXT, data_type TEXT, key_type TEXT);")
    cursor.executescript('''
    INSERT INTO bd_schema (table_name, column_name, data_type, key_type) VALUES
    ('works', 'id', 'TEXT', 'Primary'),
    ('works', 'title', 'TEXT', 'Normal'),
    ('works', 'publication_date', 'TEXT', 'Indexing'),
    ('works', 'doi', 'TEXT', 'Normal'),
    ('works', 'cited_by_count', 'INTEGER' , 'Normal'),
    ('works', 'abstract_index', 'TEXT', 'Normal'),
    ('works', 'search_query', 'TEXT', 'Indexing'),
    ('works', 'abstract_text', 'TEXT', 'Indexing by abstract_index'),
    ('authors', 'id', 'TEXT', 'Primary'),
    ('authors', 'name', 'TEXT' , 'Normal'),
    ('concepts', 'id', 'TEXT', 'Primary'),
    ('concepts', 'name', 'TEXT', 'Indexing'),
    ('concepts', 'level', 'TEXT', 'Normal'),
    ('institutions', 'id', 'TEXT', 'Primary'),
    ('institutions', 'name', 'TEXT', 'Indexing'),
    ('institutions', 'country', 'TEXT', 'Normal'),
    ('institutions', 'region', 'TEXT', 'Normal'),
    ('institutions', 'city', 'TEXT', 'Normal'),
    ('institutions', 'latitude', 'INTEGER', 'Normal'),
    ('institutions', 'longitude', 'INTEGER', 'Normal'),
    ('work_authors', 'work_id', 'TEXT', 'Foreign'),
    ('work_authors', 'author_id', 'TEXT', 'Foreign'),
    ('work_authors','ins_id', 'TEXT', 'Foreign'),
    ('work_references', 'parent_work_id', 'TEXT', 'Foreign'),
    ('work_references', 'child_work_id', 'TEXT', 'Foreign'),
    ('work_concepts', 'work_id', 'TEXT', 'Foreign'),
    ('work_concepts', 'concept_id', 'TEXT', 'Foreign'),
    ('work_concepts', 'score', 'INTEGER', 'Normal')
    ''')
    connection.commit()
    print("bd_schema table built successfully.")

if __name__ == "__main__":
    db_path = "openalex_data.db"
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    try:
        clean_all_ids(cursor, connection)
        clean_publication_dates(cursor, connection)
        reconstruct_abstracts(cursor, connection)
        remove_duplicates(cursor, connection)
        handle_unknown_author_ids(cursor, connection)
        create_btree_indexes(cursor, connection)
        build_bd_schema(cursor, connection)
        
    except Exception as e:
        print(f"An error occurred: {e}")
        connection.rollback()
    finally:
        cursor.close()
        connection.close()

