-- SQL Query to remove comments from result field for batch ID 2336
-- Removes // comments but preserves // in URLs (like http://)

-- First, let's see what it looks like before:
SELECT 
    id,
    url,
    LEFT(result, 500) as result_preview_before
FROM priority_batches
WHERE id = 2336;

-- Update: Remove everything after ", until " or } or ], keeping the comma
-- This removes comments and extra text after quoted values in JSON
-- Example: "product_category": "Clothing",  // comment here
-- Result:  "product_category": "Clothing",

-- Method 1: Remove everything after ", until ", }, or ]
UPDATE priority_batches
SET result = regexp_replace(
    result,
    '(",\s*)[^"}]*?(?=["}\]])',  -- Match ", followed by whitespace, then everything until ", }, or ]
    '\1',                         -- Replace with just ", (keeps the comma)
    'gm'                          -- Global and multiline flags
)
WHERE id = 2336;

-- Method 2: More precise - handles edge cases better
-- Removes everything after ", until ", }, or ], but preserves the comma
UPDATE priority_batches
SET result = regexp_replace(
    result,
    '(",\s*)[^"}]*?(?=["}\]])',  -- ", then whitespace, then any chars until ", }, or ]
    '",',                         -- Replace with just ", (comma preserved)
    'gm'
)
WHERE id = 2336;

-- Method 3: Alternative - removes until ", }, ], or end of line (whichever comes first)
UPDATE priority_batches
SET result = regexp_replace(
    result,
    '(",\s*)[^"}]*?(?=["}\]\n]|$)',  -- ", then whitespace, then chars until ", }, ], newline, or end
    '",',                             -- Replace with just ",
    'gm'
)
WHERE id = 2336;

-- Verify the update:
SELECT 
    id,
    url,
    LEFT(result, 500) as result_preview_after
FROM priority_batches
WHERE id = 2336;

-- Recommended: Method 2 - removes everything after ", until ", }, or ]
UPDATE priority_batches
SET result = regexp_replace(
    result,
    '(",\s*)[^"}]*?(?=["}\]])',  -- ", then whitespace, then any chars until ", }, or ]
    '",',                         -- Replace with just ", (comma preserved)
    'gm'
)
WHERE id = 2336;

-- If you want to update ALL batches with comments after ", (be careful!):
UPDATE priority_batches
SET result = regexp_replace(
    result,
    '(",\s*)[^"}]*?(?=["}\]])',  -- Remove everything after ", until ", }, or ]
    '",',                         -- Keep the comma
    'gm'
)
WHERE result ~ '(",\s*)[^"}]*?(?=["}\]])';  -- Only update rows that have text after ",

