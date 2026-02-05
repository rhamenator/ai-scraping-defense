#!/usr/bin/env python3
"""
AI-Driven Security Testing Script

Uses LLM capabilities to analyze security scan results, identify patterns,
and suggest remediation strategies.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Dict

try:
    import openai
except ImportError:
    print("Warning: openai not available. Install with: pip install openai")
    openai = None

try:
    import anthropic
except ImportError:
    print("Warning: anthropic not available. Install with: pip install anthropic")
    anthropic = None


def read_scan_results(reports_dir: Path) -> Dict[str, str]:
    """Read all security scan results from reports directory."""
    results = {}

    if not reports_dir.exists():
        print(f"Reports directory not found: {reports_dir}")
        return results

    for report_file in reports_dir.rglob("*.txt"):
        try:
            content = report_file.read_text()
            if content.strip():
                results[report_file.name] = content[:10000]  # Limit size
        except Exception as e:
            print(f"Error reading {report_file}: {e}")

    return results


def analyze_with_openai(results: Dict[str, str], api_key: str) -> str:
    """Analyze security results using OpenAI."""
    if not openai:
        return "OpenAI library not available"

    client = openai.OpenAI(api_key=api_key)

    # Summarize results for analysis
    summary = "Security Scan Results:\n\n"
    for filename, content in results.items():
        summary += f"=== {filename} ===\n"
        summary += content[:2000] + "\n\n"  # First 2000 chars of each

    prompt = f"""You are a security expert analyzing automated security scan results.
Review the following security scan outputs and provide:

1. Critical vulnerabilities that need immediate attention
2. Medium priority issues that should be addressed
3. False positives that can likely be ignored
4. Recommended remediation steps for critical issues
5. Overall security posture assessment

Scan Results:
{summary}

Provide a concise, actionable security analysis."""

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {
                    "role": "system",
                    "content": "You are a cybersecurity expert analyzing vulnerability scan results.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.3,
        )

        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing with OpenAI: {str(e)}"


def analyze_with_anthropic(results: Dict[str, str], api_key: str) -> str:
    """Analyze security results using Anthropic Claude."""
    if not anthropic:
        return "Anthropic library not available"

    client = anthropic.Anthropic(api_key=api_key)

    # Summarize results for analysis
    summary = "Security Scan Results:\n\n"
    for filename, content in results.items():
        summary += f"=== {filename} ===\n"
        summary += content[:2000] + "\n\n"

    prompt = f"""Analyze these automated security scan results and provide:

1. Critical vulnerabilities requiring immediate action
2. Medium priority security issues
3. Likely false positives
4. Specific remediation recommendations
5. Security posture rating (1-10)

{summary}

Focus on actionable insights."""

    try:
        response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=2000,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text
    except Exception as e:
        return f"Error analyzing with Anthropic: {str(e)}"


def generate_correlation_analysis(results: Dict[str, str]) -> str:
    """Generate correlation analysis without LLM (fallback)."""
    analysis = "=== AI-Driven Security Correlation Analysis ===\n\n"

    # Track common patterns
    critical_keywords = ["critical", "severe", "high risk", "exploitable"]
    medium_keywords = ["medium", "moderate", "warning"]
    info_keywords = ["info", "informational", "low"]

    critical_count = 0
    medium_count = 0
    info_count = 0

    findings = []

    for filename, content in results.items():
        content_lower = content.lower()

        # Count severity levels
        critical_count += sum(content_lower.count(kw) for kw in critical_keywords)
        medium_count += sum(content_lower.count(kw) for kw in medium_keywords)
        info_count += sum(content_lower.count(kw) for kw in info_keywords)

        # Look for specific vulnerability patterns
        if "sql injection" in content_lower:
            findings.append(f"⚠️  SQL Injection indicators found in {filename}")
        if "xss" in content_lower or "cross-site scripting" in content_lower:
            findings.append(f"⚠️  XSS vulnerabilities found in {filename}")
        if "authentication" in content_lower and "bypass" in content_lower:
            findings.append(f"🚨 Authentication bypass indicators in {filename}")
        if "rce" in content_lower or "remote code execution" in content_lower:
            findings.append(f"🚨 Remote Code Execution risk in {filename}")
        if "path traversal" in content_lower or "directory traversal" in content_lower:
            findings.append(f"⚠️  Path traversal vulnerability in {filename}")

    analysis += "Severity Distribution:\n"
    analysis += f"  Critical/High: {critical_count} occurrences\n"
    analysis += f"  Medium: {medium_count} occurrences\n"
    analysis += f"  Info/Low: {info_count} occurrences\n\n"

    if findings:
        analysis += "Key Findings:\n"
        for finding in findings[:20]:  # Limit to top 20
            analysis += f"  {finding}\n"
    else:
        analysis += "No critical patterns detected in automated scan.\n"

    analysis += "\n"

    # Risk assessment
    total_issues = critical_count + medium_count
    if total_issues > 100:
        risk_level = "HIGH"
    elif total_issues > 50:
        risk_level = "MEDIUM"
    elif total_issues > 10:
        risk_level = "LOW"
    else:
        risk_level = "MINIMAL"

    analysis += f"Overall Risk Level: {risk_level}\n"

    return analysis


def main():
    parser = argparse.ArgumentParser(description="AI-Driven Security Test Analysis")
    parser.add_argument(
        "--reports-dir",
        type=str,
        default="reports",
        help="Directory containing security scan reports",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "local"],
        default="local",
        help="AI provider to use for analysis",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/ai_analysis.txt",
        help="Output file for AI analysis",
    )

    args = parser.parse_args()

    reports_dir = Path(args.reports_dir)
    output_file = Path(args.output)

    print("=== AI-Driven Security Testing ===")
    print(f"Analyzing reports from: {reports_dir}")

    # Read all scan results
    results = read_scan_results(reports_dir)

    if not results:
        print("No scan results found!")
        sys.exit(1)

    print(f"Found {len(results)} report files")

    # Generate analysis
    analysis = ""

    if args.provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("OPENAI_API_KEY environment variable not set")
            sys.exit(1)
        print("Analyzing with OpenAI GPT-4...")
        analysis = analyze_with_openai(results, api_key)

    elif args.provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("ANTHROPIC_API_KEY environment variable not set")
            sys.exit(1)
        print("Analyzing with Anthropic Claude...")
        analysis = analyze_with_anthropic(results, api_key)

    else:  # local
        print("Generating local correlation analysis...")
        analysis = generate_correlation_analysis(results)

    # Save analysis
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(analysis)

    print(f"\nAnalysis saved to: {output_file}")
    print("\n" + "=" * 60)
    print(analysis)
    print("=" * 60)


if __name__ == "__main__":
    main()
