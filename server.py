import os
import argparse
from config import MYSQL_PORT, get_database_description
from mysql_protocol import start_mysql_server
from database import init_database # DB_PATH is no longer a global constant from database.py


def main(db_path: str = "app_db.sqlite"):
    """Initialize and start MySQL protocol server."""
    print("=" * 70)
    print("SQL Proxy - MySQL Protocol Server (SQLite Backend)")
    print("=" * 70)
    
    # Initialize DB if missing
    if not os.path.exists(db_path):
        print(f"\n⚠️  Database file {db_path} not found.")
        print("   Initializing empty database...")
        init_database(db_path) # Pass db_path to init_database
        print("   (Tip: Run 'python generate_data.py --db-path YOUR_DB_PATH' to populate with sample data)")
    
    print(f"\n📊 Configuration:")
    print(f"   MySQL Port: {MYSQL_PORT}")
    print(f"   Backend: SQLite ({db_path})")
    
    # Print schema info
    print(f"\n📋 Database Schema:")
    schema_info = get_database_description()
    for line in schema_info.split('\n')[:15]:
        if line.strip():
            print(f"   {line}")
    
    # Start MySQL server
    print(f"\n🚀 Starting services...")
    print(f"   ✓ MySQL protocol listening on port {MYSQL_PORT}")
    print(f"\n   Connect via MySQL:")
    print(f"     mysql -h localhost -P {MYSQL_PORT} -u root")
    print("=" * 70 + "\n")
    
    # Pass None as LLM since we are using SQLite directly
    start_mysql_server(None, MYSQL_PORT, db_path) # Pass db_path to start_mysql_server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the SQL proxy server.")
    parser.add_argument("--db-path", type=str, default="app_db.sqlite",
                        help="Path to the SQLite database file.")
    args = parser.parse_args()
    main(args.db_path)
