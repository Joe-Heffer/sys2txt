# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

## Reporting a Vulnerability

We take the security of sys2txt seriously. If you discover a security vulnerability, please follow these steps:

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

1. **GitHub Security Advisories** (preferred):
   - Go to https://github.com/Joe-Heffer/sys2txt/security/advisories/new
   - Fill out the security advisory form with details

2. **Email**:
   - Send details to jheffer@gmail.com
   - Use the subject line: "SECURITY: [Brief Description]"

### What to Include

When reporting a vulnerability, please include:

- Type of vulnerability (e.g., code injection, command injection, arbitrary file access)
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if available)
- Impact of the vulnerability, including how an attacker might exploit it

### What to Expect

- **Acknowledgment**: We will acknowledge receipt of your vulnerability report within 48 hours
- **Updates**: We will send regular updates about our progress (at least every 5 business days)
- **Timeline**: We aim to address critical vulnerabilities within 30 days
- **Credit**: If you wish, we will credit you in the security advisory and release notes

### Disclosure Policy

- We request that you give us reasonable time to address the vulnerability before any public disclosure
- We will coordinate with you on the disclosure timeline
- We will publicly acknowledge your responsible disclosure (unless you prefer to remain anonymous)

## Security Considerations

### System Audio Recording

sys2txt records system audio, which may capture sensitive information:

- **Microphone Access**: The tool can record any audio playing through your system
- **Privacy**: Be aware that recordings may contain private conversations, credentials read aloud, or other sensitive audio
- **File Permissions**: Recorded audio files are saved with default file permissions - ensure appropriate access controls

### Command Injection Risks

The tool uses system commands (`ffmpeg`, `pactl`):

- **Source Names**: PulseAudio source names are passed to `ffmpeg` - only use trusted source names
- **File Paths**: User-provided file paths are used in system commands - validate paths before use
- **Environment**: Run the tool in a controlled environment if processing untrusted input

### Dependencies

sys2txt depends on external packages:

- **faster-whisper**: Transcription engine (optional)
- **openai-whisper**: Fallback transcription engine
- **System commands**: `ffmpeg`, `pactl`

We recommend:
- Keeping dependencies up to date
- Using virtual environments to isolate dependencies
- Reviewing dependency security advisories regularly

### Best Practices

When using sys2txt:

1. **Permissions**: Run with minimal required permissions
2. **File Storage**: Store recordings and transcripts in secure locations with appropriate permissions
3. **Cleanup**: Delete sensitive audio files and transcripts when no longer needed
4. **Network**: Be aware that Whisper models may be downloaded from the internet on first use
5. **GPU Access**: When using CUDA acceleration, ensure proper GPU access controls

## Security Updates

Security updates will be released as:
- Patch versions (e.g., 0.1.1 → 0.1.2)
- Post-releases for urgent fixes (e.g., 0.1.1.post1)

Subscribe to release notifications:
- Watch the repository: https://github.com/Joe-Heffer/sys2txt
- Enable notifications for security advisories

## Known Security Limitations

1. **No Input Sanitization**: File paths and source names from users are not extensively sanitized
2. **Temporary Files**: Audio segments in live mode use predictable temporary file names
3. **No Encryption**: Audio files and transcripts are stored unencrypted
4. **System Dependencies**: Security depends on system-installed `ffmpeg` and `pactl` versions

## Related Security Documentation

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [FFmpeg Security](https://ffmpeg.org/security.html)

## Questions?

If you have questions about this security policy, please open a discussion at:
https://github.com/Joe-Heffer/sys2txt/discussions
