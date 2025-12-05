import os
import json
from dotenv import load_dotenv

load_dotenv()

OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3307))

SCHEMA_CONFIG_PATH = "config/database_schema.json"


def load_schema_config(path: str = None):
    """Load database schema configuration from JSON file."""
    config_path = path if path else SCHEMA_CONFIG_PATH
    with open(config_path, "r") as f:
        return json.load(f)


def get_database_description():
    """Generate a text description of the database structure."""
    schema = load_schema_config()
    description = f"Database: {schema['database']}\n\n"
    
    for table in schema["tables"]:
        description += f"Table: {table['name']}\n"
        for col in table["columns"]:
            desc = f"  - {col['name']} ({col['type']})"
            if col.get("primary_key"):
                desc += " [PRIMARY KEY]"
            if col.get("unique"):
                desc += " [UNIQUE]"
            if col.get("nullable") is False:
                desc += " [NOT NULL]"
            if col.get("foreign_key"):
                fk = col["foreign_key"]
                desc += f" [FOREIGN KEY -> {fk['table']}.{fk['column']}]"
            description += "\n"
        description += "\n"
    
    return description
