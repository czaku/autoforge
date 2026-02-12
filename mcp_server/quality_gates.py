"""
Quality Gates Enforcement Module
=================================

Provides mechanical enforcement of build/test/lint requirements
before features can be marked as passing.

This prevents agents from marking features complete without
actually verifying they work.
"""

import json
import os
import subprocess
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class QualityGate:
    """Definition of a single quality gate."""
    name: str
    command: str
    required: bool = True
    timeout: int = 300  # seconds
    working_dir: Optional[str] = None
    env_vars: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QualityGate':
        return cls(
            name=data['name'],
            command=data['command'],
            required=data.get('required', True),
            timeout=data.get('timeout', 300),
            working_dir=data.get('working_dir'),
            env_vars=data.get('env_vars', {})
        )


@dataclass
class GateResult:
    """Result of running a quality gate."""
    name: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class QualityGateManager:
    """Manages and executes quality gates."""
    
    DEFAULT_GATES = [
        QualityGate(
            name="api_build",
            command="cd api && pnpm build",
            required=True,
            timeout=300
        ),
        QualityGate(
            name="api_test",
            command="cd api && pnpm test --passWithNoTests",
            required=True,
            timeout=600
        ),
        QualityGate(
            name="api_lint",
            command="cd api && pnpm lint",
            required=False,  # Can be made stricter later
            timeout=120
        ),
    ]
    
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config_file = project_dir / ".autoforge" / "quality_gates.yaml"
        self.gates = self._load_gates()
    
    def _load_gates(self) -> List[QualityGate]:
        """Load gates from config or use defaults."""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    config = yaml.safe_load(f)
                return [QualityGate.from_dict(g) for g in config.get('gates', [])]
            except Exception as e:
                print(f"Warning: Failed to load quality gates config: {e}")
                return self.DEFAULT_GATES
        return self.DEFAULT_GATES
    
    def run_gate(self, gate: QualityGate) -> GateResult:
        """Execute a single quality gate."""
        import time
        
        start_time = time.time()
        
        # Determine working directory
        if gate.working_dir:
            cwd = self.project_dir / gate.working_dir
        else:
            cwd = self.project_dir
        
        # Prepare environment
        env = os.environ.copy()
        env.update(gate.env_vars)
        
        try:
            result = subprocess.run(
                gate.command,
                shell=True,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=gate.timeout
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return GateResult(
                name=gate.name,
                passed=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
                stderr=result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
                duration_ms=duration_ms
            )
            
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return GateResult(
                name=gate.name,
                passed=False,
                exit_code=-1,
                stdout="",
                stderr=f"Timeout after {gate.timeout} seconds",
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return GateResult(
                name=gate.name,
                passed=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms
            )
    
    def run_all_gates(self) -> tuple[bool, List[GateResult]]:
        """
        Run all quality gates.
        
        Returns:
            (all_passed, results)
        """
        results = []
        all_passed = True
        
        for gate in self.gates:
            result = self.run_gate(gate)
            results.append(result)
            
            if gate.required and not result.passed:
                all_passed = False
                # Still run remaining gates to get full report
        
        return all_passed, results
    
    def get_summary(self, results: List[GateResult]) -> Dict[str, Any]:
        """Generate a summary of gate results."""
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        
        required_failed = [
            r.name for r in results 
            if not r.passed and any(g.name == r.name and g.required for g in self.gates)
        ]
        
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "all_passed": failed == 0 or len(required_failed) == 0,
            "required_failed": required_failed,
            "gates": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "exit_code": r.exit_code,
                    "duration_ms": r.duration_ms,
                    "error": r.stderr[:500] if not r.passed else None
                }
                for r in results
            ]
        }


def run_quality_gates(project_dir: Path) -> tuple[bool, Dict[str, Any]]:
    """
    Convenience function to run all quality gates and get summary.
    
    Returns:
        (all_required_passed, summary_dict)
    """
    manager = QualityGateManager(project_dir)
    all_passed, results = manager.run_all_gates()
    summary = manager.get_summary(results)
    return all_passed, summary
