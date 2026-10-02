"""
OpsMind Safety Framework - MVP Version
Simplified guardrails for basic security
"""

import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from collections import deque
import logging

from opsmind.config import logger


class GuardrailType(Enum):
    """Basic guardrail types for MVP"""
    VALIDATION = "validation"
    RATE_LIMITING = "rate_limiting"
    UI_CONTENT_ESCAPING = "ui_content_escaping"


class GuardrailStatus(Enum):
    """Status of guardrail checks"""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class GuardrailConfig:
    """Simple configuration for guardrails"""
    name: str
    type: GuardrailType
    enabled: bool = True
    strict_mode: bool = False
    custom_params: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.custom_params is None:
            self.custom_params = {}
            
    @property
    def params(self) -> Dict[str, Any]:
        """Get custom parameters (guaranteed to be a dict)"""
        return self.custom_params or {}


@dataclass
class GuardrailResult:
    """Result of a guardrail check"""
    guardrail_name: str
    status: GuardrailStatus
    message: str
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class BaseGuardrail(ABC):
    """Base class for all guardrails"""
    
    def __init__(self, config: GuardrailConfig):
        self.config = config
        self.check_count = 0
        self._lock = threading.Lock()
    
    @abstractmethod
    async def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """Perform the guardrail check"""
        pass
    
    def update_stats(self):
        """Simple stats tracking"""
        with self._lock:
            self.check_count += 1


class ValidationGuardrail(BaseGuardrail):
    """Basic input validation"""
    
    def __init__(self, config: GuardrailConfig):
        super().__init__(config)
        self.max_field_length = config.params.get('max_field_length', 10000)
        self.forbidden_patterns = config.params.get('forbidden_patterns', [
            '<script>', 'javascript:', 'vbscript:', 'onload=', 'onerror='
        ])
    
    async def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """Basic validation check"""
        try:
            data = context.get('data', {})
            
            # Check field lengths
            for key, value in data.items():
                if isinstance(value, str) and len(value) > self.max_field_length:
                    return GuardrailResult(
                        guardrail_name=self.config.name,
                        status=GuardrailStatus.FAILED,
                        message=f"Field '{key}' exceeds maximum length"
                    )
            
            # Check for forbidden patterns
            for key, value in data.items():
                if isinstance(value, str):
                    for pattern in self.forbidden_patterns:
                        if pattern.lower() in value.lower():
                            return GuardrailResult(
                                guardrail_name=self.config.name,
                                status=GuardrailStatus.FAILED,
                                message=f"Field '{key}' contains forbidden pattern: {pattern}"
                            )
            
            return GuardrailResult(
                guardrail_name=self.config.name,
                status=GuardrailStatus.PASSED,
                message="Validation passed"
            )
            
        except Exception as e:
            return GuardrailResult(
                guardrail_name=self.config.name,
                status=GuardrailStatus.ERROR,
                message=f"Validation error: {str(e)}"
            )


class RateLimitGuardrail(BaseGuardrail):
    """Simple rate limiting"""
    
    def __init__(self, config: GuardrailConfig):
        super().__init__(config)
        self.max_requests = config.params.get('max_requests', 100)
        self.time_window = config.params.get('time_window', 60)
        self.request_times = deque()
        self._lock = threading.Lock()
    
    async def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """Simple rate limit check"""
        try:
            current_time = time.time()
            
            with self._lock:
                # Remove old requests
                while self.request_times and current_time - self.request_times[0] > self.time_window:
                    self.request_times.popleft()
                
                # Check limit
                if len(self.request_times) >= self.max_requests:
                    return GuardrailResult(
                        guardrail_name=self.config.name,
                        status=GuardrailStatus.FAILED,
                        message=f"Rate limit exceeded: {len(self.request_times)} requests in {self.time_window}s"
                    )
                
                # Record request
                self.request_times.append(current_time)
            
            return GuardrailResult(
                guardrail_name=self.config.name,
                status=GuardrailStatus.PASSED,
                message="Rate limit check passed"
            )
            
        except Exception as e:
            return GuardrailResult(
                guardrail_name=self.config.name,
                status=GuardrailStatus.ERROR,
                message=f"Rate limit error: {str(e)}"
            )


class UIContentEscapingGuardrail(BaseGuardrail):
    """Basic XSS protection for ADK compliance"""
    
    def __init__(self, config: GuardrailConfig):
        super().__init__(config)
        self.html_entities = {
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '&': '&amp;',
        }
        
        self.dangerous_patterns = config.params.get('dangerous_patterns', [
            '<script', '</script>', '<iframe', 'javascript:', 'onclick=', 'onload='
        ])
    
    async def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """Basic UI content escaping"""
        try:
            # Get content from various sources
            content_sources = []
            
            data = context.get('data', {})
            for key, value in data.items():
                if isinstance(value, str) and len(value) > 10:
                    content_sources.append((f"data.{key}", value))
            
            if 'content' in context:
                content_sources.append(('content', str(context['content'])))
            
            issues_found = []
            
            for source_name, content in content_sources:
                if not content:
                    continue
                
                escaped_content = content
                
                # Check for dangerous patterns
                for pattern in self.dangerous_patterns:
                    if pattern.lower() in content.lower():
                        issues_found.append(f"{source_name}: dangerous pattern '{pattern}'")
                        escaped_content = escaped_content.replace(pattern, f'[REMOVED_{pattern.upper()}]')
                
                # Basic HTML escaping
                for char, entity in self.html_entities.items():
                    if char in escaped_content:
                        escaped_content = escaped_content.replace(char, entity)
                
                # Update context with escaped content
                if source_name.startswith('data.'):
                    field_name = source_name[5:]
                    context['data'][field_name] = escaped_content
                elif source_name in context:
                    context[source_name] = escaped_content
            
            if issues_found:
                return GuardrailResult(
                    guardrail_name=self.config.name,
                    status=GuardrailStatus.PASSED,
                    message=f"Content escaped. Issues fixed: {'; '.join(issues_found)}"
                )
            else:
                return GuardrailResult(
                    guardrail_name=self.config.name,
                    status=GuardrailStatus.PASSED,
                    message="No escaping required"
                )
                
        except Exception as e:
            return GuardrailResult(
                guardrail_name=self.config.name,
                status=GuardrailStatus.ERROR,
                message=f"UI escaping error: {str(e)}"
            )


class GuardrailManager:
    """Simple guardrail manager"""
    
    def __init__(self):
        self.guardrails: Dict[str, BaseGuardrail] = {}
        self._lock = threading.Lock()
        
        # Simple factory mapping
        self.guardrail_factories = {
            GuardrailType.VALIDATION: ValidationGuardrail,
            GuardrailType.RATE_LIMITING: RateLimitGuardrail,
            GuardrailType.UI_CONTENT_ESCAPING: UIContentEscapingGuardrail,
        }
    
    def add_guardrail(self, config: GuardrailConfig) -> bool:
        """Add a guardrail"""
        try:
            if config.type not in self.guardrail_factories:
                logger.error(f"Unknown guardrail type: {config.type}")
                return False
            
            guardrail_class = self.guardrail_factories[config.type]
            guardrail = guardrail_class(config)
            
            with self._lock:
                self.guardrails[config.name] = guardrail
            
            logger.info(f"Added guardrail: {config.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add guardrail {config.name}: {e}")
            return False
    
    async def check_all(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run all enabled guardrails"""
        results = []
        passed = 0
        failed = 0
        errors = 0
        
        try:
            # Get enabled guardrails
            guardrails_to_check = []
            with self._lock:
                guardrails_to_check = [(name, guardrail) for name, guardrail in self.guardrails.items() 
                                     if guardrail.config.enabled]
            
            # Run guardrails
            for name, guardrail in guardrails_to_check:
                try:
                    result = await guardrail.check(context)
                    results.append(result)
                    guardrail.update_stats()
                    
                    if result.status == GuardrailStatus.PASSED:
                        passed += 1
                    elif result.status == GuardrailStatus.FAILED:
                        failed += 1
                    else:
                        errors += 1
                        
                except Exception as e:
                    error_result = GuardrailResult(
                        guardrail_name=name,
                        status=GuardrailStatus.ERROR,
                        message=f"Execution error: {str(e)}"
                    )
                    results.append(error_result)
                    errors += 1
            
            # Check for strict mode failures
            has_strict_failures = any(
                result.status == GuardrailStatus.FAILED and 
                self.guardrails[result.guardrail_name].config.strict_mode
                for result in results
            )
            
            return {
                'status': "blocked" if has_strict_failures else "allowed",
                'passed': passed,
                'failed': failed,
                'errors': errors,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Error in guardrail check_all: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'results': []
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Simple stats"""
        with self._lock:
            return {
                'total_guardrails': len(self.guardrails),
                'enabled_guardrails': len([g for g in self.guardrails.values() if g.config.enabled]),
                'guardrail_checks': {name: g.check_count for name, g in self.guardrails.items()}
            }


# Global manager instance
_guardrail_manager = None


def get_guardrail_manager() -> GuardrailManager:
    """Get the global guardrail manager instance"""
    global _guardrail_manager
    if _guardrail_manager is None:
        _guardrail_manager = GuardrailManager()
    return _guardrail_manager


def initialize_default_guardrails():
    """Initialize basic guardrails for MVP"""
    manager = get_guardrail_manager()
    
    # Basic validation guardrail
    validation_config = GuardrailConfig(
        name="data_validation",
        type=GuardrailType.VALIDATION,
        enabled=True,
        strict_mode=True,
        custom_params={
            'max_field_length': 50000,
            'forbidden_patterns': ['<script>', 'javascript:', 'vbscript:', 'onload=', 'onerror=']
        }
    )
    manager.add_guardrail(validation_config)
    
    # Basic rate limiting
    rate_limit_config = GuardrailConfig(
        name="rate_limiter",
        type=GuardrailType.RATE_LIMITING,
        enabled=True,
        strict_mode=False,
        custom_params={
            'max_requests': 100,
            'time_window': 60
        }
    )
    manager.add_guardrail(rate_limit_config)
    
    # Basic UI content escaping (required for ADK)
    ui_escaping_config = GuardrailConfig(
        name="ui_content_escaper",
        type=GuardrailType.UI_CONTENT_ESCAPING,
        enabled=True,
        strict_mode=False,
        custom_params={
            'dangerous_patterns': [
                '<script', '</script>', '<iframe', 'javascript:', 'onclick=', 'onload=',
                'onerror=', 'onmouseover=', 'vbscript:', 'data:'
            ]
        }
    )
    manager.add_guardrail(ui_escaping_config)
    
    logger.info("Initialized basic guardrails for OpsMind MVP")


def with_guardrails():
    """Simple decorator for automatic guardrail checking"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            manager = get_guardrail_manager()
            
            # Simple context
            context = {
                'function_name': func.__name__,
                'args': args,
                'kwargs': kwargs,
                'data': kwargs.get('data', {})
            }
            
            # Run guardrails
            result = await manager.check_all(context)
            
            # Block if strict failures
            if result['status'] == 'blocked':
                logger.warning(f"Guardrails blocked execution for {func.__name__}")
                raise RuntimeError(f"Guardrails blocked execution: {result}")
            
            # Execute function
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator