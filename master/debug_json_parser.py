#!/usr/bin/env python3
"""
Standalone script to fetch one oldest unsynced priority batch record
and attempt to parse its JSON result field.
"""

import os
import sys
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import DATABASE_URL

def main():
    # Create database connection
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Count total unsynced batches
        count_query = text("""
            SELECT COUNT(*) as total
            FROM priority_batches
            WHERE sync = false
        """)
        
        total_count = db.execute(count_query).scalar()
        
        print("=" * 80)
        print("JSON Validation Report for Unsynced Batches")
        print("=" * 80)
        print(f"Total unsynced batches: {total_count}")
        print()
        
        if total_count == 0:
            print("No unsynced batches found.")
            return
        
        # Fetch all unsynced batches
        query = text("""
            SELECT 
                id,
                website_id,
                url,
                website_url,
                result,
                model,
                sync,
                sample,
                created_at
            FROM priority_batches
            WHERE sync = false
            ORDER BY created_at ASC
        """)
        
        results = db.execute(query).fetchall()
        
        valid_json_count = 0
        invalid_json_count = 0
        invalid_batch_ids = []
        error_types = {}
        
        print("Checking JSON validity for all unsynced batches...")
        print()
        
        for idx, result in enumerate(results, 1):
            batch_id = result.id
            
            # Try to parse JSON with Python
            try:
                parsed_json = json.loads(result.result)
                valid_json_count += 1
                if idx % 100 == 0:
                    print(f"Processed {idx}/{total_count} batches... (Valid: {valid_json_count}, Invalid: {invalid_json_count})")
            except json.JSONDecodeError as e:
                invalid_json_count += 1
                invalid_batch_ids.append(batch_id)
                
                # Track error types
                error_msg = e.msg
                if error_msg not in error_types:
                    error_types[error_msg] = 0
                error_types[error_msg] += 1
                
                if idx % 100 == 0:
                    print(f"Processed {idx}/{total_count} batches... (Valid: {valid_json_count}, Invalid: {invalid_json_count})")
            except Exception as e:
                invalid_json_count += 1
                invalid_batch_ids.append(batch_id)
                error_type = type(e).__name__
                if error_type not in error_types:
                    error_types[error_type] = 0
                error_types[error_type] += 1
        
        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total unsynced batches: {total_count}")
        print(f"✅ Valid JSON: {valid_json_count} ({valid_json_count * 100.0 / total_count:.2f}%)")
        print(f"❌ Invalid JSON: {invalid_json_count} ({invalid_json_count * 100.0 / total_count:.2f}%)")
        print()
        
        # Calculate percentage
        invalid_percentage = (invalid_json_count * 100.0 / total_count) if total_count > 0 else 0
        
        if invalid_json_count > 0:
            print("=" * 80)
            print("Error Types Distribution:")
            print("=" * 80)
            for error_msg, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
                print(f"  {error_msg}: {count}")
            print()
            
            print("=" * 80)
            print(f"Invalid JSON Batch IDs (first 50):")
            print("=" * 80)
            for batch_id in invalid_batch_ids[:50]:
                print(f"  {batch_id}")
            if len(invalid_batch_ids) > 50:
                print(f"  ... and {len(invalid_batch_ids) - 50} more")
            print()
            
            print("=" * 80)
            print("Sample Invalid JSON (first invalid batch):")
            print("=" * 80)
            if invalid_batch_ids:
                sample_query = text("""
                    SELECT id, url, result
                    FROM priority_batches
                    WHERE id = :batch_id
                """)
                sample = db.execute(sample_query, {"batch_id": invalid_batch_ids[0]}).fetchone()
                if sample:
                    print(f"Batch ID: {sample.id}")
                    print(f"URL: {sample.url}")
                    print()
                    print("JSON (first 1000 chars):")
                    print(sample.result[:1000])
                    print("...")
                    print()
                    try:
                        json.loads(sample.result)
                    except json.JSONDecodeError as e:
                        print(f"Error: {e.msg} at line {e.lineno}, column {e.colno}")
            
            # Delete invalid records if they're less than 5% of total
            if invalid_percentage < 5.0 and invalid_json_count > 0:
                print()
                print("=" * 80)
                print("DELETION DECISION")
                print("=" * 80)
                print(f"Invalid JSON percentage: {invalid_percentage:.2f}%")
                print(f"Threshold: 5.00%")
                print(f"Since invalid JSON is less than 5%, deleting {invalid_json_count} invalid records...")
                print()
                
                try:
                    # Delete invalid batch records one by one (more reliable)
                    deleted_count = 0
                    for batch_id in invalid_batch_ids:
                        delete_query = text("DELETE FROM priority_batches WHERE id = :batch_id")
                        result = db.execute(delete_query, {"batch_id": batch_id})
                        deleted_count += result.rowcount
                    
                    db.commit()
                    print(f"✅ Successfully deleted {deleted_count} invalid batch records")
                    print(f"   Deleted batch IDs: {invalid_batch_ids[:20]}{'...' if len(invalid_batch_ids) > 20 else ''}")
                    
                except Exception as delete_error:
                    db.rollback()
                    print(f"❌ Error deleting invalid records: {delete_error}")
                    import traceback
                    traceback.print_exc()
            else:
                if invalid_json_count > 0:
                    print()
                    print("=" * 80)
                    print("DELETION DECISION")
                    print("=" * 80)
                    print(f"Invalid JSON percentage: {invalid_percentage:.2f}%")
                    print(f"Threshold: 5.00%")
                    print(f"⚠️  Invalid JSON is {invalid_percentage:.2f}% which is >= 5%, NOT deleting records")
                    print("   (Only deleting if invalid JSON is less than 5% of total)")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
        engine.dispose()

if __name__ == "__main__":
    main()

