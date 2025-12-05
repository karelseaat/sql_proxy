import sqlite3
import json
import argparse
import requests
import re
from llm import OllamaLLM
from config import load_schema_config
# from database import DB_PATH # DB_PATH is now passed as an argument

def generate_data(schema_config_path=None, db_path: str = "app_db.sqlite"):
    """Generate realistic sample data using LLM and populate the database."""
    llm = OllamaLLM()
    if not llm.is_available():
        print("Error: Ollama is not available. Please start it to generate data.")
        return

    schema = load_schema_config(schema_config_path)
    conn = sqlite3.connect(db_path) # Use passed db_path
    cursor = conn.cursor()
    
    print("Generating sample data...")
    
    # Sort tables to handle dependencies (very basic topological sort)
    # For now, we rely on the order in config, assuming parents come before children.
    # Ideally, we should sort based on foreign keys.
    
    tables = schema["tables"]
    
    for table in tables:
        table_name = table["name"]
        
        # Check if table already has data
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            if count > 0:
                print(f"Skipping table: {table_name} (already has {count} rows)")
                continue
        except sqlite3.OperationalError:
            pass # Should not happen if init_database was run

        print(f"Processing table: {table_name}")
        
        # Get table schema for prompt
        columns = [col["name"] for col in table["columns"] if not col.get("autoincrement")]
        
        # Check for foreign keys to provide context or constraints
        # This is a simple implementation; for strict FKs, we might need to fetch parent IDs.
        # For this prototype, we'll ask the LLM to generate consistent IDs assuming 1-based indexing
        # or we could fetch existing IDs. Let's try to fetch existing parent IDs if any.
        
        fk_constraints = []
        for col in table["columns"]:
            if col.get("foreign_key"):
                fk_table = col["foreign_key"]["table"]
                fk_col = col["foreign_key"]["column"]
                # Fetch available IDs from parent table
                try:
                    cursor.execute(f"SELECT {fk_col} FROM {fk_table} LIMIT 20")
                    parent_ids = [row[0] for row in cursor.fetchall()]
                    fk_constraints.append(f"- Column '{col['name']}' must reference valid '{fk_table}.{fk_col}' values. Available IDs: {parent_ids}")
                except sqlite3.OperationalError:
                    print(f"  Warning: Could not fetch parent IDs for {fk_table} (table might be empty or missing)")

        prompt = f"""You are a test data generator.
Generate 5-10 rows of realistic sample data for the '{table_name}' table.

Columns to populate: {', '.join(columns)}

Constraints & Context:
{chr(10).join(fk_constraints)}

Return strictly a valid JSON array of objects.
Keys MUST match the column names exactly.
Do NOT include columns that are AUTOINCREMENT (like 'id') unless specified.
Values should be realistic (names, dates, emails, descriptions).

JSON format example:
[
  {{"col1": "val1", "col2": 1}},
  {{"col1": "val2", "col2": 2}}
]
"""
        # print(prompt)
        
        # Reuse the generate_results parsing logic which is robust now
        # We construct a fake "SQL query" just to pass to the method if we were using it directly,
        # but here we invoke the raw generation logic.
        # Actually, let's use a dedicated method or just call the API directly to avoid confusion,
        # but since we have the parsing logic in llm.py, let's add a helper there or just duplicate minimal logic.
        
        try:
            response = requests.post(
                f"{llm.api_url}/api/generate",
                json={
                    "model": llm.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7 # Higher temp for variety in data
                },
                timeout=60
            )
            response.raise_for_status()
            result_json = response.json()
            response_text = result_json.get("response", "").strip()
            
            # Parse JSON
            data = []
            # Clean markdown
            if "```json" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "")
            elif "```" in response_text:
                response_text = response_text.replace("```", "")
            response_text = response_text.strip()

            try:
                data = json.loads(response_text)
            except json.JSONDecodeError:
                 # Try regex
                match = re.search(r'\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(0))
                    except:
                        pass
            
            if not data:
                print(f"  Failed to generate/parse data for {table_name}")
                print(f"  Raw response preview: {response_text[:500]}...")
                continue
                
            # Insert data
            inserted_count = 0
            for row in data:
                # Filter keys to only known columns
                valid_row = {k: v for k, v in row.items() if k in columns}
                if not valid_row:
                    continue
                
                placeholders = ", ".join(["?"] * len(valid_row))
                cols = ", ".join(valid_row.keys())
                vals = list(valid_row.values())
                
                sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
                try:
                    cursor.execute(sql, vals)
                    inserted_count += 1
                except sqlite3.Error as e:
                    print(f"  Insert error: {e}")
            
            print(f"  ✓ Inserted {inserted_count} rows into {table_name}")
            conn.commit()
            
        except Exception as e:
            print(f"  Error generating data for {table_name}: {e}")

    conn.close()
    print("Data generation complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate sample data for the SQL proxy database.")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to the schema configuration JSON file (e.g., config/database_schema.json)")
    parser.add_argument("--db-path", type=str, default="app_db.sqlite",
                        help="Path to the SQLite database file.")
    args = parser.parse_args()
    
    generate_data(args.config, args.db_path)
