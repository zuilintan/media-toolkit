"""
workflow — 高层工作流（目录扫描、批量执行、ComicInfo 写入、回退）

子模块:
    sourcefile — 源文件扫描 & 重命名执行（sourcefile 子命令）
    metadata   — ComicInfo.xml 生成 & 写入（metadata 子命令）
    drag       — 通用拖入循环 + 目录搬移（双子命令共用）
    session    — 操作记录 & 回退（仅 sourcefile 读取使用）
"""
