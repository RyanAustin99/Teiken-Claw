"""
System prompt building for the Teiken Claw agent.

This module provides functions for building system prompts
that configure the AI agent's behavior.

Key Features:
    - Mode-aware prompt formatting
    - Soul/personality configuration
    - Tool usage instructions
"""

from typing import Any, Dict, List, Optional


# Default system prompt template
DEFAULT_SYSTEM_PROMPT = """You are Teiken Claw, an AI assistant with access to tools.

You are helpful, accurate, and concise. When you need to perform an action, use the available tools.

Guidelines:
- Be direct and helpful
- Use tools when appropriate to accomplish tasks
- If you don't know something, say so
- Don't make up information
- Be concise in your responses

Current mode: {mode}
"""

# Mode-specific prompts
MODE_PROMPTS = {
    "default": """You are in standard mode. Provide helpful, balanced responses.""",
    
    "creative": """You are in creative mode. Feel free to be more imaginative and exploratory in your responses while still being helpful.""",
    
    "precise": """You are in precise mode. Be extremely accurate and factual. Cite sources when possible. Avoid speculation.""",
    
    "coding": """You are in coding mode. Focus on providing accurate, well-structured code solutions. Include comments and explanations where helpful.""",
    
    "analysis": """You are in analysis mode. Provide thorough, analytical responses. Consider multiple perspectives and implications.""",
}


def build_system_prompt(
    mode: str = "default",
    soul_config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build the system prompt for the agent.
    
    Args:
        mode: Operating mode for the agent
        soul_config: Optional soul/personality configuration
        
    Returns:
        Complete system prompt string
    """
    parts = []
    
    # Base prompt
    base_prompt = DEFAULT_SYSTEM_PROMPT.format(mode=mode)
    parts.append(base_prompt)
    
    # Mode-specific additions
    if mode in MODE_PROMPTS:
        parts.append("\n" + MODE_PROMPTS[mode])
    
    # Soul/personality configuration
    if soul_config:
        soul_prompt = _build_soul_prompt(soul_config)
        if soul_prompt:
            parts.append("\n" + soul_prompt)
    
    return "\n".join(parts)


def _build_soul_prompt(soul_config: Dict[str, Any]) -> str:
    """
    Build soul/personality prompt from configuration.
    
    Args:
        soul_config: Soul configuration dictionary
        
    Returns:
        Soul prompt string
    """
    parts = []
    
    # Personality traits
    traits = soul_config.get("traits", [])
    if traits:
        parts.append("Personality traits: " + ", ".join(traits))
    
    # Background/context
    background = soul_config.get("background")
    if background:
        parts.append(f"Background: {background}")
    
    # Communication style
    style = soul_config.get("communication_style")
    if style:
        parts.append(f"Communication style: {style}")
    
    # Custom instructions
    instructions = soul_config.get("instructions")
    if instructions:
        parts.append(f"Special instructions: {instructions}")
    
    return "\n".join(parts)


def build_tool_prompt(tools: List[Dict[str, Any]]) -> str:
    """
    Build a prompt describing available tools.
    
    This is appended to help the model understand tool usage.
    
    Args:
        tools: List of tool schemas
        
    Returns:
        Tool description string
    """
    if not tools:
        return ""
    
    lines = ["Available tools:"]
    
    for tool in tools:
        function = tool.get("function", {})
        name = function.get("name", "unknown")
        description = function.get("description", "No description")
        
        lines.append(f"- {name}: {description}")
    
    lines.append("\nUse tools by calling them with appropriate arguments.")
    
    return "\n".join(lines)


def build_context_prompt(
    session_info: Optional[Dict[str, Any]] = None,
    user_info: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build context information for the prompt.
    
    Args:
        session_info: Session-related information
        user_info: User-related information
        
    Returns:
        Context prompt string
    """
    parts = []
    
    if session_info:
        session_id = session_info.get("session_id")
        if session_id:
            parts.append(f"Session: {session_id[:8]}...")
        
        message_count = session_info.get("message_count")
        if message_count is not None:
            parts.append(f"Messages in conversation: {message_count}")
    
    if user_info:
        user_name = user_info.get("name")
        if user_name:
            parts.append(f"User: {user_name}")
        
        is_admin = user_info.get("is_admin")
        if is_admin:
            parts.append("User has admin privileges")
    
    if not parts:
        return ""
    
    return "Context:\n" + "\n".join(f"- {p}" for p in parts)


def format_message_for_prompt(
    role: str,
    content: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    tool_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Format a message for the Ollama API.
    
    Args:
        role: Message role (user, assistant, system, tool)
        content: Message content
        tool_calls: Optional tool calls from assistant
        tool_results: Optional tool results
        
    Returns:
        Message dictionary for Ollama API
    """
    message = {"role": role, "content": content}
    
    if tool_calls:
        message["tool_calls"] = tool_calls
    
    return message


def build_tool_result_message(
    tool_call_id: str,
    tool_name: str,
    result: str,
) -> Dict[str, Any]:
    """
    Build a tool result message for the conversation.
    
    Args:
        tool_call_id: ID of the tool call
        tool_name: Name of the tool
        result: Result content
        
    Returns:
        Tool result message dictionary
    """
    return {
        "role": "tool",
        "content": result,
        "name": tool_name,
    }


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "MODE_PROMPTS",
    "build_system_prompt",
    "build_tool_prompt",
    "build_context_prompt",
    "format_message_for_prompt",
    "build_tool_result_message",
]
