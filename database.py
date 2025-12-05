import sqlite3
import json
import os
import argparse
from config import load_schema_config

def get_sqlite_type(mysql_type):
    """Map MySQL types to SQLite types."""
    type_upper = mysql_type.upper()
    if "INT" in type_upper:
        return "INTEGER"
    elif "CHAR" in type_upper or "TEXT" in type_upper:
        return "TEXT"
    elif "FLOAT" in type_upper or "DOUBLE" in type_upper or "DECIMAL" in type_upper:
        return "REAL"
    elif "BOOL" in type_upper:
        return "INTEGER" # SQLite uses 0/1 for booleans
    elif "DATE" in type_upper or "TIME" in type_upper:
        return "TEXT" # SQLite stores dates as text
    else:
        return "TEXT"

def init_database(db_path: str = "app_db.sqlite", schema_config_path: str = None):
    """Initialize SQLite database from schema config."""
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")
    
    schema = load_schema_config(schema_config_path) # Pass schema_config_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"Initializing database: {schema['database']} ({db_path})")
    
    for table in schema["tables"]:
        columns_def = []
        foreign_keys = []
        
        for col in table["columns"]:
            col_def = f"{col['name']} {get_sqlite_type(col['type'])}"
            
            if col.get("primary_key"):
                col_def += " PRIMARY KEY"
                if col.get("autoincrement"):
                    col_def += " AUTOINCREMENT"
            
            if col.get("nullable") is False:
                col_def += " NOT NULL"
            
            if col.get("unique"):
                col_def += " UNIQUE"
            
            if col.get("default") is not None:
                default_val = col['default']
                if default_val == "CURRENT_TIMESTAMP":
                    col_def += " DEFAULT CURRENT_TIMESTAMP"
                elif isinstance(default_val, str):
                    col_def += f" DEFAULT {default_val}"
                else:
                    col_def += f" DEFAULT {default_val}"
            
            columns_def.append(col_def)
            
            if col.get("foreign_key"):
                fk = col["foreign_key"]
                foreign_keys.append(
                    f"FOREIGN KEY ({col['name']}) REFERENCES {fk['table']} ({fk['column']})"
                )
        
        create_stmt = f"CREATE TABLE {table['name']} (\n  "
        create_stmt += ",\n  ".join(columns_def)
        if foreign_keys:
            create_stmt += ",\n  " + ",\n  ".join(foreign_keys)
        create_stmt += "\n);"
        
        print(f"Creating table: {table['name']}")
        # print(create_stmt)
        cursor.execute(create_stmt)
    
    conn.commit()
    conn.close()
    print("Database initialization complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize SQLite database schema.")
    parser.add_argument("--db-path", type=str, default="app_db.sqlite",
                        help="Path to the SQLite database file.")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to the schema configuration JSON file (e.g., config/database_schema.json)")
    args = parser.parse_args()
    init_database(args.db_path, args.config)
