"""
Sub-agent result summarization for the Teiken Claw agent system.

This module provides the SubAgentSummarizer class for merging and
summarizing results from multiple sub-agents into compact,
parent-readable format.

Key Features:
    - SubAgentSummarizer: Summarizes sub-agent results
    - Merge child outputs into parent-readable format
    - Handle mixed success/failure states
    - Extract key findings
    - Generate summary reports
"""

import logging
from typing import Any, Dict, List, Optional

from app.subagents.models import SubAgentResult

logger = logging.getLogger(__name__)


class SubAgentSummarizer:
    """
    Summarizer for sub-agent results.
    
    Provides utilities for merging multiple sub-agent outputs
    into compact parent-readable summaries.
    """
    
    def __init__(self):
        """Initialize the summarizer."""
        logger.debug("SubAgentSummarizer initialized")
    
    def summarize_results(
        self,
        results: List[SubAgentResult],
        include_partials: bool = True,
    ) -> str:
        """
        Merge child outputs into compact parent-readable format.
        
        Args:
            results: List of SubAgentResult from child agents
            include_partials: Whether to include partial/failed results
            
        Returns:
            Summary string for parent agent
        """
        if not results:
            return "No sub-agent results to summarize."
        
        # Categorize results
        successful = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]
        
        lines = []
        
        # Summary header
        lines.append(f"Sub-Agent Results Summary: {len(successful)}/{len(results)} successful")
        
        if successful:
            lines.append("\n## Successful Results")
            for i, result in enumerate(successful, 1):
                content = result.content
                # Truncate long content
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"\n{i}. [{result.metadata.get('purpose', 'Task')}]")
                lines.append(f"   {content}")
        
        if failed and include_partials:
            lines.append("\n## Failed/Partial Results")
            for i, result in enumerate(failed, 1):
                lines.append(f"\n{i}. ERROR ({result.error_code}): {result.error}")
                if result.content:
                    content = result.content
                    if len(content) > 200:
                        content = content[:200] + "..."
                    lines.append(f"   Partial output: {content}")
        
        # Key findings
        findings = self.extract_key_findings(results)
        if findings:
            lines.append("\n## Key Findings")
            for finding in findings:
                lines.append(f"- {finding}")
        
        return "\n".join(lines)
    
    def format_partial_results(
        self,
        results: List[SubAgentResult],
    ) -> str:
        """
        Format partial results from failed/incomplete sub-agents.
        
        Args:
            results: List of SubAgentResult
            
        Returns:
            Formatted string of partial results
        """
        partial = [r for r in results if not r.ok or r.metadata.get("partial")]
        
        if not partial:
            return "All sub-agents completed successfully."
        
        lines = ["Partial Results:"]
        
        for i, result in enumerate(partial, 1):
            status = "FAILED" if not result.ok else "PARTIAL"
            lines.append(f"\n{i}. [{status}]")
            
            if result.error:
                lines.append(f"   Error: {result.error}")
            
            if result.content:
                content = result.content
                if len(content) > 300:
                    content = content[:300] + "..."
                lines.append(f"   Output: {content}")
        
        return "\n".join(lines)
    
    def extract_key_findings(
        self,
        results: List[SubAgentResult],
    ) -> List[str]:
        """
        Extract key findings from sub-agent results.
        
        Analyzes results and extracts important points that
        the parent agent should be aware of.
        
        Args:
            results: List of SubAgentResult
            
        Returns:
            List of key findings as strings
        """
        findings = []
        
        for result in results:
            # Extract from metadata
            if result.metadata:
                # Check for specific findings markers
                if "finding" in result.metadata:
                    findings.append(result.metadata["finding"])
                
                # Check for data extracts
                if "extracted_data" in result.metadata:
                    data = result.metadata["extracted_data"]
                    if isinstance(data, dict):
                        for key, value in data.items():
                            findings.append(f"{key}: {value}")
                
                # Check for errors/warnings
                if not result.ok:
                    findings.append(f"Error in subtask: {result.error}")
                elif result.metadata.get("partial"):
                    findings.append(f"Partial result available for: {result.metadata.get('purpose', 'task')}")
        
        return findings
    
    def generate_summary_report(
        self,
        results: List[SubAgentResult],
        task_descriptions: Optional[List[str]] = None,
    ) -> SubAgentResult:
        """
        Generate a comprehensive summary report.
        
        Creates a single SubAgentResult that summarizes all
        child agent results for the parent.
        
        Args:
            results: List of SubAgentResult from children
            task_descriptions: Optional list of task descriptions
            
        Returns:
            SubAgentResult with comprehensive summary
        """
        if not results:
            return SubAgentResult.error(
                error="No results to summarize",
                error_code="EMPTY_RESULTS",
            )
        
        # Calculate statistics
        total = len(results)
        successful = sum(1 for r in results if r.ok)
        failed = total - successful
        
        # Build report
        lines = []
        lines.append(f"=== Sub-Agent Execution Report ===")
        lines.append(f"Total: {total} | Success: {successful} | Failed: {failed}")
        lines.append("")
        
        # Individual results
        lines.append("## Results")
        
        for i, result in enumerate(results, 1):
            task_desc = task_descriptions[i-1] if task_descriptions and i-1 < len(task_descriptions) else f"Task {i}"
            status = "✓" if result.ok else "✗"
            
            lines.append(f"\n{status} {task_desc}")
            
            if result.ok:
                content = result.content
                # Truncate to reasonable length
                if len(content) > 1000:
                    content = content[:1000] + "\n...[truncated]"
                lines.append(content)
            else:
                lines.append(f"ERROR ({result.error_code}): {result.error}")
        
        # Findings
        findings = self.extract_key_findings(results)
        if findings:
            lines.append("\n## Key Findings")
            for finding in findings:
                lines.append(f"- {finding}")
        
        # Recommendations
        if failed > 0:
            lines.append(f"\n## Recommendations")
            lines.append(f"- {failed} sub-agent(s) failed - consider reviewing their outputs")
            lines.append("- Some tasks may need to be retried with different parameters")
        
        content = "\n".join(lines)
        
        # Determine overall success
        overall_ok = successful > 0  # At least some success
        
        return SubAgentResult(
            ok=overall_ok,
            content=content,
            error=None if overall_ok else "Some sub-agents failed",
            error_code=None if overall_ok else "PARTIAL_FAILURE",
            metadata={
                "total": total,
                "successful": successful,
                "failed": failed,
                "has_findings": len(findings) > 0,
            }
        )
    
    def aggregate_metrics(
        self,
        results: List[SubAgentResult],
    ) -> Dict[str, Any]:
        """
        Aggregate metrics from sub-agent results.
        
        Args:
            results: List of SubAgentResult
            
        Returns:
            Dictionary with aggregated metrics
        """
        total = len(results)
        successful = sum(1 for r in results if r.ok)
        failed = total - successful
        
        total_turns = sum(
            r.metadata.get("turns", 0)
            for r in results
        )
        
        total_tool_calls = sum(
            r.metadata.get("tool_calls", 0)
            for r in results
        )
        
        return {
            "total_subagents": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "total_turns": total_turns,
            "total_tool_calls": total_tool_calls,
            "avg_turns": total_turns / total if total > 0 else 0,
        }


# Global summarizer instance
_summarizer: Optional[SubAgentSummarizer] = None


def get_subagent_summarizer() -> SubAgentSummarizer:
    """
    Get the global sub-agent summarizer instance.
    
    Returns:
        Global SubAgentSummarizer instance
    """
    global _summarizer
    if _summarizer is None:
        _summarizer = SubAgentSummarizer()
    return _summarizer


def set_subagent_summarizer(summarizer: SubAgentSummarizer) -> None:
    """
    Set the global sub-agent summarizer instance.
    
    Args:
        summarizer: SubAgentSummarizer to use globally
    """
    global _summarizer
    _summarizer = summarizer


__all__ = [
    "SubAgentSummarizer",
    "get_subagent_summarizer",
    "set_subagent_summarizer",
]
