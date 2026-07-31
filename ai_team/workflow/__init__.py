"""
Workflow Engine
===============
Bạn tự vẽ workflow (node + edge), engine chạy nó.

Luật xuyên suốt — xem `graph.py`:

    Mọi đường đi từ auto-trigger (slack_listener / cron / webhook) tới node
    `runtime = "claude"` phải đi qua ít nhất một `manual_gate`.

Lý do: subscription Claude dành cho người thật ngồi máy. Node Claude được
listener tự kích = truy cập tự động = khoá account. Gate đứng trước node Claude
biến mỗi lời gọi thành một cú bấm của bạn. Gate đứng *sau* (duyệt PR) bảo vệ
repo, không bảo vệ account — hai chuyện khác nhau, cần cả hai.

Node `runtime = "opencode"` không bị ràng buộc này, cứ để listener kích thoải mái.
"""

from ai_team.workflow.graph import (
    Graph,
    Node,
    Edge,
    ValidationResult,
    human_checkpoints_upstream_of,
    initial_state,
    parse,
    ready_nodes,
    unguarded_claude_nodes,
    validate,
)

__all__ = [
    "Graph",
    "Node",
    "Edge",
    "ValidationResult",
    "human_checkpoints_upstream_of",
    "initial_state",
    "parse",
    "ready_nodes",
    "unguarded_claude_nodes",
    "validate",
]
