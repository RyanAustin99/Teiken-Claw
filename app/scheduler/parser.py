"""
Schedule parsing for the Teiken Claw scheduler.

This module provides:
- ScheduleParser class for parsing schedule expressions
- Support for cron, interval, and date triggers
- User-friendly format conversions
- Validation of trigger configurations

Key Features:
    - Parse standard cron expressions
    - Parse natural language intervals
    - Parse ISO datetime strings
    - Validate trigger configurations
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Union, Dict, Any

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.schedulers.base import BaseScheduler

from app.scheduler.jobs import TriggerType, TriggerConfig

logger = logging.getLogger(__name__)


class ScheduleParseError(Exception):
    """Error parsing schedule expression."""
    pass


class ScheduleParser:
    """
    Parser for schedule expressions.
    
    Provides methods to parse and validate:
    - Cron expressions (standard 5-field or 6-field)
    - Interval configurations (seconds, minutes, hours, days, weeks)
    - Date/datetime strings (ISO format or natural language)
    
    Example:
        parser = ScheduleParser()
        
        # Parse cron expression
        trigger = parser.parse_cron("0 9 * * *")  # Every day at 9 AM
        
        # Parse interval
        trigger = parser.parse_interval({"minutes": 30})  # Every 30 minutes
        
        # Parse date
        trigger = parser.parse_date("2024-12-25T09:00:00")  # One-time at specific time
    """
    
    # Common cron aliases
    CRON_ALIASES = {
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
        "@monthly": "0 0 1 * *",
        "@weekly": "0 0 * * 0",
        "@daily": "0 0 * * *",
        "@midnight": "0 0 * * *",
        "@hourly": "0 * * * *",
    }
    
    # Day name mappings
    DAY_NAMES = {
        "sun": 0, "sunday": 0,
        "mon": 1, "monday": 1,
        "tue": 2, "tuesday": 2,
        "wed": 3, "wednesday": 3,
        "thu": 4, "thursday": 4,
        "fri": 5, "friday": 5,
        "sat": 6, "saturday": 6,
    }
    
    # Month name mappings
    MONTH_NAMES = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    
    def __init__(self, timezone: Optional[str] = None):
        """
        Initialize the schedule parser.
        
        Args:
            timezone: Default timezone for triggers (default: UTC)
        """
        self.timezone = timezone or "UTC"
    
    def parse_cron(self, expression: str, timezone: Optional[str] = None) -> CronTrigger:
        """
        Parse a cron expression into a CronTrigger.
        
        Supports:
        - Standard 5-field cron (minute, hour, day, month, day_of_week)
        - 6-field cron (second, minute, hour, day, month, day_of_week)
        - Special aliases (@yearly, @monthly, @weekly, @daily, @hourly)
        
        Args:
            expression: Cron expression or alias
            timezone: Optional timezone override
            
        Returns:
            CronTrigger instance
            
        Raises:
            ScheduleParseError: If expression is invalid
        """
        try:
            # Check for aliases
            expression_lower = expression.lower().strip()
            if expression_lower in self.CRON_ALIASES:
                expression = self.CRON_ALIASES[expression_lower]
                logger.debug(f"Expanded cron alias '{expression_lower}' to '{expression}'")
            
            # Parse the expression
            fields = expression.split()
            
            if len(fields) == 5:
                # Standard 5-field: minute hour day month day_of_week
                trigger = CronTrigger(
                    minute=fields[0],
                    hour=fields[1],
                    day=fields[2],
                    month=fields[3],
                    day_of_week=fields[4],
                    timezone=timezone or self.timezone,
                )
            elif len(fields) == 6:
                # 6-field: second minute hour day month day_of_week
                trigger = CronTrigger(
                    second=fields[0],
                    minute=fields[1],
                    hour=fields[2],
                    day=fields[3],
                    month=fields[4],
                    day_of_week=fields[5],
                    timezone=timezone or self.timezone,
                )
            else:
                raise ScheduleParseError(
                    f"Invalid cron expression: expected 5 or 6 fields, got {len(fields)}"
                )
            
            logger.debug(f"Parsed cron expression: {expression}")
            return trigger
            
        except ScheduleParseError:
            raise
        except Exception as e:
            raise ScheduleParseError(f"Failed to parse cron expression '{expression}': {e}")
    
    def parse_interval(self, config: Dict[str, Any]) -> IntervalTrigger:
        """
        Parse an interval configuration into an IntervalTrigger.
        
        Supports:
        - seconds, minutes, hours, days, weeks
        - start_date, end_date for bounded intervals
        - jitter for random delay
        
        Args:
            config: Dictionary with interval configuration
                - seconds: int
                - minutes: int
                - hours: int
                - days: int
                - weeks: int
                - start_date: Optional datetime or ISO string
                - end_date: Optional datetime or ISO string
                - jitter: Optional int (seconds)
                
        Returns:
            IntervalTrigger instance
            
        Raises:
            ScheduleParseError: If configuration is invalid
        """
        try:
            # Extract interval components
            seconds = config.get("seconds", 0) or 0
            minutes = config.get("minutes", 0) or 0
            hours = config.get("hours", 0) or 0
            days = config.get("days", 0) or 0
            weeks = config.get("weeks", 0) or 0
            
            # Validate at least one interval component is set
            total_seconds = seconds + minutes * 60 + hours * 3600 + days * 86400 + weeks * 604800
            if total_seconds <= 0:
                raise ScheduleParseError(
                    "At least one interval component must be positive "
                    "(seconds, minutes, hours, days, or weeks)"
                )
            
            # Parse optional dates
            start_date = self._parse_optional_datetime(config.get("start_date"))
            end_date = self._parse_optional_datetime(config.get("end_date"))
            jitter = config.get("jitter")
            
            trigger = IntervalTrigger(
                seconds=seconds,
                minutes=minutes,
                hours=hours,
                days=days,
                weeks=weeks,
                start_date=start_date,
                end_date=end_date,
                jitter=jitter,
                timezone=self.timezone,
            )
            
            logger.debug(
                f"Parsed interval trigger: {seconds}s {minutes}m {hours}h {days}d {weeks}w"
            )
            return trigger
            
        except ScheduleParseError:
            raise
        except Exception as e:
            raise ScheduleParseError(f"Failed to parse interval config: {e}")
    
    def parse_date(self, datetime_str: Union[str, datetime]) -> DateTrigger:
        """
        Parse a datetime string into a DateTrigger.
        
        Supports:
        - ISO 8601 format: "2024-12-25T09:00:00"
        - Date only: "2024-12-25" (defaults to midnight)
        - datetime objects
        
        Args:
            datetime_str: ISO datetime string or datetime object
            
        Returns:
            DateTrigger instance
            
        Raises:
            ScheduleParseError: If datetime is invalid
        """
        try:
            # Handle datetime object directly
            if isinstance(datetime_str, datetime):
                dt = datetime_str
            else:
                dt = self._parse_datetime_string(datetime_str)
            
            # Validate it's in the future
            if dt < datetime.utcnow():
                logger.warning(f"Date trigger is in the past: {dt}")
            
            trigger = DateTrigger(run_date=dt, timezone=self.timezone)
            
            logger.debug(f"Parsed date trigger: {dt}")
            return trigger
            
        except ScheduleParseError:
            raise
        except Exception as e:
            raise ScheduleParseError(f"Failed to parse date '{datetime_str}': {e}")
    
    def parse_trigger(
        self,
        trigger_type: Union[TriggerType, str],
        config: Union[TriggerConfig, Dict[str, Any]],
    ) -> Union[CronTrigger, IntervalTrigger, DateTrigger]:
        """
        Parse a trigger based on type and configuration.
        
        Args:
            trigger_type: Type of trigger (date, interval, cron)
            config: Trigger configuration
            
        Returns:
            Appropriate trigger instance
            
        Raises:
            ScheduleParseError: If trigger type or config is invalid
        """
        # Normalize trigger type
        if isinstance(trigger_type, str):
            trigger_type = TriggerType(trigger_type.lower())
        
        # Normalize config
        if isinstance(config, TriggerConfig):
            config = config.model_dump(exclude_none=True)
        
        if trigger_type == TriggerType.DATE:
            # For date trigger, use run_at or start_date
            run_at = config.get("run_at") or config.get("start_date")
            if not run_at:
                raise ScheduleParseError("Date trigger requires 'run_at' or 'start_date'")
            return self.parse_date(run_at)
        
        elif trigger_type == TriggerType.INTERVAL:
            return self.parse_interval(config)
        
        elif trigger_type == TriggerType.CRON:
            # For cron trigger, use cron_expression or individual fields
            cron_expr = config.get("cron_expression")
            if cron_expr:
                return self.parse_cron(cron_expr, config.get("timezone"))
            
            # Build from individual fields
            return self._build_cron_from_fields(config)
        
        else:
            raise ScheduleParseError(f"Unknown trigger type: {trigger_type}")
    
    def validate_trigger_config(
        self,
        trigger_type: Union[TriggerType, str],
        config: Union[TriggerConfig, Dict[str, Any]],
    ) -> bool:
        """
        Validate a trigger configuration.
        
        Args:
            trigger_type: Type of trigger
            config: Trigger configuration
            
        Returns:
            True if valid
            
        Raises:
            ScheduleParseError: If configuration is invalid
        """
        try:
            self.parse_trigger(trigger_type, config)
            return True
        except Exception as e:
            raise ScheduleParseError(f"Invalid trigger config: {e}")
    
    def _parse_datetime_string(self, datetime_str: str) -> datetime:
        """
        Parse a datetime string into a datetime object.
        
        Args:
            datetime_str: String to parse
            
        Returns:
            datetime object
        """
        datetime_str = datetime_str.strip()
        
        # Try ISO format with time
        try:
            return datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        except ValueError:
            pass
        
        # Try date only (YYYY-MM-DD)
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        if re.match(date_pattern, datetime_str):
            return datetime.strptime(datetime_str, "%Y-%m-%d")
        
        # Try common formats
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(datetime_str, fmt)
            except ValueError:
                continue
        
        raise ScheduleParseError(f"Unable to parse datetime: {datetime_str}")
    
    def _parse_optional_datetime(
        self,
        value: Optional[Union[str, datetime]],
    ) -> Optional[datetime]:
        """
        Parse an optional datetime value.
        
        Args:
            value: Optional datetime string or object
            
        Returns:
            datetime object or None
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return self._parse_datetime_string(value)
    
    def _build_cron_from_fields(self, config: Dict[str, Any]) -> CronTrigger:
        """
        Build a CronTrigger from individual field configurations.
        
        Args:
            config: Dictionary with cron fields
            
        Returns:
            CronTrigger instance
        """
        return CronTrigger(
            year=config.get("year"),
            month=config.get("month"),
            day=config.get("day"),
            week=config.get("week"),
            day_of_week=config.get("day_of_week"),
            hour=config.get("hour"),
            minute=config.get("minute"),
            second=config.get("second"),
            timezone=config.get("timezone") or self.timezone,
            start_date=self._parse_optional_datetime(config.get("start_date")),
            end_date=self._parse_optional_datetime(config.get("end_date")),
        )
    
    @staticmethod
    def get_next_run_times(
        trigger: Union[CronTrigger, IntervalTrigger, DateTrigger],
        count: int = 5,
    ) -> list:
        """
        Get the next N run times for a trigger.
        
        Args:
            trigger: The trigger to calculate run times for
            count: Number of run times to calculate
            
        Returns:
            List of datetime objects
        """
        from datetime import timezone as tz
        
        now = datetime.now(tz.utc)
        run_times = []
        
        for _ in range(count):
            next_time = trigger.get_next_fire_time(None, now)
            if next_time is None:
                break
            run_times.append(next_time)
            now = next_time
        
        return run_times
    
    @staticmethod
    def format_trigger_description(
        trigger: Union[CronTrigger, IntervalTrigger, DateTrigger],
    ) -> str:
        """
        Get a human-readable description of a trigger.
        
        Args:
            trigger: The trigger to describe
            
        Returns:
            Human-readable description string
        """
        if isinstance(trigger, CronTrigger):
            return str(trigger)
        elif isinstance(trigger, IntervalTrigger):
            return str(trigger)
        elif isinstance(trigger, DateTrigger):
            return f"Run once at {trigger.run_date}"
        else:
            return f"Unknown trigger type: {type(trigger)}"


# Export
__all__ = [
    "ScheduleParser",
    "ScheduleParseError",
]
