# Antivirus False Positive Notice

`src/tarpit/obfuscation.py` contains JavaScript that fingerprints the browser. Some antivirus programs may detect the generated script as **Generic.HTML.Phishing**.

The fingerprinting code only records user agent details locally and does **not** transmit data to any external server. It helps classify automated bots and is part of the tarpit component.

## **Verify File Integrity**

1. Compute a checksum and compare it to the repository version:
   ```bash
   sha256sum src/tarpit/obfuscation.py
   ```
2. Review the commit history for this file:
   ```bash
   git log --oneline src/tarpit/obfuscation.py
   ```
   This ensures the file matches the official source.

## Reporting a False Positive

If your antivirus flags or quarantines the file, submit a false positive report to the vendor. Provide the file path and explain that it is part of an open-source research project for detecting malicious bots. Most vendors offer online portals or an email address for sample submissions.
