import requests
import json
from typing import Optional
from config import OLLAMA_API_URL, OLLAMA_MODEL, get_database_description


class OllamaLLM:
    """Wrapper for Ollama LLM API."""
    
    def __init__(self, api_url: str = OLLAMA_API_URL, model: str = OLLAMA_MODEL):
        self.api_url = api_url.rstrip("/")
        self.model = model
    
    def generate_sql(self, user_query: str) -> Optional[str]:
        """
        Generate SQL query from natural language using Ollama LLM.
        
        Args:
            user_query: Natural language query from the user
            
        Returns:
            Generated SQL query string or None if error occurs
        """
        db_schema = get_database_description()
        
        dialect = "MySQL"
        
        prompt = f"""You are a {dialect} expert. Based on the following database schema, convert the user's natural language query into a valid {dialect} query.

DATABASE SCHEMA:
{db_schema}

USER QUERY: {user_query}

Generate only the SQL query without any explanation. Return a valid {dialect} statement."""

        try:
            response = requests.post(
                f"{self.api_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3
                },
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            sql_query = result.get("response", "").strip()
            
            return sql_query if sql_query else None
        except requests.exceptions.RequestException as e:
            print(f"Error calling Ollama API: {e}")
            return None

    def generate_results(self, sql_query: str) -> Optional[list]:
        """
        Generate realistic database results for a SQL query using LLM.
        Acts as a database simulator - generates data that matches the schema.
        
        Args:
            sql_query: SQL query to execute (simulated)
            
        Returns:
            List of result rows (dicts) or None if error
        """
        # --- FAST PATH: Bypass LLM for common metadata/connection queries ---
        q_upper = sql_query.upper().strip()
        
        # 1. Connection / Session settings
        if q_upper.startswith("SET NAMES") or q_upper.startswith("SET CHARACTER SET") or q_upper.startswith("SET CHARSET"):
            return []
        if q_upper.startswith("SET AUTOCOMMIT") or q_upper.startswith("SET SQL_MODE") or q_upper.startswith("SET TRANSACTION"):
            return []
        if "SET SESSION" in q_upper or "SET GLOBAL" in q_upper:
             # Rudimentary check, can be expanded
            return []
        
        # 2. SELECT DATABASE()
        if "SELECT DATABASE()" in q_upper:
            db_schema = get_database_description()
            # Extract db name from description string (hacky but works with current config.py)
            # Description format: "Database: <name>\n..."
            import re
            m = re.search(r"Database: (\w+)", db_schema)
            db_name = m.group(1) if m else "app_db"
            return [{"DATABASE()": db_name}]
        
        # 3. Simple SHOW commands (Partial coverage)
        if q_upper == "SHOW DATABASES":
             db_schema = get_database_description()
             import re
             m = re.search(r"Database: (\w+)", db_schema)
             db_name = m.group(1) if m else "app_db"
             return [{"Database": db_name}, {"Database": "information_schema"}]
        
        if q_upper.startswith("SHOW VARIABLES"):
             # Return empty or dummy for variables to avoid LLM latency
             # Ideally we'd parse LIKE '...' but returning [] often suffices for drivers
             return []
        
        # --- END FAST PATH ---
        
        db_schema = get_database_description()
        
        prompt = f"""You are a database simulator. Based on the database schema and SQL query, generate realistic result data as if the query was executed on a real database.

Your ONLY task is to produce a valid JSON array of objects that represents the result set of the SQL query.
DO NOT include any conversational text, explanations, code snippets (like ```json), or any other extraneous information.
Adhere ABSOLUTELY to the following JSON format. 

DATABASE SCHEMA:
{db_schema}

SQL QUERY: {sql_query}

JSON RESULT:
Example format: [{{ "column1": "value1", "column2": "value2" }}, ...] 


If the query would produce no results, return: []
If the query would have syntax errors or is not a SELECT query producing a result set, return: []"""
        
        print(f"[LLM DEBUG] Sending prompt (len={len(prompt)})")
        
        try:
            response = requests.post(
                f"{self.api_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.2
                },
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            response_text = result.get("response", "").strip()
            
            print(f"[LLM DEBUG] Raw Response (len={len(response_text)}): {response_text[:100]}...")
            
            # Extract JSON from response
            try:
                # Clean up potential markdown code blocks
                if "```json" in response_text:
                    response_text = response_text.replace("```json", "").replace("```", "")
                elif "```" in response_text:
                    response_text = response_text.replace("```", "")
                
                response_text = response_text.strip()

                results = json.loads(response_text)
                return results if isinstance(results, list) else []
            except json.JSONDecodeError as e:
                print(f"[LLM DEBUG] Initial JSON Parse Error: {e}")
                
                # Attempt to find JSON array using regex
                import re
                # Look for the first JSON array [...]
                json_match = re.search(r'\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    try:
                        # If multiple JSON arrays are present (e.g. [..] [..]), this regex might grab too much.
                        # Let's try to be non-greedy or just parse what we found.
                        # A better regex for a single balanced JSON array is hard, so let's try to parse.
                        results = json.loads(json_str)
                        return results if isinstance(results, list) else []
                    except json.JSONDecodeError:
                        # If the regex captured multiple arrays like "[...]\n[...]", json.loads fails.
                        # Let's try to find just the first closing bracket corresponding to the first opening one.
                        # Simple heuristic: count brackets
                        count = 0
                        start_idx = response_text.find('[')
                        if start_idx != -1:
                            for i, char in enumerate(response_text[start_idx:], start=start_idx):
                                if char == '[':
                                    count += 1
                                elif char == ']':
                                    count -= 1
                                    if count == 0:
                                        json_str = response_text[start_idx:i+1]
                                        try:
                                            results = json.loads(json_str)
                                            return results if isinstance(results, list) else []
                                        except json.JSONDecodeError:
                                            pass
                                        break
                        
                        print(f"[LLM DEBUG] Failed to parse regex match")
                
                # Fallback to previous logic if regex fails or is too broad
                if '[' in response_text:
                    json_str = response_text[response_text.find('['):response_text.rfind(']')+1]
                    try:
                        results = json.loads(json_str)
                        return results if isinstance(results, list) else []
                    except (json.JSONDecodeError, ValueError) as e_fallback:
                        print(f"[LLM DEBUG] Fallback JSON Parse Error: {e_fallback}")
                        print(f"[LLM DEBUG] Failed JSON text from fallback: {json_str[:200]}...")
                
                return []
        except requests.exceptions.RequestException as e:
            print(f"Error generating results with Ollama: {e}")
            return []

    def is_available(self) -> bool:
        """Check if Ollama service is available."""
        try:
            response = requests.get(f"{self.api_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False