import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    pass


class ActionType(Enum):
    CLICK = "click"
    INPUT = "input"
    CLEAR_INPUT = "clear_input"
    SELECT_DROPDOWN = "select_dropdown"
    CHECK_CHECKBOX = "check_checkbox"
    READ_TEXT = "read_text"
    READ_TABLE = "read_table"
    WAIT_WINDOW = "wait_window"
    WAIT_CONTROL = "wait_control"
    CHECK_MESSAGE = "check_message"
    SCREENSHOT = "screenshot"
    HOTKEY = "hotkey"
    DELAY = "delay"
    SAVE = "save"
    GO_BACK = "go_back"
    OPEN_MENU = "open_menu"


class ValueSource(Enum):
    CONSTANT = "constant"
    SYSTEM_FIELD = "system_field"
    CALCULATED = "calculated"
    PREVIOUS_RESULT = "previous_result"


class ErrorHandling(Enum):
    RETRY = "retry"
    SKIP = "skip"
    STOP = "stop"
    LOG_AND_CONTINUE = "log_and_continue"


@dataclass
class ActionStep:
    action_type: ActionType
    target: Dict[str, Any] = field(default_factory=dict)
    value_source: ValueSource = ValueSource.CONSTANT
    value: str = ""
    value_field: str = ""
    timeout: int = 10
    retry_count: int = 3
    on_error: ErrorHandling = ErrorHandling.RETRY
    description: str = ""
    condition: str = ""
    save_result_to: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'action_type': self.action_type.value,
            'target': self.target,
            'value_source': self.value_source.value,
            'value': self.value,
            'value_field': self.value_field,
            'timeout': self.timeout,
            'retry_count': self.retry_count,
            'on_error': self.on_error.value,
            'description': self.description,
            'condition': self.condition,
            'save_result_to': self.save_result_to
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'ActionStep':
        return ActionStep(
            action_type=ActionType(data.get('action_type', 'click')),
            target=data.get('target', {}),
            value_source=ValueSource(data.get('value_source', 'constant')),
            value=data.get('value', ''),
            value_field=data.get('value_field', ''),
            timeout=data.get('timeout', 10),
            retry_count=data.get('retry_count', 3),
            on_error=ErrorHandling(data.get('on_error', 'retry')),
            description=data.get('description', ''),
            condition=data.get('condition', ''),
            save_result_to=data.get('save_result_to', '')
        )


@dataclass
class ActionResult:
    success: bool
    action_type: ActionType
    result_value: str = ""
    error_message: str = ""
    screenshot_path: str = ""
    execution_time: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'success': self.success,
            'action_type': self.action_type.value,
            'result_value': self.result_value,
            'error_message': self.error_message,
            'screenshot_path': self.screenshot_path,
            'execution_time': self.execution_time
        }