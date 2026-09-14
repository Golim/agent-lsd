# Hacker System Monitor 2

The vulnerable feature is still the regex-backed PID lookup on `/`. The search string is interpolated directly into a shell pipeline similar to:

```sh
ps -eo pid=,args= | grep -E "<pattern>" | grep -v grep | awk '{print $1}'
```

In this second version, the application post-processes command output and only renders integers. That blocks the original direct `printenv FLAG` leak, but it does not remove command injection. The fix is to execute a command that converts the flag to decimal byte values before the output filter sees it.

A reliable payload is:

```sh
^$"; printf %s "$FLAG" | od -An -tu1; echo "
```

This keeps the original `grep -E` mostly quiet with `^$`, runs `printf %s "$FLAG" | od -An -tu1` to print the flag as decimal ASCII bytes, and then absorbs the trailing pipeline with `echo "` so the shell stays syntactically valid.

The response now contains only integers, for example:

```text
85,110,105,84,78,123,49,...
```

Decoding those bytes back to UTF-8 reconstructs the original flag. The service still blocks obvious outbound-network tooling and cleans up spawned processes after each request, so the intended solve path remains short-lived local command execution.
