# RPA Management System

一个基于 Python + PySide6 的桌面业务管理系统，聚合了以下能力：

- RPA 机器人执行
- 药师帮智能采购
- 云药店库存同步与对比
- 药师帮入库对账
- 用户、权限、配置与日志管理

## 项目结构

- `app/`：主程序与业务逻辑
  - `app/main.py`：应用入口
  - `app/ui/`：桌面界面
  - `app/core/`：核心业务服务
  - `app/storage/`：数据库与初始化逻辑
- `docs/`：项目设计与方案文档
- `scripts/`：权限与治理检查脚本
- `tests/`：功能测试

## 环境要求

- Python 3.10+
- Windows
- PySide6

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行方式

```bash
python app/main.py
```

## 说明

本项目为本地 Windows 桌面工具，运行时会依赖本地数据库、配置文件与目标 EXE/浏览器环境。请先确认相关环境可用后再执行。

## 备注

当前仓库已将源码与文档上传到 GitHub；运行时生成的日志、数据库、缓存等文件不会被提交。
