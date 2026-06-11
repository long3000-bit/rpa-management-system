# Notion Integration for Trae

Trae IDE 的 Notion API 集成插件，使用 Integration Token 方式授权（无需 OAuth）。

## 功能特性

- ✅ 使用 Integration Token 授权（永久有效，无需每天授权）
- ✅ 获取页面内容
- ✅ 更新页面属性
- ✅ 插入内容到页面
- ✅ 搜索页面
- ✅ 列出可访问的页面
- ✅ 状态栏显示授权状态
- ✅ 自动重试机制

## 安装步骤

### 1. 创建 Notion Integration

1. 访问 [Notion Integrations](https://www.notion.so/my-integrations)
2. 点击 **"New integration"**
3. 填写名称（如：`Trae Integration`）
4. 选择关联的工作区
5. 点击 **"Submit"**
6. 复制生成的 **Internal Integration Token**（格式：`secret_xxx...`）

### 2. 授权页面访问

在你要操作的 Notion 页面中：

1. 点击页面右上角 **"..."**
2. 选择 **"Add connections"**
3. 选择你创建的 Integration
4. 确认授权

### 3. 安装插件

#### 方式A：编译安装

```bash
cd d:\project\RPA\extensions\notion-trae-extension
npm install
npm run compile
```

然后在 Trae IDE 中：
1. 打开扩展面板
2. 点击 **"..."** → **"Install from VSIX..."**
3. 选择编译后的 `.vsix` 文件

#### 方式B：开发模式

```bash
cd d:\project\RPA\extensions\notion-trae-extension
npm install
npm run watch
```

在 Trae IDE 中按 `F5` 启动调试模式。

### 4. 配置 Token

在 Trae IDE 中：

1. 按 `Ctrl+Shift+P` 打开命令面板
2. 输入 **"Notion: Configure Integration Token"**
3. 输入你的 Integration Token（`secret_xxx...`）
4. 等待验证成功

## 使用命令

| 命令 | 功能 |
|------|------|
| `Notion: Configure Integration Token` | 配置授权 Token |
| `Notion: Fetch Page Content` | 获取页面内容 |
| `Notion: Update Page Properties` | 更新页面属性 |
| `Notion: Insert Content to Page` | 插入内容 |
| `Notion: List Available Pages` | 列出页面 |
| `Notion: Search Pages` | 搜索页面 |
| `Notion: Show Authorization Status` | 显示授权状态 |

## 配置项

在 Trae IDE 设置中可以配置：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `notion.integrationToken` | Integration Token | 空 |
| `notion.defaultPageId` | 默认操作页面 ID | 空 |
| `notion.autoRetry` | 自动重试失败请求 | `true` |
| `notion.retryCount` | 重试次数 | `3` |
| `notion.timeout` | 请求超时时间（毫秒） | `30000` |

## 状态栏

插件会在状态栏显示授权状态：

- `$(book) Notion: 未配置` - Token 未配置
- `$(book) Notion: Token无效` - Token 无效
- `$(check) Notion: 已授权` - 授权成功

## 与 MCP OAuth 的区别

| 特性 | MCP OAuth | Integration Token |
|------|-----------|------------------|
| 授权方式 | OAuth 流程 | API Token |
| 有效期 | 需定期刷新 | 永久有效 |
| 每日授权 | 可能需要 | 不需要 |
| 网络依赖 | 授权时需要 | 仅 API 调用需要 |
| 失败风险 | fetch failed 可能 | 稳定 |

## 常见问题

### Q: Token 格式是什么？

A: Integration Token 格式为 `secret_xxxxxxxxxxxx`，在创建 Integration 时生成。

### Q: 为什么看不到某些页面？

A: 需要在每个页面中手动添加 Integration 连接：
1. 页面右上角 **"..."**
2. **"Add connections"**
3. 选择你的 Integration

### Q: Token 会过期吗？

A: Integration Token 永久有效，除非你手动删除 Integration 或撤销授权。

### Q: 如何获取页面 ID？

A: 页面 ID 在页面 URL 中，格式如：
```
https://www.notion.so/username/PageTitle-1234567890abcdef
                                      ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
                                      这就是页面 ID（去掉连字符）
```

## 开发说明

### 项目结构

```
notion-trae-extension/
├── src/
│   ├── extension.ts      # 扩展入口
│   ├── notionApi.ts      # Notion API 封装
│   └── oauthHandler.ts   # 授权处理
├── package.json          # 扩展配置
├── tsconfig.json         # TypeScript 配置
└── README.md             # 使用说明
```

### 编译

```bash
npm run compile
```

### 打包 VSIX

```bash
npm install -g @vscode/vsce
vsce package
```

## 许可证

MIT License