/**
 * Notion Integration for Trae - 扩展入口
 * 提供 Notion API 操作命令
 */

import * as vscode from 'vscode';
import { NotionAuthHandler } from './oauthHandler';
import { NotionApi } from './notionApi';

let authHandler: NotionAuthHandler;

export function activate(context: vscode.ExtensionContext) {
    console.log('Notion Integration for Trae is now active');

    // 初始化授权处理器
    authHandler = new NotionAuthHandler(context);
    context.subscriptions.push(authHandler);

    // 注册命令

    // 1. 配置 Token
    context.subscriptions.push(
        vscode.commands.registerCommand('notion.configureToken', async () => {
            await authHandler.configureToken();
        })
    );

    // 2. 获取页面内容
    context.subscriptions.push(
        vscode.commands.registerCommand('notion.fetchPage', async () => {
            await fetchPageCommand();
        })
    );

    // 3. 更新页面属性
    context.subscriptions.push(
        vscode.commands.registerCommand('notion.updatePage', async () => {
            await updatePageCommand();
        })
    );

    // 4. 插入内容
    context.subscriptions.push(
        vscode.commands.registerCommand('notion.insertContent', async () => {
            await insertContentCommand();
        })
    );

    // 5. 列出页面
    context.subscriptions.push(
        vscode.commands.registerCommand('notion.listPages', async () => {
            await listPagesCommand();
        })
    );

    // 6. 搜索页面
    context.subscriptions.push(
        vscode.commands.registerCommand('notion.searchPages', async () => {
            await searchPagesCommand();
        })
    );

    // 7. 显示授权状态
    context.subscriptions.push(
        vscode.commands.registerCommand('notion.showStatus', async () => {
            await authHandler.showStatusDetails();
        })
    );
}

/**
 * 获取页面内容命令
 */
async function fetchPageCommand(): Promise<void> {
    const status = authHandler.getStatus();
    if (!status.isValid) {
        vscode.window.showWarningMessage('请先配置有效的 Notion Integration Token');
        return;
    }

    const config = vscode.workspace.getConfiguration('notion');
    let pageId = config.get<string>('defaultPageId', '');

    // 如果没有默认页面，让用户选择
    if (!pageId) {
        const pages = await authHandler.getApi().listPages();
        const selected = await vscode.window.showQuickPick(
            pages.map(p => ({
                label: p.title,
                description: p.id
            })),
            { placeHolder: '选择要获取的页面' }
        );

        if (!selected) {
            return;
        }
        pageId = selected.description || '';
    }

    try {
        const page = await authHandler.getApi().fetchPage(pageId);
        
        // 显示页面内容
        const doc = await vscode.workspace.openTextDocument({
            content: formatPageContent(page),
            language: 'markdown'
        });
        await vscode.window.showTextDocument(doc);
        
        vscode.window.showInformationMessage(`已获取页面: ${page.title}`);
    } catch (error) {
        vscode.window.showErrorMessage(`获取页面失败: ${error}`);
    }
}

/**
 * 更新页面属性命令
 */
async function updatePageCommand(): Promise<void> {
    const status = authHandler.getStatus();
    if (!status.isValid) {
        vscode.window.showWarningMessage('请先配置有效的 Notion Integration Token');
        return;
    }

    const config = vscode.workspace.getConfiguration('notion');
    let pageId = config.get<string>('defaultPageId', '');

    if (!pageId) {
        vscode.window.showWarningMessage('请先设置默认页面');
        return;
    }

    // 获取当前页面信息
    const page = await authHandler.getApi().fetchPage(pageId);
    
    // 让用户选择要更新的属性
    const propertyNames = Object.keys(page.properties);
    const selectedProp = await vscode.window.showQuickPick(propertyNames, {
        placeHolder: '选择要更新的属性'
    });

    if (!selectedProp) {
        return;
    }

    // 输入新值
    const newValue = await vscode.window.showInputBox({
        prompt: `输入 ${selectedProp} 的新值`,
        placeHolder: '新值'
    });

    if (!newValue) {
        return;
    }

    try {
        const success = await authHandler.getApi().updatePageProperties(pageId, {
            [selectedProp]: newValue
        });

        if (success) {
            vscode.window.showInformationMessage(`页面属性 ${selectedProp} 已更新`);
        } else {
            vscode.window.showErrorMessage('更新失败');
        }
    } catch (error) {
        vscode.window.showErrorMessage(`更新页面失败: ${error}`);
    }
}

/**
 * 插入内容命令
 */
async function insertContentCommand(): Promise<void> {
    const status = authHandler.getStatus();
    if (!status.isValid) {
        vscode.window.showWarningMessage('请先配置有效的 Notion Integration Token');
        return;
    }

    const config = vscode.workspace.getConfiguration('notion');
    let pageId = config.get<string>('defaultPageId', '');

    if (!pageId) {
        vscode.window.showWarningMessage('请先设置默认页面');
        return;
    }

    // 获取当前编辑器内容作为要插入的内容
    const editor = vscode.window.activeTextEditor;
    let content = '';

    if (editor) {
        content = editor.document.getText();
    } else {
        // 如果没有编辑器，让用户输入
        content = await vscode.window.showInputBox({
            prompt: '输入要插入的内容（支持 Markdown 格式）',
            placeHolder: '# 标题\n内容...'
        }) || '';
    }

    if (!content) {
        vscode.window.showWarningMessage('内容不能为空');
        return;
    }

    // 选择插入位置
    const position = await vscode.window.showQuickPick(['末尾', '开头'], {
        placeHolder: '选择插入位置'
    });

    if (!position) {
        return;
    }

    try {
        const success = await authHandler.getApi().insertContent(
            pageId,
            content,
            position === '末尾' ? 'end' : 'start'
        );

        if (success) {
            vscode.window.showInformationMessage('内容已插入到页面');
        } else {
            vscode.window.showErrorMessage('插入失败');
        }
    } catch (error) {
        vscode.window.showErrorMessage(`插入内容失败: ${error}`);
    }
}

/**
 * 列出页面命令
 */
async function listPagesCommand(): Promise<void> {
    const status = authHandler.getStatus();
    if (!status.isValid) {
        vscode.window.showWarningMessage('请先配置有效的 Notion Integration Token');
        return;
    }

    try {
        const pages = await authHandler.getApi().listPages();
        
        // 显示页面列表
        const selected = await vscode.window.showQuickPick(
            pages.map(p => ({
                label: p.title,
                description: p.id,
                detail: p.url
            })),
            { placeHolder: '可访问的 Notion 页面列表' }
        );

        if (selected) {
            // 询问是否设置为默认页面
            const action = await vscode.window.showInformationMessage(
                `页面: ${selected.label}`,
                '设置为默认页面',
                '获取内容'
            );

            if (action === '设置为默认页面') {
                const config = vscode.workspace.getConfiguration('notion');
                await config.update('defaultPageId', selected.description, vscode.ConfigurationTarget.Global);
                vscode.window.showInformationMessage(`默认页面已设置为: ${selected.label}`);
            } else if (action === '获取内容') {
                const page = await authHandler.getApi().fetchPage(selected.description || '');
                const doc = await vscode.workspace.openTextDocument({
                    content: formatPageContent(page),
                    language: 'markdown'
                });
                await vscode.window.showTextDocument(doc);
            }
        }
    } catch (error) {
        vscode.window.showErrorMessage(`获取页面列表失败: ${error}`);
    }
}

/**
 * 搜索页面命令
 */
async function searchPagesCommand(): Promise<void> {
    const status = authHandler.getStatus();
    if (!status.isValid) {
        vscode.window.showWarningMessage('请先配置有效的 Notion Integration Token');
        return;
    }

    const query = await vscode.window.showInputBox({
        prompt: '输入搜索关键词',
        placeHolder: '页面名称关键词'
    });

    if (!query) {
        return;
    }

    try {
        const pages = await authHandler.getApi().searchPages(query);
        
        if (pages.length === 0) {
            vscode.window.showInformationMessage('没有找到匹配的页面');
            return;
        }

        const selected = await vscode.window.showQuickPick(
            pages.map(p => ({
                label: p.title,
                description: p.id,
                detail: p.url
            })),
            { placeHolder: `搜索结果: ${pages.length} 个页面` }
        );

        if (selected) {
            const page = await authHandler.getApi().fetchPage(selected.description || '');
            const doc = await vscode.workspace.openTextDocument({
                content: formatPageContent(page),
                language: 'markdown'
            });
            await vscode.window.showTextDocument(doc);
        }
    } catch (error) {
        vscode.window.showErrorMessage(`搜索页面失败: ${error}`);
    }
}

/**
 * 格式化页面内容为 Markdown
 */
function formatPageContent(page: any): string {
    let content = `# ${page.title}\n\n`;
    content += `**页面ID**: ${page.id}\n`;
    content += `**URL**: ${page.url}\n\n`;
    
    if (page.content) {
        content += `---\n\n`;
        content += page.content;
    }
    
    return content;
}

export function deactivate() {
    console.log('Notion Integration for Trae is now deactivated');
}