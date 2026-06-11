/**
 * Notion 授权处理器
 * 使用 Integration Token 方式（无需 OAuth）
 */

import * as vscode from 'vscode';
import { NotionApi } from './notionApi';

export interface AuthStatus {
    isConfigured: boolean;
    isValid: boolean;
    userName?: string;
    userId?: string;
    lastChecked?: Date;
}

export class NotionAuthHandler {
    private context: vscode.ExtensionContext;
    private api: NotionApi | null = null;
    private statusBarItem: vscode.StatusBarItem;
    private authStatus: AuthStatus = {
        isConfigured: false,
        isValid: false
    };

    constructor(context: vscode.ExtensionContext) {
        this.context = context;
        
        // 创建状态栏项
        this.statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
        this.statusBarItem.command = 'notion.showStatus';
        this.statusBarItem.text = '$(book) Notion: 未配置';
        this.statusBarItem.show();
        
        // 初始化时检查配置
        this.checkConfiguration();
    }

    /**
     * 检查当前配置状态
     */
    async checkConfiguration(): Promise<AuthStatus> {
        const config = vscode.workspace.getConfiguration('notion');
        const token = config.get<string>('integrationToken', '');
        
        if (!token || token.trim() === '') {
            this.authStatus = {
                isConfigured: false,
                isValid: false
            };
            this.updateStatusBar('未配置', false);
            return this.authStatus;
        }
        
        // 创建 API 实例并测试连接
        this.api = new NotionApi({
            token: token,
            timeout: config.get<number>('timeout', 60000),
            retryCount: config.get<number>('retryCount', 5),
            autoRetry: config.get<boolean>('autoRetry', true),
            proxy: config.get<string>('proxy', '') || process.env.HTTPS_PROXY || process.env.HTTP_PROXY || '',
            cacheEnabled: config.get<boolean>('cacheEnabled', true)
        });
        
        try {
            const isValid = await this.api.testConnection();
            
            if (isValid) {
                const user = await this.api.getCurrentUser();
                this.authStatus = {
                    isConfigured: true,
                    isValid: true,
                    userName: user.name,
                    userId: user.id,
                    lastChecked: new Date()
                };
                this.updateStatusBar('已授权', true);
            } else {
                this.authStatus = {
                    isConfigured: true,
                    isValid: false,
                    lastChecked: new Date()
                };
                this.updateStatusBar('Token无效', false);
            }
        } catch (error) {
            this.authStatus = {
                isConfigured: true,
                isValid: false,
                lastChecked: new Date()
            };
            this.updateStatusBar('连接失败', false);
        }
        
        return this.authStatus;
    }

    /**
     * 配置 Integration Token
     */
    async configureToken(): Promise<boolean> {
        // 显示输入框让用户输入 Token
        const token = await vscode.window.showInputBox({
            prompt: '请输入 Notion Integration Token',
            placeHolder: 'secret_xxxxxxxxxxxx',
            password: true,
            ignoreFocusOut: true,
            validateInput: (value) => {
                if (!value || value.trim() === '') {
                    return 'Token 不能为空';
                }
                if (!value.startsWith('secret_')) {
                    return 'Token 格式错误，应以 secret_ 开头';
                }
                return null;
            }
        });
        
        if (!token) {
            return false;
        }
        
        // 保存到配置
        const config = vscode.workspace.getConfiguration('notion');
        await config.update('integrationToken', token, vscode.ConfigurationTarget.Global);
        
        // 测试新 Token
        const status = await this.checkConfiguration();
        
        if (status.isValid) {
            vscode.window.showInformationMessage(`Notion 授权成功！用户: ${status.userName}`);
            return true;
        } else {
            vscode.window.showErrorMessage('Notion Token 无效，请检查后重新配置');
            return false;
        }
    }

    /**
     * 配置默认页面 ID
     */
    async configureDefaultPage(): Promise<boolean> {
        // 先检查是否已授权
        if (!this.authStatus.isValid) {
            vscode.window.showWarningMessage('请先配置有效的 Notion Integration Token');
            return false;
        }
        
        // 显示可访问的页面列表
        const pages = await this.getApi().listPages();
        
        if (pages.length === 0) {
            vscode.window.showWarningMessage('没有找到可访问的 Notion 页面');
            return false;
        }
        
        const selected = await vscode.window.showQuickPick(
            pages.map(p => ({
                label: p.title,
                description: p.id,
                detail: p.url
            })),
            {
                placeHolder: '选择默认操作的页面',
                ignoreFocusOut: true
            }
        );
        
        if (!selected) {
            return false;
        }
        
        // 保存到配置
        const config = vscode.workspace.getConfiguration('notion');
        await config.update('defaultPageId', selected.description, vscode.ConfigurationTarget.Global);
        
        vscode.window.showInformationMessage(`默认页面已设置为: ${selected.label}`);
        return true;
    }

    /**
     * 获取 API 实例
     */
    getApi(): NotionApi {
        if (!this.api) {
            throw new Error('Notion API 未初始化，请先配置 Token');
        }
        return this.api;
    }

    /**
     * 获取授权状态
     */
    getStatus(): AuthStatus {
        return this.authStatus;
    }

    /**
     * 显示授权状态详情
     */
    async showStatusDetails(): Promise<void> {
        const status = this.authStatus;
        
        let message = '';
        if (!status.isConfigured) {
            message = 'Notion Integration Token 未配置\n\n请运行 "Notion: Configure Integration Token" 命令进行配置';
        } else if (!status.isValid) {
            message = 'Notion Integration Token 无效\n\n请检查 Token 是否正确，或是否已过期';
        } else {
            message = `Notion 授权状态: 有效\n\n用户: ${status.userName || 'Unknown'}\n用户ID: ${status.userId || 'Unknown'}\n检查时间: ${status.lastChecked?.toLocaleString() || 'Unknown'}`;
        }
        
        const action = await vscode.window.showInformationMessage(message, 
            status.isConfigured ? '重新配置' : '配置Token',
            '查看帮助'
        );
        
        if (action === '配置Token' || action === '重新配置') {
            await this.configureToken();
        } else if (action === '查看帮助') {
            vscode.env.openExternal(vscode.Uri.parse('https://developers.notion.com/docs/getting-started'));
        }
    }

    /**
     * 更新状态栏显示
     */
    private updateStatusBar(text: string, isValid: boolean): void {
        const icon = isValid ? '$(check)' : '$(warning)';
        this.statusBarItem.text = `$(book) Notion: ${text}`;
        this.statusBarItem.tooltip = isValid 
            ? 'Notion Integration 已授权' 
            : '点击查看授权状态详情';
    }

    /**
     * 清理资源
     */
    dispose(): void {
        this.statusBarItem.dispose();
    }
}