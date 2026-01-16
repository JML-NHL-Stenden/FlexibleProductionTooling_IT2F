#!/usr/bin/env python3
"""Debug script to check stored Arkite unit credentials in the database"""

import os
import psycopg2
import psycopg2.extras

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "odoo")
DB_USER = os.getenv("DB_USER", "odoo")
DB_PASS = os.getenv("DB_PASS", "odoo")

def main():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Check units
        print("\n=== ARKITE UNITS ===")
        cursor.execute("""
            SELECT id, name, unit_id, api_base, api_key, active
            FROM product_module_arkite_unit
            WHERE active = true
        """)
        units = cursor.fetchall()
        for u in units:
            print(f"\nID: {u['id']}")
            print(f"  Name: {u['name']}")
            print(f"  Unit ID: '{u['unit_id']}' (len: {len(u['unit_id']) if u['unit_id'] else 0})")
            print(f"  API Base: '{u['api_base']}'")
            print(f"  API Key: '{u['api_key']}' (len: {len(u['api_key']) if u['api_key'] else 0})")
            print(f"  Active: {u['active']}")
        
        # Check projects linked to units
        print("\n=== PROJECTS WITH LINKED UNITS ===")
        cursor.execute("""
            SELECT 
                p.id,
                p.name as project_name,
                u.name as unit_name,
                u.unit_id,
                u.api_base,
                u.api_key
            FROM product_module_project p
            INNER JOIN product_module_arkite_unit u ON p.arkite_unit_id = u.id
            WHERE u.active = true
        """)
        projects = cursor.fetchall()
        for p in projects:
            print(f"\nProject: {p['project_name']} (ID: {p['id']})")
            print(f"  Unit: {p['unit_name']}")
            print(f"  Unit ID: '{p['unit_id']}' (len: {len(p['unit_id']) if p['unit_id'] else 0})")
            print(f"  API Base: '{p['api_base']}'")
            print(f"  API Key: '{p['api_key']}' (len: {len(p['api_key']) if p['api_key'] else 0})")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    main()
