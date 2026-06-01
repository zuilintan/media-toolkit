"""文件归类业务（从 ps1 移植）。

工作流：拖入 path → :func:`~module.artifact.workflow.classify.path.path_to_author_name`
→ :func:`~module.artifact.workflow.classify.matcher.find_candidates`（精确 + 别名）
→ 0/1/N 候选交互选择 → :func:`~module.artifact.workflow.classify.ops.classify_one`
（:func:`~base.fs.merge_into` 搬移 + 打开目标 + iwara URL）。
"""
