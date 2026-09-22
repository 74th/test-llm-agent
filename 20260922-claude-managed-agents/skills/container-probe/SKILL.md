---
name: container-probe
description: Report which container/environment the current session's tools are actually running in. Use this whenever asked to "probe the container", "check where you're running", or "report the environment marker".
---

# Container Probe

When invoked, gather the following facts using the available tools (`bash`,
`read`) and report them back in **exactly** this format, one line per item,
nothing else before or after:

```
CONTAINER_PROBE_MARKER: <contents of /etc/cma-verification-marker, or "MISSING" if the file does not exist>
CONTAINER_PROBE_HOSTNAME: <output of `hostname`>
CONTAINER_PROBE_WORKDIR: <output of `pwd` immediately after `cd /workspace`>
```

Steps:

1. Run `cat /etc/cma-verification-marker`. If the command fails (file not
   found), use the literal string `MISSING` for `CONTAINER_PROBE_MARKER`
   instead of the command's error text.
2. Run `hostname` and use its output verbatim for `CONTAINER_PROBE_HOSTNAME`.
3. Run `cd /workspace && pwd` and use its output verbatim for
   `CONTAINER_PROBE_WORKDIR`.
4. Print the three lines above, in that order, with no extra commentary. Do
   not summarize or explain the values — the caller parses this output
   mechanically.

This lets a human (or the verification driver) distinguish "the skill was
loaded and followed" (fixed three-line format, real marker/hostname/workdir
values) from "the skill was not attached or not read" (the agent answers in
free text, or the marker line is missing).
