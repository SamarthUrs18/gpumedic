# Security

Please don't open a public issue for a security problem. Report it privately instead:
**[Security → Report a vulnerability](https://github.com/SamarthUrs18/gpumedic/security/advisories/new)**
on this repository. Only the maintainers can see it, and it'll get an answer within a few days.
Give it time to be fixed before disclosing.

## What's worth reporting

gpumedic runs on GPU servers, often as root from a scheduler's health check, so these matter:

- anything that makes gpumedic **write, delete or change** something outside the folder `capture`
  is told to use
- a crafted snapshot or capture (`--replay`) that leads to **code execution** or reads files it
  shouldn't
- a capture that **leaks more than it says it does** — secrets, environment variables, other users'
  processes
- anything that makes gpumedic **send data over the network** (it never should)

## Supported versions

Fixes go into the latest release. gpumedic is pre-1.0, so there are no long-term branches yet.
