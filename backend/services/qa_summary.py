"""QA Summary Generator service for FORGE AI QA & DevOps module."""

from pathlib import Path
from typing import Union, Dict, Any

from backend.schemas.qa_schema import QAOutput


def generate_qa_summary(
    qa_output: Union[QAOutput, Dict[str, Any]],
    output_path: str = "outputs/qa_summary.txt"
) -> str:
    """Generate plain text QA Summary report and save to output_path."""
    if isinstance(qa_output, QAOutput):
        status = qa_output.status.upper()
        tests_run = qa_output.tests_run
        passed = qa_output.tests_passed
        failed = qa_output.tests_failed
        critical = qa_output.critical_errors
        warnings = qa_output.warnings
        deployment_ready = "YES" if qa_output.deployment_ready else "NO"
    elif isinstance(qa_output, dict):
        status = str(qa_output.get("status", "FAILED")).upper()
        tests_run = qa_output.get("tests_run", 0)
        passed = qa_output.get("tests_passed", 0)
        failed = qa_output.get("tests_failed", 0)
        critical = qa_output.get("critical_errors", 0)
        warnings = qa_output.get("warnings", 0)
        is_ready = qa_output.get("deployment_ready")
        if is_ready is None:
            is_ready = (status == "PASSED" and critical == 0)
        deployment_ready = "YES" if is_ready else "NO"
    else:
        raise ValueError("qa_output must be a QAOutput instance or dict")

    lines = [
        "QA SUMMARY",
        f"Status : {status}",
        f"Tests Run : {tests_run}",
        f"Passed : {passed}",
        f"Failed : {failed}",
        f"Critical : {critical}",
        f"Warnings : {warnings}",
        f"Deployment Ready : {deployment_ready}",
    ]

    summary_text = "\n".join(lines) + "\n"

    # Write summary text to output file
    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(summary_text, encoding="utf-8")

    return summary_text
