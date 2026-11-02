# Local MCP Security Plan & Verification

This document specifies the threat model, security boundaries, and defensive verifications for the Local WebLens MCP system.

## Boundaries and Defenses

1. **SSRF Boundary Enforcement**:
   - `DestinationPolicy.check_ip()` rejects IPv4 loopback (`127.0.0.1`), IPv6 loopback (`::1`, `[::1]`), RFC1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and AWS/GCP cloud link-local metadata endpoints (`169.254.169.254`).
   - `DestinationPolicy.check_hostname()` rejects explicit internal hostnames (`localhost`, `metadata.google.internal`, `instance-data.ec2.internal`, `*.lan`, `*.local`).
   - Rejection occurs before TCP socket initialization.

2. **Filesystem Traversal Boundary**:
   - Cache storage and database paths are normalized and validated against boundary boundaries. Attempts to reference `../../` outside the designated cache namespace raise an error.

3. **Spreadsheet Formula Injection Defense**:
   - Any cell beginning with `=`, `+`, `-`, `@`, `\t`, `\r` is defanged by prepending a single quote (`'`), neutralizing DDE execution in Excel and LibreOffice Calc.
   - Both input user rows and scraped output web values are defanged.

4. **Indirect Prompt Injection Defense**:
   - Web extracts and search snippets are scanned with `scan_injection()`.
   - Instructions attempting system overrides or directive suppression are identified and quarantined.

5. **Token Boundary Containment**:
   - Sentence-level chunker `_sub_split_paragraph()` prevents context explosion on dense web pages without paragraph breaks.
   - Progressive summary truncation enforces the 2,000-token ceiling on multi-hop deep research.

## Test Results
- **Suite**: `weblens-lab/security_lab/run_three_system_security_audit.py`
- **Result**: **26/26 PASSED (100.0%)**

