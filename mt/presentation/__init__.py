"""
presentation — 表示层（领域对象 → 终端可读视图）

将 RenamePlan / ComicInfo 字段渲染为面向用户的输出，
依赖底层 infra.console（颜色、分隔线、高亮）与 core 数据模型，
使 infra.console 本身不再耦合领域结构。
"""
