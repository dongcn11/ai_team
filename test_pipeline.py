#!/usr/bin/env python
"""Quick test to verify pipeline stage configuration."""

import tempfile
from pathlib import Path
from ai_team.config import load

test_config = """
[agents]
pm_tool     = "opencode"
pm_model    = "opencode/qwen3.5-plus"
scrum_tool  = "opencode"
scrum_model = "opencode/qwen3.5-plus"

[output]
directory = "./output"

[timeouts]
claude_code = 600
opencode    = 600

[tech_stack]
backend  = "Python FastAPI + SQLModel + SQLite"
frontend = "React + TypeScript + Vite + TailwindCSS"

[pipeline.stages.pm]
enabled = true

[pipeline.stages.scrum]
enabled = false

[pipeline.stages.analyst]
enabled = true

[pipeline.stages.coding]
enabled = true

[pipeline.stages.leader]
enabled = false
"""

# Write to temp file
with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
    f.write(test_config)
    temp_path = f.name

try:
    cfg = load(temp_path)
    
    print("Pipeline stage configuration:")
    for stage_id, stage in cfg.pipeline_stages.items():
        status = "✅ enabled" if stage.enabled else "❌ disabled"
        print(f"  {stage_id:10} → {status}")
finally:
    Path(temp_path).unlink()
