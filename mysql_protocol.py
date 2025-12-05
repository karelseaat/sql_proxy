import struct
import threading
import socket
import sqlite3
# from database import DB_PATH # Removed global DB_PATH


class MySQLProtocolHandler:
    """Implements MySQL wire protocol for client connections."""
    
    PROTOCOL_VERSION = 10
    
    # Capability Flags
    CLIENT_LONG_PASSWORD = 1
    CLIENT_FOUND_ROWS = 2
    CLIENT_LONG_FLAG = 4
    CLIENT_CONNECT_WITH_DB = 8
    CLIENT_ODBC = 64
    CLIENT_LOCAL_FILES = 128
    CLIENT_IGNORE_SPACE = 256
    CLIENT_PROTOCOL_41 = 512
    CLIENT_INTERACTIVE = 1024
    CLIENT_SSL = 2048
    CLIENT_IGNORE_SIGPIPE = 4096
    CLIENT_TRANSACTIONS = 8192
    CLIENT_RESERVED = 16384
    CLIENT_SECURE_CONNECTION = 32768
    CLIENT_MULTI_STATEMENTS = 65536
    CLIENT_MULTI_RESULTS = 131072
    CLIENT_PS_MULTI_RESULTS = 262144
    CLIENT_PLUGIN_AUTH = 524288
    CLIENT_CONNECT_ATTRS = 1048576
    CLIENT_PLUGIN_AUTH_LENENC_CLIENT_DATA = 2097152
    CLIENT_CAN_HANDLE_EXPIRED_PASSWORDS = 4194304
    CLIENT_SESSION_TRACK = 8388608
    CLIENT_DEPRECATE_EOF = 16777216
    
    def __init__(self, llm=None, db_path: str = "app_db.sqlite"):
        # llm param is kept for compatibility but unused
        self.conn = None
        self.addr = None
        self.salt = b'\x21\x32\x35\x34\x5f\x30\x2a\x3b\x1c\x3d\x2e\x1f\x5a\x7b\x4c\x3d\x5e\x2f\x60\x00' # 20 random bytes + null terminator
        self.db_conn = None
        self.db_path = db_path # Store db_path
    
    def handle_client(self, conn, addr):
        """Handle incoming MySQL protocol connection."""
        self.conn = conn
        self.addr = addr
        print(f"[MySQL] Client connected from {addr}")
        
        try:
            self._send_handshake()
            self._handle_auth()
            
            # Connect to SQLite DB for this session
            self.db_conn = sqlite3.connect(self.db_path)
            
            self._command_loop()
        except Exception as e:
            print(f"[MySQL Handler Error] {e}")
        finally:
            if self.db_conn:
                self.db_conn.close()
            conn.close()
            print(f"[MySQL] Client disconnected from {addr}")
    
    def _send_handshake(self):
        """Send MySQL handshake packet."""
        print("[DEBUG] Sending HandshakeV10 packet...")
        # Server Capabilities
        capabilities = (
            self.CLIENT_LONG_PASSWORD |
            self.CLIENT_FOUND_ROWS |
            self.CLIENT_LONG_FLAG |
            self.CLIENT_CONNECT_WITH_DB |
            self.CLIENT_PROTOCOL_41 |
            self.CLIENT_TRANSACTIONS |
            self.CLIENT_SECURE_CONNECTION |
            self.CLIENT_PLUGIN_AUTH
        )
        
        handshake = b''
        handshake += bytes([self.PROTOCOL_VERSION])
        handshake += b'8.0.0\x00'                         # Server Version
        handshake += struct.pack('<I', 1)                 # Thread ID
        handshake += self.salt[:8]                        # Auth Plugin Data Part 1
        handshake += b'\x00'                              # Filter
        
        # Capabilities (Lower 2 bytes)
        handshake += struct.pack('<H', capabilities & 0xFFFF)
        
        handshake += bytes([33])                          # Character Set (33 = utf8_general_ci)
        handshake += struct.pack('<H', 2)                 # Status Flags (2 = AUTOCOMMIT)
        
        # Capabilities (Upper 2 bytes)
        handshake += struct.pack('<H', (capabilities >> 16) & 0xFFFF)
        
        # Auth Plugin Data Length
        # For Secure Password Authentication
        handshake += bytes([21])                          # Length of salt (20) + 1
        
        handshake += b'\x00' * 10                         # Reserved
        
        # Auth Plugin Data Part 2
        handshake += self.salt[8:]                        # Rest of salt
        
        # Auth Plugin Name
        handshake += b'mysql_native_password\x00'
        
        self._send_packet(handshake, 0)
        print(f"[DEBUG] Handshake sent. Salt: {self.salt.hex()}")
    
    def _handle_auth(self):
        """Handle MySQL authentication."""
        print("[DEBUG] Waiting for auth packet...")
        data = self._recv_packet()
        if data:
            print(f"[DEBUG] Received auth response. Length: {len(data)}")
            self._send_ok_packet()
            print("[DEBUG] Sent OK packet after auth.")
    
    def _command_loop(self):
        """Main command handling loop."""
        print("[DEBUG] Entering command loop...")
        while True:
            try:
                packet = self._recv_packet()
                if not packet:
                    print("[DEBUG] Connection closed by client (empty packet).")
                    break
                
                command_type = packet[0] if packet else 0
                print(f"[DEBUG] Received command: {hex(command_type)}")
                
                if command_type == 0x01:
                    print("[DEBUG] Command: QUIT")
                    self._handle_quit()
                    break
                elif command_type == 0x03:
                    print("[DEBUG] Command: QUERY")
                    self._handle_query(packet[1:])
                elif command_type == 0x0e:
                    print("[DEBUG] Command: RESET_CONNECTION")
                    self._handle_reset_connection()
                elif command_type == 0x0f:
                    print("[DEBUG] Command: INIT_DB")
                    self._handle_init_db(packet[1:])
                else:
                    print(f"[DEBUG] Unknown command: {hex(command_type)}, sending OK")
                    self._send_ok_packet()
            
            except ConnectionResetError:
                print("[DEBUG] Connection reset by peer.")
                break
            except Exception as e:
                print(f"[MySQL Command Error] {e}")
                break
    
    def _handle_query(self, query_data):
        """Handle QUERY command (0x03)."""
        try:
            query_str = query_data.decode('utf-8', errors='ignore').strip()
            print(f"[MySQL Query] {query_str}")
            
            results = self._execute_query_sqlite(query_str)
            
            if results is None:
                # This happens for non-SELECT queries (INSERT/UPDATE) or errors handled internally
                # If it was an error, _execute_query_sqlite usually returns None after sending ERR
                # But if it was a successful INSERT, we should have sent OK.
                pass 
            else:
                self._send_result_set(results)
        
        except Exception as e:
            print(f"[Query Execution Error] {e}")
            self._send_error_packet(1064, str(e)[:80])

    def _handle_system_variables(self, query_str):
        """Handle queries for MySQL system variables."""
        import re
        
        defaults = {
            'auto_increment_increment': 1,
            'character_set_client': 'utf8mb4',
            'character_set_connection': 'utf8mb4',
            'character_set_results': 'utf8mb4',
            'character_set_server': 'utf8mb4',
            'collation_server': 'utf8mb4_general_ci',
            'collation_connection': 'utf8mb4_general_ci',
            'init_connect': '',
            'interactive_timeout': 28800,
            'license': 'GPL',
            'lower_case_table_names': 1,
            'max_allowed_packet': 67108864,
            'net_write_timeout': 60,
            'performance_schema': '0',
            'query_cache_size': 1048576,
            'query_cache_type': 'OFF',
            'sql_mode': 'NO_ENGINE_SUBSTITUTION',
            'system_time_zone': 'UTC',
            'time_zone': 'SYSTEM',
            'tx_isolation': 'REPEATABLE-READ',
            'transaction_isolation': 'REPEATABLE-READ',
            'wait_timeout': 28800,
            'version_comment': 'MySQL Community Server (GPL)',
            'version': '8.0.0'
        }
        
        # Regex to parse: @@[session.|global.]variable [AS alias]
        # Matches: @@var, @@session.var, @@var AS alias
        pattern = re.compile(r"@@(?:session\.|global\.)?([a-zA-Z0-9_]+)(?:\s+AS\s+([a-zA-Z0-9_]+))?", re.IGNORECASE)
        
        matches = pattern.findall(query_str)
        result_row = {}
        
        if not matches:
            # Fallback if regex doesn't match but "@@" was present (unlikely with standard drivers)
            # Just return empty list or basic version
            return [{"@@version": "8.0.0"}]

        for var_name, alias in matches:
            key = alias if alias else f"@@{var_name}"
            value = defaults.get(var_name.lower(), "")
            result_row[key] = value
            
        return [result_row]

    def _execute_query_sqlite(self, query_str):
        """Execute query against SQLite backend."""
        if not self.db_conn:
            return None

        # Strip C-style comments (/* ... */)
        import re
        clean_query = re.sub(r'/\*.*?\*/', '', query_str, flags=re.DOTALL)
        
        # Remove database prefix (app_db. or `app_db`.) from query
        # This is a simple regex, might need refinement for complex queries
        clean_query = re.sub(r'`?app_db`?\.`?([a-zA-Z0-9_]+)`?', r'\1', clean_query, flags=re.IGNORECASE)
        
        q_upper = clean_query.upper().strip()
        
        # Ignore SET/SHOW commands often sent by MySQL clients
        if q_upper.startswith("SET ") or q_upper.startswith("SHOW "):
             # Handle specific SHOW commands if needed
             if "SHOW DATABASES" in q_upper or "SHOW SCHEMAS" in q_upper:
                 return [{"Database": "app_db"}]
             if "SHOW TABLES" in q_upper or "SHOW FULL TABLES" in q_upper:
                 cursor = self.db_conn.cursor()
                 cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                 tables = cursor.fetchall()
                 if "FULL" in q_upper:
                     return [{"Tables_in_app_db": row[0], "Table_type": "BASE TABLE"} for row in tables]
                 return [{"Tables_in_app_db": row[0]} for row in tables]
            
             if "SHOW TABLE STATUS" in q_upper:
                 # Parse LIKE if present
                 target_table = None
                 if "LIKE" in q_upper:
                     import re
                     # Extract 'value' from LIKE 'value'
                     m = re.search(r"LIKE\s+'([^']+)'", query_str, re.IGNORECASE)
                     if m:
                         target_table = m.group(1)
                 
                 cursor = self.db_conn.cursor()
                 if target_table:
                     # Handle sqlite_sequence specifically if requested, or just standard tables
                     # sqlite_sequence is a real table in SQLite if autoincrement is used.
                     cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?", (target_table,))
                 else:
                     cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                     
                 tables = cursor.fetchall()
                 results = []
                 for t in tables:
                     results.append({
                         "Name": t[0],
                         "Engine": "InnoDB",
                         "Version": 10,
                         "Row_format": "Dynamic",
                         "Rows": 0,
                         "Avg_row_length": 0,
                         "Data_length": 0,
                         "Max_data_length": 0,
                         "Index_length": 0,
                         "Data_free": 0,
                         "Auto_increment": 1,
                         "Create_time": None,
                         "Update_time": None,
                         "Check_time": None,
                         "Collation": "utf8mb4_general_ci",
                         "Checksum": None,
                         "Create_options": "",
                         "Comment": ""
                     })
                 return results

             if "SHOW CREATE TABLE" in q_upper:
                 # Extract table name
                 match = re.search(r"SHOW CREATE TABLE\s+`?([a-zA-Z0-9_]+)`?", clean_query, re.IGNORECASE)
                 if match:
                     table_name = match.group(1)
                     cursor = self.db_conn.cursor()
                     cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                     row = cursor.fetchone()
                     if row:
                         return [{"Table": table_name, "Create Table": row[0]}]
                 return []

             # Mock other SHOW commands for DBeaver/JDBC compatibility
             if "SHOW ENGINES" in q_upper:
                 return [{"Engine": "InnoDB", "Support": "DEFAULT", "Comment": "Supports transactions", "Transactions": "YES", "XA": "YES", "Savepoints": "YES"}]
             if "SHOW CHARSET" in q_upper:
                 return [{"Charset": "utf8mb4", "Description": "UTF-8 Unicode", "Default collation": "utf8mb4_general_ci", "Maxlen": 4}]
             if "SHOW COLLATION" in q_upper:
                 return [{"Collation": "utf8mb4_general_ci", "Charset": "utf8mb4", "Id": 45, "Default": "Yes", "Compiled": "Yes", "Sortlen": 1}]
             if "SHOW PLUGINS" in q_upper:
                 return []
             if "SHOW VARIABLES" in q_upper:
                 # Handle "SHOW VARIABLES LIKE '...'"
                 # This is a quick hack. Ideally we'd match the pattern.
                 # For now, return a few common ones or empty if specific one requested (unless we implement logic)
                 if "LOWER_CASE_TABLE_NAMES" in q_upper:
                     return [{"Variable_name": "lower_case_table_names", "Value": "1"}]
                 return []
             
             # For others, return empty result (or OK packet for SET)
             if q_upper.startswith("SET "):
                 self._send_ok_packet()
                 return None
             return [] # Empty result set for unknown SHOW

        # Handle USE command
        if q_upper.startswith("USE "):
            self._send_ok_packet()
            return None

        # Handle SELECT DATABASE()
        if "SELECT DATABASE()" in q_upper:
            return [{"DATABASE()": "app_db"}]
        
        # Mock INFORMATION_SCHEMA queries
        if "INFORMATION_SCHEMA" in q_upper:
            if "STATISTICS" in q_upper:
                return []
            if "SCHEMATA" in q_upper:
                return [{"CATALOG_NAME": "def", "SCHEMA_NAME": "app_db", "DEFAULT_CHARACTER_SET_NAME": "utf8mb4", "DEFAULT_COLLATION_NAME": "utf8mb4_general_ci", "SQL_PATH": None}]
            if "TABLES" in q_upper:
                # If it's the specific size query: SELECT SUM(...) ...
                if "SUM(" in q_upper and "DATA_LENGTH" in q_upper:
                    return [{"SUM((DATA_LENGTH+INDEX_LENGTH))": 1024 * 1024}] # Return dummy size (1MB)
                
                # Otherwise list tables
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                results = []
                for t in tables:
                    results.append({
                        "TABLE_CATALOG": "def",
                        "TABLE_SCHEMA": "app_db",
                        "TABLE_NAME": t[0],
                        "TABLE_TYPE": "BASE TABLE",
                        "ENGINE": "InnoDB",
                        "VERSION": 10,
                        "ROW_FORMAT": "Dynamic",
                        "TABLE_ROWS": 0,
                        "AVG_ROW_LENGTH": 0,
                        "DATA_LENGTH": 0,
                        "MAX_DATA_LENGTH": 0,
                        "INDEX_LENGTH": 0,
                        "DATA_FREE": 0,
                        "AUTO_INCREMENT": 1,
                        "CREATE_TIME": None,
                        "UPDATE_TIME": None,
                        "CHECK_TIME": None,
                        "TABLE_COLLATION": "utf8mb4_general_ci",
                        "CHECKSUM": None,
                        "CREATE_OPTIONS": "",
                        "TABLE_COMMENT": ""
                    })
                return results
            if "COLUMNS" in q_upper:
                # List columns for all tables
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                results = []
                for t in tables:
                    table_name = t[0]
                    try:
                        # Use PRAGMA table_info
                        cursor.execute(f"PRAGMA table_info({table_name})")
                        columns = cursor.fetchall()
                        # cid, name, type, notnull, dflt_value, pk
                        for col in columns:
                            results.append({
                                "TABLE_CATALOG": "def",
                                "TABLE_SCHEMA": "app_db",
                                "TABLE_NAME": table_name,
                                "COLUMN_NAME": col[1],
                                "ORDINAL_POSITION": col[0] + 1,
                                "COLUMN_DEFAULT": col[4],
                                "IS_NULLABLE": "NO" if col[3] else "YES",
                                "DATA_TYPE": col[2] or "TEXT",
                                "CHARACTER_MAXIMUM_LENGTH": 255,
                                "CHARACTER_OCTET_LENGTH": 255,
                                "NUMERIC_PRECISION": None,
                                "NUMERIC_SCALE": None,
                                "DATETIME_PRECISION": None,
                                "CHARACTER_SET_NAME": "utf8mb4",
                                "COLLATION_NAME": "utf8mb4_general_ci",
                                "COLUMN_TYPE": col[2] or "text",
                                "COLUMN_KEY": "PRI" if col[5] else "",
                                "EXTRA": "",
                                "PRIVILEGES": "select,insert,update,references",
                                "COLUMN_COMMENT": "",
                                "GENERATION_EXPRESSION": ""
                            })
                    except:
                        pass
                return results

            if "KEY_COLUMN_USAGE" in q_upper:
                # Mock key usage (Primary Keys)
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                results = []
                for t in tables:
                    table_name = t[0]
                    try:
                        cursor.execute(f"PRAGMA table_info({table_name})")
                        columns = cursor.fetchall()
                        for col in columns:
                            if col[5]: # pk > 0
                                results.append({
                                    "CONSTRAINT_CATALOG": "def",
                                    "CONSTRAINT_SCHEMA": "app_db",
                                    "CONSTRAINT_NAME": "PRIMARY",
                                    "TABLE_CATALOG": "def",
                                    "TABLE_SCHEMA": "app_db",
                                    "TABLE_NAME": table_name,
                                    "COLUMN_NAME": col[1],
                                    "ORDINAL_POSITION": col[0] + 1,
                                    "POSITION_IN_UNIQUE_CONSTRAINT": None,
                                    "REFERENCED_TABLE_SCHEMA": None,
                                    "REFERENCED_TABLE_NAME": None,
                                    "REFERENCED_COLUMN_NAME": None
                                })
                    except:
                        pass
                return results
                
            if "CHECK_CONSTRAINTS" in q_upper:
                # Mock check constraints (return empty for now)
                return []
            
        # Handle System Variables (e.g. @@session.auto_increment_increment)
        if "@@" in q_upper:
            return self._handle_system_variables(clean_query) # Use cleaned query for regex

        try:
            cursor = self.db_conn.cursor()
            cursor.execute(clean_query) # Use cleaned query here
            
            if q_upper.startswith("SELECT"):
                columns = [description[0] for description in cursor.description]
                rows = cursor.fetchall()
                
                # Convert to list of dicts
                results = []
                for row in rows:
                    result_row = {}
                    for i, col in enumerate(columns):
                        result_row[col] = row[i]
                    results.append(result_row)
                return results
            else:
                # For INSERT, UPDATE, DELETE
                self.db_conn.commit()
                self._send_ok_packet()
                return None
                
        except sqlite3.Error as e:
            print(f"[SQLite Error] {e}")
            self._send_error_packet(1064, f"SQLite Error: {e}")
            return None
    
    def _handle_quit(self):
        """Handle QUIT command (0x01)."""
        pass
    
    def _handle_reset_connection(self):
        """Handle RESET_CONNECTION command (0x0e)."""
        self._send_ok_packet()
    
    def _handle_init_db(self, data):
        """Handle INIT_DB command (0x0f)."""
        self._send_ok_packet()
    
    def _send_result_set(self, results):
        """Send result set in MySQL protocol format."""
        if not results:
            self._send_ok_packet()
            return
        
        if isinstance(results, list) and len(results) > 0:
            first_row = results[0]
            
            if isinstance(first_row, dict):
                columns = list(first_row.keys())
            elif isinstance(first_row, (list, tuple)):
                columns = [f"col_{i}" for i in range(len(first_row))]
            else:
                self._send_ok_packet()
                return
            
            self._send_column_count(len(columns))
            self._send_column_definitions(columns)
            self._send_eof_packet()
            
            for row in results:
                if isinstance(row, dict):
                    values = [str(row.get(col, '')) for col in columns]
                elif isinstance(row, (list, tuple)):
                    values = [str(v) for v in row]
                else:
                    values = [str(row)]
                
                self._send_text_row(values)
            
            self._send_eof_packet()
        else:
            self._send_ok_packet()
    
    def _send_column_count(self, count):
        """Send column count packet."""
        packet = self._encode_length_coded_binary(count)
        self._send_packet(packet)
    
    def _send_column_definitions(self, columns):
        """Send column definition packets."""
        for col_name in columns:
            col_packet = b''
            col_packet += self._encode_length_coded_string(b'def')
            col_packet += self._encode_length_coded_string(b'database')
            col_packet += self._encode_length_coded_string(b'table')
            col_packet += self._encode_length_coded_string(b'table')
            col_packet += self._encode_length_coded_string(col_name.encode('utf-8'))
            col_packet += self._encode_length_coded_string(col_name.encode('utf-8'))
            col_packet += bytes([0x0c])
            col_packet += struct.pack('<H', 0x0021)       # Charset 33 (utf8)
            col_packet += struct.pack('<I', 255)          # Column length
            col_packet += bytes([0xfd])                   # Type: MYSQL_TYPE_VAR_STRING
            col_packet += struct.pack('<H', 0)            # Flags
            col_packet += bytes([0x00, 0x00])             # Decimals + Filler
            
            self._send_packet(col_packet)
    
    def _send_text_row(self, values):
        """Send text protocol row packet."""
        packet = b''
        for value in values:
            if value is None or value == 'None':
                packet += b'\xfb'
            else:
                value_bytes = str(value).encode('utf-8')
                packet += self._encode_length_coded_binary(len(value_bytes))
                packet += value_bytes
        
        self._send_packet(packet)
    
    def _send_ok_packet(self):
        """Send OK packet."""
        packet = b'\x00'
        packet += b'\x00\x00'
        packet += struct.pack('<H', 0)
        packet += bytes([0x00, 0x00])
        self._send_packet(packet)
    
    def _send_error_packet(self, error_code, error_message):
        """Send ERR packet."""
        packet = b'\xff'
        packet += struct.pack('<H', error_code)
        packet += b'#28000'
        packet += error_message[:80].encode('utf-8')
        self._send_packet(packet)
    
    def _send_eof_packet(self):
        """Send EOF packet."""
        packet = b'\xfe\x00\x00\x00\x00'
        self._send_packet(packet)
    
    def _encode_length_coded_binary(self, value):
        """Encode length-coded binary format."""
        if value is None:
            return b'\xfb'
        elif value < 251:
            return bytes([value])
        elif value < 65536:
            return b'\xfc' + struct.pack('<H', value)
        elif value < 16777216:
            return b'\xfd' + struct.pack('<I', value)[:3]
        else:
            return b'\xfe' + struct.pack('<Q', value)
    
    def _encode_length_coded_string(self, value):
        """Encode length-coded string."""
        return self._encode_length_coded_binary(len(value)) + value
    
    def _send_packet(self, data, packet_num=None):
        """Send packet with MySQL packet header."""
        if packet_num is None:
            self.packet_num = getattr(self, 'packet_num', 0) + 1
            packet_num = self.packet_num
        
        length = len(data)
        header = struct.pack('<I', length)[:3]
        header += bytes([packet_num & 0xff])
        
        # print(f"[DEBUG] Sent Packet: Len={length}, Seq={packet_num}")
        self.conn.sendall(header + data)
    
    def _recv_packet(self):
        """Receive packet from client."""
        try:
            header = self.conn.recv(4)
            if len(header) < 4:
                return None
            
            length = struct.unpack('<I', header[:3] + b'\x00')[0]
            packet_num = header[3]
            
            # Sync packet number sequence from client
            self.packet_num = packet_num
            
            # print(f"[DEBUG] Recv Packet: Len={length}, Seq={packet_num}")
            
            if length == 0:
                return b''
            
            data = b''
            remaining = length
            while remaining > 0:
                chunk = self.conn.recv(min(remaining, 4096))
                if not chunk:
                    break
                data += chunk
                remaining -= len(chunk)
            
            return data
        
        except Exception as e:
            print(f"[Recv Error] {e}")
            return None


def start_mysql_server(llm, port, db_path: str = "app_db.sqlite"):
    """Start MySQL protocol server on specified port."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(5)
    
    print(f"✓ MySQL protocol listener on port {port}")
    
    while True:
        try:
            conn, addr = server.accept()
            handler = MySQLProtocolHandler(llm, db_path)
            client_thread = threading.Thread(
                target=handler.handle_client,
                args=(conn, addr),
                daemon=True
            )
            client_thread.start()
        except Exception as e:
            print(f"[MySQL Server Error] {e}")