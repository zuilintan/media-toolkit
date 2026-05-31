"""module.artifact.workflow.classify — 文件归类业务（从 ps1 移植）

工作流: 拖入 path → 解析作者名 → 候选目录匹配（精确 + 别名）→
       0/1/N 候选交互选择 → merge_into 搬移 → 打开目标 + iwara URL
"""
