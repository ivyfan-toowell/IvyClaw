"""subagents/schemas.py --  子代理的结构化输出schema """
from pydantic import BaseModel, Field

class ReviewResult(BaseModel):
    """Reviewer 子代理的结构化审查结论。
    用 response_format 后，主 Agent 收到的是符合此 schema 的 JSON，
    可以用代码判断 approved，而不是去解析一段自由文本。
    """

    approved: bool = Field(description="是否通过审查（True=可提PR，False=需返工）")
    summary:str = Field(description="一句话概括总体言论")
    issues:list[str] = Field(default_factory=list, description="发现的问题清单（无则空）")
    security_notes: list[str] = Field(
        default_factory=list, description="安全自查发现（如硬编码密钥、危险操作等）"
    )