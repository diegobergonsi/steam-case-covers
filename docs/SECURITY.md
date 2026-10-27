# Security

steamcase runs entirely on your computer. It talks only to Steam's public servers to fetch game artwork, never sends your files anywhere, never asks for a password or API key, and never runs with elevated rights.

If you find a security problem, please report it privately: open the **Security** tab of this repository and choose **Report a vulnerability**. Please don't post details in a public issue first.

Release files are built by GitHub Actions from the tagged source. Each release lists SHA-256 checksums in `SHA256SUMS`, so you can verify what you downloaded.

Each release file also carries signed build provenance: a certificate, signed by GitHub, saying which commit of this repository built that exact file. To check a download (needs the GitHub CLI):

```bash
gh attestation verify SteamCaseCovers-linux --repo diegobergonsi/steam-case-covers
```
