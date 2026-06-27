-- ============================================
-- SQL Queries to Check Priority Batches Data
-- ============================================

-- 1. Overall Statistics
SELECT 
    COUNT(*) as total_batches,
    COUNT(*) FILTER (WHERE sync = true) as synced_count,
    COUNT(*) FILTER (WHERE sync = false) as unsynced_count,
    COUNT(*) FILTER (WHERE sample = true) as sample_count,
    MIN(created_at) as oldest_batch,
    MAX(created_at) as newest_batch
FROM priority_batches;

-- 2. Count by Sync Status
SELECT 
    sync,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM priority_batches), 2) as percentage
FROM priority_batches
GROUP BY sync
ORDER BY sync;

-- 3. Find Batches with Potentially Invalid JSON
-- (Contains control characters, null bytes, or invalid escape sequences)
SELECT 
    id,
    website_id,
    url,
    model,
    sync,
    created_at,
    LENGTH(result) as result_length,
    -- Check for null bytes
    CASE WHEN result LIKE '%' || CHR(0) || '%' THEN 'Has null bytes' ELSE '' END as has_null_bytes,
    -- Check for control characters (basic check)
    CASE WHEN result ~ '[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]' THEN 'Has control chars' ELSE '' END as has_control_chars
FROM priority_batches
WHERE 
    result LIKE '%' || CHR(0) || '%'
    OR result ~ '[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]'
    OR result LIKE '%\\%' ESCAPE '\'
ORDER BY created_at DESC
LIMIT 50;

-- 3a. View Full Result Content for Specific Batch IDs (for debugging)
-- Replace the IDs with the ones you found
SELECT 
    id,
    website_id,
    url,
    model,
    sync,
    created_at,
    result as full_result,
    LENGTH(result) as result_length
FROM priority_batches
WHERE id IN (39687, 39686)  -- Replace with your batch IDs
ORDER BY id;

-- 4. Sample Unsynced Batches (Oldest First)
SELECT 
    id,
    website_id,
    url,
    website_url,
    model,
    sync,
    sample,
    created_at,
    LENGTH(result) as result_length,
    LEFT(result, 200) as result_preview
FROM priority_batches
WHERE sync = false
ORDER BY created_at ASC
LIMIT 20;

-- 5. Check for Specific JSON Parsing Issues
-- Find batches with unquoted property names (common error)
SELECT 
    id,
    url,
    model,
    sync,
    created_at,
    -- Look for patterns like: property_name: instead of "property_name":
    CASE 
        WHEN result ~ '[a-zA-Z_][a-zA-Z0-9_]*\s*:' THEN 'Possible unquoted keys'
        ELSE ''
    END as issue_type
FROM priority_batches
WHERE sync = false
    AND result ~ '[a-zA-Z_][a-zA-Z0-9_]*\s*:'
LIMIT 50;

-- 6. Find Batches with Trailing Commas (common JSON error)
SELECT 
    id,
    url,
    model,
    sync,
    created_at,
    -- Look for trailing commas before } or ]
    CASE 
        WHEN result ~ ',\s*[}\]](?!\s*[,:])' THEN 'Has trailing comma'
        ELSE ''
    END as issue_type
FROM priority_batches
WHERE sync = false
    AND result ~ ',\s*[}\]](?!\s*[,:])'
LIMIT 50;

-- 7. Distribution by Model
SELECT 
    model,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE sync = true) as synced,
    COUNT(*) FILTER (WHERE sync = false) as unsynced,
    ROUND(COUNT(*) FILTER (WHERE sync = true) * 100.0 / COUNT(*), 2) as sync_percentage
FROM priority_batches
GROUP BY model
ORDER BY total DESC;

-- 8. Recent Batches (Last 100)
SELECT 
    id,
    website_id,
    url,
    model,
    sync,
    sample,
    created_at,
    LENGTH(result) as result_length
FROM priority_batches
ORDER BY created_at DESC
LIMIT 100;

-- 9. Find Batches with Very Long Results (might indicate issues)
SELECT 
    id,
    website_id,
    url,
    model,
    sync,
    created_at,
    LENGTH(result) as result_length,
    LEFT(result, 500) as result_preview
FROM priority_batches
WHERE LENGTH(result) > 10000
ORDER BY LENGTH(result) DESC
LIMIT 20;

-- 10. Count Batches by Website
SELECT 
    w.id as website_id,
    w.name as website_name,
    w.url as website_url,
    COUNT(pb.id) as total_batches,
    COUNT(pb.id) FILTER (WHERE pb.sync = true) as synced_batches,
    COUNT(pb.id) FILTER (WHERE pb.sync = false) as unsynced_batches
FROM priority_batches pb
JOIN websites w ON pb.website_id = w.id
GROUP BY w.id, w.name, w.url
ORDER BY total_batches DESC
LIMIT 20;

-- 11. Find Batches with Invalid Escape Sequences
SELECT 
    id,
    url,
    model,
    sync,
    created_at,
    -- Look for invalid escape sequences (not \", \\, \/, \b, \f, \n, \r, \t, \uXXXX)
    CASE 
        WHEN result ~ '\\[^"\\/bfnrtu0-9a-fA-F]' THEN 'Invalid escape sequence'
        ELSE ''
    END as issue_type
FROM priority_batches
WHERE sync = false
    AND result ~ '\\[^"\\/bfnrtu0-9a-fA-F]'
LIMIT 50;

-- 12. Test JSON Validity (PostgreSQL 12+)
-- This attempts to parse JSON and shows which ones fail
SELECT 
    id,
    url,
    model,
    sync,
    created_at,
    CASE 
        WHEN result::json IS NULL THEN 'Invalid JSON'
        ELSE 'Valid JSON'
    END as json_status
FROM priority_batches
WHERE sync = false
LIMIT 100;

-- 13. Get Sample of Problematic Batches (for debugging)
SELECT 
    id,
    website_id,
    url,
    model,
    sync,
    created_at,
    -- Show first 500 chars of result
    SUBSTRING(result, 1, 500) as result_sample,
    -- Count occurrences of common issues
    (LENGTH(result) - LENGTH(REPLACE(result, CHR(0), ''))) as null_byte_count,
    (LENGTH(result) - LENGTH(REPLACE(result, '\', ''))) as backslash_count
FROM priority_batches
WHERE sync = false
ORDER BY created_at ASC
LIMIT 10;

-- 14. View Full Result for Specific Batch IDs (Copy-Paste Ready)
-- Usage: Replace the IDs in the WHERE clause with your batch IDs
SELECT 
    id,
    url,
    model,
    sync,
    created_at,
    result
FROM priority_batches
WHERE id IN (39687, 39686)  -- Replace with your batch IDs
ORDER BY id;

-- 15. Try to Parse JSON and Show Error Details
-- This will show which batches fail JSON parsing
SELECT 
    id,
    url,
    model,
    sync,
    created_at,
    CASE 
        WHEN result::json IS NULL THEN 'Invalid JSON'
        ELSE 'Valid JSON'
    END as json_status,
    -- Show first 300 chars to see the issue
    LEFT(result, 300) as result_preview
FROM priority_batches
WHERE id IN (39687, 39686)  -- Replace with your batch IDs
ORDER BY id;

-- 16. Test JSON Parsing with Error Details (PostgreSQL 12+)
-- This will attempt to parse and show the error if it fails
SELECT 
    id,
    url,
    model,
    sync,
    created_at,
    CASE 
        WHEN (SELECT result::json FROM priority_batches WHERE id = pb.id) IS NULL THEN 'Invalid JSON'
        ELSE 'Valid JSON'
    END as json_status
FROM priority_batches pb
WHERE id IN (39687, 39686)
ORDER BY id;

-- 17. Find Hidden Control Characters (Hex View)
-- This shows the actual byte values that might be causing issues
SELECT 
    id,
    url,
    -- Convert to hex to see hidden characters
    ENCODE(result::bytea, 'hex') as result_hex,
    -- Find positions of problematic characters
    POSITION(CHR(0) IN result) as null_byte_pos,
    POSITION(CHR(1) IN result) as ctrl_char_1_pos,
    POSITION(CHR(2) IN result) as ctrl_char_2_pos,
    -- Count newlines
    (LENGTH(result) - LENGTH(REPLACE(result, CHR(10), ''))) as newline_count,
    -- Count carriage returns
    (LENGTH(result) - LENGTH(REPLACE(result, CHR(13), ''))) as cr_count
FROM priority_batches
WHERE id IN (39687, 39686)
ORDER BY id;

