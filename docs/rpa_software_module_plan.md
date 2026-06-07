# RPA 软件功能模块规划

## 1. 产品定位

本软件定位为本地 Windows 桌面业务工具，第一阶段提供“Excel 驱动 EXE 软件查询/录入”功能，后续继续扩展“对账”功能。

核心目标不是做一次性脚本，而是做一个可持续扩展的软件平台：

- 支持导入 Excel
- 支持配置目标 EXE 软件
- 支持按行执行查询、录入、保存等自动化任务
- 支持写回执行结果
- 支持失败重试、日志、截图留证
- 后续支持对账、差异分析、结果导出

## 2. 模块规划

### 2.1 功能导航

建议软件主界面先设计为以下模块：

1. 首页/任务中心
2. EXE 自动填单
3. 对账管理
4. 执行记录
5. 配置中心
6. 日志与截图

第一阶段重点开发：

- EXE 自动填单
- 执行记录
- 配置中心

第二阶段开发：

- 对账管理
- 差异处理
- 对账报表导出

## 3. 第一阶段：EXE 自动填单模块

### 3.1 用户操作流程

1. 选择 Excel 文件
2. 选择业务模板
3. 预览 Excel 数据
4. 校验必填字段
5. 点击开始执行
6. 软件自动打开或连接目标 EXE
7. 按 Excel 每一行查询、录入、保存
8. 实时显示执行进度
9. 执行结果写回 Excel
10. 生成日志和失败截图

### 3.2 页面功能

自动填单页面建议包含：

- Excel 文件选择
- Sheet 选择
- 字段映射配置
- 任务模式选择：全部执行、仅执行待处理、仅重试失败
- 执行按钮：开始、暂停、继续、停止
- 执行进度：总数、成功、失败、跳过、当前行
- 实时日志窗口
- 结果导出按钮

### 3.3 Excel 字段建议

基础字段：

- 序号
- 单据类型
- 查询条件
- 客户名称
- 商品名称
- 数量
- 单价
- 金额
- 备注

系统写回字段：

- 执行状态
- 执行时间
- 失败原因
- 系统返回信息
- 截图路径
- 任务批次号

执行状态建议固定为：

- 待处理
- 处理中
- 成功
- 失败
- 跳过

## 4. 第二阶段：对账模块

### 4.1 对账目标

对账模块用于比较两个或多个数据来源之间的差异，例如：

- Excel A 与 Excel B 对账
- 系统导出表与业务表对账
- 采购单与入库单对账
- 订单金额、数量、客户、商品等字段核对

### 4.2 对账流程

1. 导入源文件 A
2. 导入目标文件 B
3. 选择对账模板
4. 配置匹配键，例如单号、客户、商品编码
5. 配置比较字段，例如数量、金额、价格
6. 点击开始对账
7. 输出一致、差异、缺失、多余数据
8. 导出对账结果 Excel

### 4.3 对账结果分类

- 完全一致
- 源文件有、目标文件无
- 目标文件有、源文件无
- 数量不一致
- 金额不一致
- 商品信息不一致
- 重复数据

## 5. 技术架构建议

### 5.1 推荐技术栈

如果目标是做 Windows 本地软件，推荐：

- 界面：PySide6
- 自动化控制：pywinauto + uiautomation
- Excel 处理：openpyxl
- 数据存储：SQLite
- 配置文件：YAML 或 JSON
- 日志：Python logging
- 打包：PyInstaller

### 5.2 为什么这样选

PySide6 适合做本地 Windows 桌面软件，能打包成 EXE。

pywinauto 和 uiautomation 适合控制第三方 EXE 软件界面。

openpyxl 适合读取、修改、写回 Excel 文件。

SQLite 适合保存任务记录、模板配置、执行日志索引，不需要额外安装数据库。

## 6. 建议项目结构

```text
RPA/
  app/
    main.py
    ui/
      main_window.py
      task_center_page.py
      auto_fill_page.py
      reconciliation_page.py
      settings_page.py
    core/
      excel_service.py
      task_service.py
      log_service.py
      screenshot_service.py
    automation/
      app_connector.py
      exe_controller.py
      workflows/
        base_workflow.py
        auto_fill_workflow.py
    reconciliation/
      matcher.py
      comparer.py
      report_writer.py
    storage/
      database.py
      models.py
    config/
      settings.py
  data/
    templates/
  output/
  logs/
  screenshots/
  docs/
```

## 7. 核心数据模型

### 7.1 任务记录

- task_id
- task_name
- module_type
- source_file
- status
- total_count
- success_count
- failed_count
- skipped_count
- started_at
- finished_at

### 7.2 行执行记录

- row_id
- task_id
- excel_row_number
- business_key
- status
- error_message
- system_message
- screenshot_path
- executed_at

### 7.3 模板配置

- template_id
- template_name
- module_type
- field_mapping
- required_fields
- workflow_config
- created_at
- updated_at

## 8. 自动填单执行流程

```text
选择Excel
  ↓
读取Sheet
  ↓
校验字段
  ↓
创建任务批次
  ↓
连接目标EXE
  ↓
逐行执行
  ↓
写回Excel状态
  ↓
保存任务记录
  ↓
输出日志和截图
```

## 9. 稳定性设计

### 9.1 断点续跑

每处理一行前先写回“处理中”，处理完成后写“成功”或“失败”。

如果软件中途关闭或电脑异常，下一次启动可以选择：

- 继续处理待处理行
- 重试失败行
- 从指定行开始

### 9.2 失败留证

每行失败时保存：

- 失败原因
- 当前窗口截图
- 当前任务日志
- Excel 行号

### 9.3 防重复录入

录入前尽量先查询是否已存在相同单据或业务主键。

如果系统无法查询重复，则至少在 Excel 中记录：

- 任务批次号
- 系统返回编号
- 已提交状态

## 10. 开发里程碑

### 里程碑 1：软件骨架

- 创建桌面软件窗口
- 完成左侧导航
- 完成首页、自动填单、对账、设置页面占位
- 完成基础配置读取

### 里程碑 2：Excel 能力

- 选择 Excel
- 读取 Sheet
- 预览数据
- 校验必填字段
- 写回执行状态

### 里程碑 3：EXE 控制验证

- 打开目标软件
- 连接主窗口
- 自动输入测试内容
- 自动点击查询或保存按钮
- 保存截图

### 里程碑 4：完整自动填单

- 按 Excel 逐行执行
- 支持暂停、停止、失败跳过
- 写回结果
- 生成日志

### 里程碑 5：对账模块

- 导入两份 Excel
- 配置匹配字段
- 比较数量、金额等字段
- 输出差异结果
- 导出对账报告

## 11. 下一步需要确认的信息

正式开发前，需要确认：

1. 软件界面使用中文还是中英文都要支持
2. 目标 EXE 软件名称和安装路径
3. Excel 样例文件
4. 人工操作流程截图或录屏
5. 对账模块未来要对哪两类数据
6. 是否需要账号权限、多用户、操作员记录

