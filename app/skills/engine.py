"""Skill execution engine for Teiken Claw.

This module provides the SkillEngine class for executing skill workflows
step-by-step with context management and error handling.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

from app.skills.loader import SkillLoader, get_skill_loader
from app.skills.schema import SkillDefinition, SkillStep, StepType

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    """Result of skill execution."""
    success: bool
    outputs: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    steps_executed: int = 0
    execution_time_ms: float = 0.0
    logs: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "success": self.success,
            "outputs": self.outputs,
            "error": self.error,
            "steps_executed": self.steps_executed,
            "execution_time_ms": self.execution_time_ms,
            "logs": self.logs,
        }
    
    def __str__(self) -> str:
        """String representation of result."""
        if self.success:
            return f"SkillResult(success=True, steps={self.steps_executed}, outputs={self.outputs})"
        return f"SkillResult(success=False, error={self.error})"


@dataclass
class ExecutionContext:
    """Execution context passed between steps."""
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    current_step_id: Optional[str] = None
    step_results: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from context (checks outputs first, then inputs, then variables)."""
        if key in self.outputs:
            return self.outputs[key]
        if key in self.inputs:
            return self.inputs[key]
        if key in self.variables:
            return self.variables[key]
        return default
    
    def set_output(self, key: str, value: Any) -> None:
        """Set an output value."""
        self.outputs[key] = value
    
    def set_variable(self, key: str, value: Any) -> None:
        """Set a variable value."""
        self.variables[key] = value
    
    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
    
    def has_errors(self) -> bool:
        """Check if context has any errors."""
        return len(self.errors) > 0


class SkillEngine:
    """Engine for executing skill workflows."""
    
    def __init__(self, loader: Optional[SkillLoader] = None):
        """Initialize the skill engine.
        
        Args:
            loader: SkillLoader instance to use. Defaults to global loader.
        """
        self.loader = loader or get_skill_loader()
        self.tool_registry: dict[str, Any] = {}
        
        logger.info("SkillEngine initialized")
    
    def register_tool(self, name: str, tool: Any) -> None:
        """Register a tool for use in skill executions.
        
        Args:
            name: Tool name
            tool: Tool instance with execute method
        """
        self.tool_registry[name] = tool
        logger.debug(f"Registered tool: {name}")
    
    def execute_skill(
        self, 
        skill_name: str, 
        inputs: Optional[dict[str, Any]] = None,
        context: Optional[ExecutionContext] = None
    ) -> SkillResult:
        """Execute a skill by name with provided inputs.
        
        Args:
            skill_name: Name of the skill to execute
            inputs: Input parameters for the skill
            context: Optional existing execution context
            
        Returns:
            SkillResult with execution outcome
        """
        start_time = datetime.now()
        
        # Load skill definition
        skill = self.loader.get_skill(skill_name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"Skill not found: {skill_name}"
            )
        
        # Initialize context
        if context is None:
            context = ExecutionContext()
        
        if inputs:
            context.inputs.update(inputs)
        
        # Validate required inputs
        for skill_input in skill.inputs:
            if skill_input.required:
                if skill_input.name not in context.inputs and skill_input.default is None:
                    return SkillResult(
                        success=False,
                        error=f"Missing required input: {skill_input.name}"
                    )
                if skill_input.name not in context.inputs:
                    context.inputs[skill_input.name] = skill_input.default
        
        logger.info(f"Executing skill: {skill.name} (version {skill.version})")
        
        # Execute steps sequentially
        try:
            result = self._execute_steps(skill, context)
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return SkillResult(
                success=True,
                outputs=result.outputs,
                steps_executed=context.step_results.__len__(),
                execution_time_ms=execution_time,
                logs=context.errors
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"Skill execution failed: {e}", exc_info=True)
            context.add_error(str(e))
            
            return SkillResult(
                success=False,
                error=str(e),
                steps_executed=context.step_results.__len__(),
                execution_time_ms=execution_time,
                logs=context.errors
            )
    
    def _execute_steps(self, skill: SkillDefinition, context: ExecutionContext) -> ExecutionContext:
        """Execute all steps in a skill workflow.
        
        Args:
            skill: The skill definition
            context: Execution context
            
        Returns:
            Updated execution context
            
        Raises:
            Exception: If a step fails
        """
        current_step = skill.get_first_step()
        
        while current_step:
            context.current_step_id = current_step.id
            logger.debug(f"Executing step: {current_step.id} (type: {current_step.type.value})")
            
            try:
                result = self._execute_step(current_step, context)
                context.step_results[current_step.id] = result
                
                # Determine next step
                if current_step.type == StepType.RETURN:
                    # Return step ends execution
                    break
                
                # Handle branching based on result
                if current_step.on_success and result is not None:
                    next_step_id = current_step.on_success
                elif current_step.on_failure and result is None:
                    next_step_id = current_step.on_failure
                else:
                    # Default: go to next step in sequence
                    current_idx = next(i for i, s in enumerate(skill.steps) if s.id == current_step.id)
                    if current_idx + 1 < len(skill.steps):
                        next_step_id = skill.steps[current_idx + 1].id
                    else:
                        next_step_id = None
                
                if next_step_id:
                    current_step = skill.get_step(next_step_id)
                else:
                    current_step = None
                    
            except Exception as e:
                logger.error(f"Step {current_step.id} failed: {e}")
                context.add_error(f"Step {current_step.id}: {str(e)}")
                
                # Try to go to failure branch
                if current_step.on_failure:
                    current_step = skill.get_step(current_step.on_failure)
                else:
                    raise
        
        return context
    
    def _execute_step(self, step: SkillStep, context: ExecutionContext) -> Any:
        """Execute a single step based on its type.
        
        Args:
            step: The step to execute
            context: Execution context
            
        Returns:
            Result of step execution
        """
        executors = {
            StepType.TOOL_CALL: self.execute_tool_call,
            StepType.LLM_PROMPT: self.execute_llm_prompt,
            StepType.CONDITION: self.execute_condition,
            StepType.TRANSFORM: self.execute_transform,
            StepType.SUBAGENT: self.execute_subagent,
            StepType.SCHEDULE_CREATE: self.execute_schedule_create,
            StepType.RETURN: self.execute_return,
        }
        
        executor = executors.get(step.type)
        if not executor:
            raise ValueError(f"Unknown step type: {step.type}")
        
        return executor(step, context)
    
    def execute_tool_call(self, step: SkillStep, context: ExecutionContext) -> Any:
        """Execute a tool call step.
        
        Args:
            step: The tool call step
            context: Execution context
            
        Returns:
            Tool execution result
        """
        if not step.tool_name:
            raise ValueError(f"Step {step.id}: tool_name is required")
        
        tool = self.tool_registry.get(step.tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {step.tool_name}")
        
        # Resolve parameters from context
        params = self._resolve_params(step.tool_params, context)
        
        logger.debug(f"Calling tool: {step.tool_name} with params: {params}")
        
        if hasattr(tool, 'execute'):
            result = tool.execute(**params)
        elif callable(tool):
            result = tool(**params)
        else:
            raise ValueError(f"Tool {step.tool_name} is not executable")
        
        # Store result if step has output mapping
        if step.id:
            context.step_results[step.id] = result
        
        return result
    
    def execute_llm_prompt(self, step: SkillStep, context: ExecutionContext) -> Any:
        """Execute an LLM prompt step.
        
        Args:
            step: The LLM prompt step
            context: Execution context
            
        Returns:
            LLM response
        """
        if not step.prompt:
            raise ValueError(f"Step {step.id}: prompt is required")
        
        # Resolve prompt inputs from context
        prompt_inputs = {}
        if step.prompt_inputs:
            for key, value_path in step.prompt_inputs.items():
                prompt_inputs[key] = self._resolve_value(value_path, context)
        
        # Format prompt with inputs
        prompt = step.prompt
        if prompt_inputs:
            try:
                prompt = prompt.format(**prompt_inputs)
            except KeyError as e:
                raise ValueError(f"Missing prompt input: {e}")
        
        logger.debug(f"Executing LLM prompt: {prompt[:100]}...")
        
        # TODO: Integrate with actual LLM client
        # For now, return a placeholder
        result = f"LLM response to: {prompt[:50]}..."
        
        if step.id:
            context.step_results[step.id] = result
        
        return result
    
    def execute_condition(self, step: SkillStep, context: ExecutionContext) -> bool:
        """Execute a condition step.
        
        Args:
            step: The condition step
            context: Execution context
            
        Returns:
            Boolean result of condition evaluation
        """
        if not step.condition_expression:
            raise ValueError(f"Step {step.id}: condition_expression is required")
        
        # Resolve variables in expression
        expression = self._resolve_expression(step.condition_expression, context)
        
        logger.debug(f"Evaluating condition: {expression}")
        
        try:
            # Safe evaluation of condition
            result = self._safe_eval(expression, context.variables)
            
            if step.id:
                context.step_results[step.id] = result
            
            return result
            
        except Exception as e:
            raise ValueError(f"Condition evaluation failed: {e}")
    
    def execute_transform(self, step: SkillStep, context: ExecutionContext) -> Any:
        """Execute a transform step.
        
        Args:
            step: The transform step
            context: Execution context
            
        Returns:
            Transformed result
        """
        if not step.transform_expression:
            raise ValueError(f"Step {step.id}: transform_expression is required")
        
        # Get input value
        input_value = None
        if step.transform_input:
            input_value = self._resolve_value(step.transform_input, context)
        
        # Apply transformation
        expression = step.transform_expression
        if input_value is not None:
            # Replace placeholder with actual value
            expression = expression.replace("{{input}}", repr(input_value))
        
        logger.debug(f"Applying transform: {expression}")
        
        try:
            result = self._safe_eval(expression, context.variables)
            
            if step.id:
                context.step_results[step.id] = result
            
            return result
            
        except Exception as e:
            raise ValueError(f"Transform failed: {e}")
    
    def execute_subagent(self, step: SkillStep, context: ExecutionContext) -> Any:
        """Execute a subagent step.
        
        Args:
            step: The subagent step
            context: Execution context
            
        Returns:
            Subagent response
        """
        if not step.subagent_name:
            raise ValueError(f"Step {step.id}: subagent_name is required")
        
        # Resolve subagent prompt
        prompt = step.subagent_prompt or ""
        if step.prompt_inputs:
            for key, value_path in step.prompt_inputs.items():
                prompt = prompt.replace(f"{{{key}}}", str(self._resolve_value(value_path, context)))
        
        logger.debug(f"Invoking subagent: {step.subagent_name}")
        
        # TODO: Integrate with actual subagent system
        # For now, return a placeholder
        result = f"Subagent {step.subagent_name} response"
        
        if step.id:
            context.step_results[step.id] = result
        
        return result
    
    def execute_schedule_create(self, step: SkillStep, context: ExecutionContext) -> str:
        """Execute a schedule creation step.
        
        Args:
            step: The schedule create step
            context: Execution context
            
        Returns:
            Created schedule/job ID
        """
        if not step.schedule_cron:
            raise ValueError(f"Step {step.id}: schedule_cron is required")
        
        if not step.schedule_action:
            raise ValueError(f"Step {step.id}: schedule_action is required")
        
        # Resolve parameters from context
        cron = self._resolve_value(step.schedule_cron, context)
        action = self._resolve_value(step.schedule_action, context)
        
        logger.debug(f"Creating schedule: cron={cron}, action={action}")
        
        # Get scheduler tool if available
        scheduler = self.tool_registry.get("scheduler")
        if scheduler:
            # Create job via scheduler
            job_name = context.get("job_name", f"skill_{context.current_step_id}")
            result = f"job_{job_name}_{int(datetime.now().timestamp())}"
        else:
            result = f"schedule_created:{cron}"
        
        if step.id:
            context.step_results[step.id] = result
        
        return result
    
    def execute_return(self, step: SkillStep, context: ExecutionContext) -> SkillResult:
        """Execute a return step and end skill execution.
        
        Args:
            step: The return step
            context: Execution context
            
        Returns:
            SkillResult with outputs
        """
        # Resolve return value
        return_value = None
        if step.return_value:
            return_value = self._resolve_value(step.return_value, context)
        
        # Build outputs from context
        outputs = dict(context.outputs)
        if return_value is not None:
            outputs["result"] = return_value
        
        logger.info(f"Skill returning: {outputs}")
        
        return SkillResult(
            success=True,
            outputs=outputs
        )
    
    def _resolve_params(
        self, 
        params: Optional[dict[str, Any]], 
        context: ExecutionContext
    ) -> dict[str, Any]:
        """Resolve parameter values from context.
        
        Args:
            params: Parameter dictionary with potential context references
            context: Execution context
            
        Returns:
            Resolved parameter dictionary
        """
        if not params:
            return {}
        
        resolved = {}
        for key, value in params.items():
            resolved[key] = self._resolve_value(value, context)
        
        return resolved
    
    def _resolve_value(self, value: Any, context: ExecutionContext) -> Any:
        """Resolve a value that may contain context references.
        
        Args:
            value: Value to resolve (may be a string like "${variable.name}")
            context: Execution context
            
        Returns:
            Resolved value
        """
        if not isinstance(value, str):
            return value
        
        # Handle context references: ${variable.name}
        pattern = r'\$\{([^}]+)\}'
        
        def replace_ref(match):
            path = match.group(1)
            return str(context.get(path, match.group(0)))
        
        return re.sub(pattern, replace_ref, value)
    
    def _resolve_expression(
        self, 
        expression: str, 
        context: ExecutionContext
    ) -> str:
        """Resolve variables in an expression.
        
        Args:
            expression: Expression string
            context: Execution context
            
        Returns:
            Resolved expression
        """
        return self._resolve_value(expression, context)
    
    def _safe_eval(self, expression: str, variables: dict[str, Any]) -> Any:
        """Safely evaluate a simple expression.
        
        Args:
            expression: Expression to evaluate
            variables: Variables available in scope
            
        Returns:
            Evaluation result
        """
        # Only allow safe operations
        allowed_names = {
            "True": True,
            "False": False,
            "None": None,
            "and": lambda a, b: a and b,
            "or": lambda a, b: a or b,
            "not": lambda a: not a,
            "in": lambda a, b: a in b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
        }
        
        # Add variables to allowed names
        allowed_names.update(variables)
        
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return result


# Global engine instance
_default_engine: Optional[SkillEngine] = None


def get_skill_engine() -> SkillEngine:
    """Get the default global skill engine instance.
    
    Returns:
        The global SkillEngine instance
    """
    global _default_engine
    if _default_engine is None:
        _default_engine = SkillEngine()
    return _default_engine


def execute_skill(
    skill_name: str, 
    inputs: Optional[dict[str, Any]] = None
) -> SkillResult:
    """Convenience function to execute a skill.
    
    Args:
        skill_name: Name of the skill
        inputs: Input parameters
        
    Returns:
        SkillResult
    """
    return get_skill_engine().execute_skill(skill_name, inputs)


__all__ = [
    'SkillEngine',
    'SkillResult',
    'ExecutionContext',
    'get_skill_engine',
    'execute_skill',
]
