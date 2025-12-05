#!/usr/bin/env python
"""
Test script for MySQL protocol server.
Verifies that the MySQL protocol handler works correctly.
"""

import socket
import struct
import time
import sys


def test_mysql_connection(host='localhost', port=3307):
    """Test connecting to MySQL protocol server."""
    print(f"Testing MySQL protocol connection to {host}:{port}")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        print("✓ Successfully connected to MySQL server")
        
        data = sock.recv(1024)
        if data:
            print(f"✓ Received handshake packet: {len(data)} bytes")
            if data[0] == 10:
                print("✓ MySQL protocol version 10 detected")
        
        sock.close()
        return True
    
    except ConnectionRefusedError:
        print("✗ Connection refused - is the server running?")
        return False
    except socket.timeout:
        print("✗ Connection timeout")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("SQL Proxy MySQL Protocol Test")
    print("=" * 60)
    
    mysql_ok = test_mysql_connection()
    
    print("\n" + "=" * 60)
    if mysql_ok:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ MySQL protocol not responding")
        sys.exit(1)