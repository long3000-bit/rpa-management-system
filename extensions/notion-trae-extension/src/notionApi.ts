/**
 * Notion API 封装
 * 提供 fetch、update、insert、search 等操作
 */

import axios, { AxiosInstance, AxiosError } from 'axios';

export interface NotionPage {
    id: string;
    title: string;
    url: string;
    properties: Record<string, any>;
    content?: string;
}

export interface NotionBlock {
    type: string;
    content: string;
    children?: NotionBlock[];
}

export interface NotionApiConfig {
    token: string;
    timeout?: number;
    retryCount?: number;
    autoRetry?: boolean;
    proxy?: string;  // 代理地址，如 http://127.0.0.1:7890
    cacheEnabled?: boolean;  // 是否启用缓存
}

export class NotionApi {
    private client: AxiosInstance;
    private config: NotionApiConfig;
    private baseUrl = 'https://api.notion.com/v1';
    private apiVersion = '2022-06-28';
    private cache: Map<string, { data: any; timestamp: number }> = new Map();
    private requestQueue: Promise<void> = Promise.resolve();
    private lastRequestTime: number = 0;
    private minRequestInterval: number = 350; // Notion API 限流：3 requests/second

    constructor(config: NotionApiConfig) {
        this.config = {
            timeout: 60000,  // 增加超时时间到 60 秒
            retryCount: 5,   // 增加重试次数到 5 次
            autoRetry: true,
            proxy: process.env.HTTPS_PROXY || process.env.HTTP_PROXY || '',
            cacheEnabled: true,
            ...config
        };

        // 配置 axios 客户端
        const axiosConfig: any = {
            baseURL: this.baseUrl,
            timeout: this.config.timeout,
            headers: {
                'Authorization': `Bearer ${this.config.token}`,
                'Notion-Version': this.apiVersion,
                'Content-Type': 'application/json'
            }
        };

        // 如果有代理，配置代理
        if (this.config.proxy) {
            const proxyUrl = new URL(this.config.proxy);
            axiosConfig.proxy = {
                host: proxyUrl.hostname,
                port: parseInt(proxyUrl.port),
                protocol: proxyUrl.protocol.replace(':', '')
            };
            console.log(`Using proxy: ${this.config.proxy}`);
        }

        this.client = axios.create(axiosConfig);
    }

    /**
     * 测试 Token 是否有效
     */
    async testConnection(): Promise<boolean> {
        try {
            const response = await this.client.get('/users/me');
            return response.status === 200;
        } catch (error) {
            return false;
        }
    }

    /**
     * 获取当前用户信息
     */
    async getCurrentUser(): Promise<any> {
        return this.requestWithRetry('get', '/users/me');
    }

    /**
     * 获取页面内容
     */
    async fetchPage(pageId: string): Promise<NotionPage> {
        // 获取页面基本信息
        const pageData = await this.requestWithRetry('get', `/pages/${pageId}`);
        
        // 获取页面内容块
        const blocksData = await this.requestWithRetry('get', `/blocks/${pageId}/children`);
        
        // 提取标题
        const title = this.extractTitle(pageData);
        
        // 提取内容
        const content = this.extractContent(blocksData.results || []);
        
        return {
            id: pageId,
            title: title,
            url: pageData.url,
            properties: pageData.properties,
            content: content
        };
    }

    /**
     * 更新页面属性
     */
    async updatePageProperties(pageId: string, properties: Record<string, any>): Promise<boolean> {
        try {
            await this.requestWithRetry('patch', `/pages/${pageId}`, { properties });
            return true;
        } catch (error) {
            return false;
        }
    }

    /**
     * 插入内容到页面末尾
     */
    async insertContent(pageId: string, content: string, position: 'end' | 'start' = 'end'): Promise<boolean> {
        try {
            const blocks = this.parseContentToBlocks(content);
            
            await this.requestWithRetry('patch', `/blocks/${pageId}/children`, {
                children: blocks,
                after: position === 'end' ? undefined : null
            });
            
            return true;
        } catch (error) {
            return false;
        }
    }

    /**
     * 搜索页面
     */
    async searchPages(query: string): Promise<NotionPage[]> {
        const response = await this.requestWithRetry('post', '/search', {
            query: query,
            filter: {
                property: 'object',
                value: 'page'
            }
        });

        return response.results.map((page: any) => ({
            id: page.id,
            title: this.extractTitle(page),
            url: page.url,
            properties: page.properties
        }));
    }

    /**
     * 列出所有可访问的页面
     */
    async listPages(): Promise<NotionPage[]> {
        const response = await this.requestWithRetry('post', '/search', {
            filter: {
                property: 'object',
                value: 'page'
            },
            page_size: 100
        });

        return response.results.map((page: any) => ({
            id: page.id,
            title: this.extractTitle(page),
            url: page.url,
            properties: page.properties
        }));
    }

    /**
     * 创建新页面
     */
    async createPage(parentId: string, title: string, content?: string): Promise<NotionPage | null> {
        try {
            const pageData: any = {
                parent: { page_id: parentId },
                properties: {
                    title: {
                        title: [
                            {
                                type: 'text',
                                text: { content: title }
                            }
                        ]
                    }
                }
            };

            const response = await this.requestWithRetry('post', '/pages', pageData);
            
            // 如果有内容，插入内容块
            if (content) {
                await this.insertContent(response.id, content);
            }

            return {
                id: response.id,
                title: title,
                url: response.url,
                properties: response.properties
            };
        } catch (error) {
            return null;
        }
    }

    /**
     * 带重试、限流控制和缓存的请求
     */
    private async requestWithRetry(method: string, url: string, data?: any): Promise<any> {
        // 检查缓存（仅对 GET 请求）
        const cacheKey = `${method}:${url}`;
        if (method === 'get' && this.config.cacheEnabled) {
            const cached = this.cache.get(cacheKey);
            if (cached && Date.now() - cached.timestamp < 300000) { // 5分钟缓存
                console.log(`Using cached data for ${url}`);
                return cached.data;
            }
        }

        // 请求队列控制，避免 API 限流
        await this.waitForRequestSlot();

        let lastError: AxiosError | null = null;
        const retryCount = this.config.autoRetry ? this.config.retryCount || 5 : 1;

        for (let i = 0; i < retryCount; i++) {
            try {
                console.log(`Request attempt ${i + 1}/${retryCount}: ${method} ${url}`);
                
                const response = await this.client.request({
                    method: method,
                    url: url,
                    data: data
                });

                // 缓存成功的 GET 请求结果
                if (method === 'get' && this.config.cacheEnabled) {
                    this.cache.set(cacheKey, {
                        data: response.data,
                        timestamp: Date.now()
                    });
                }

                return response.data;
            } catch (error) {
                lastError = error as AxiosError;
                
                console.log(`Request failed: ${lastError.message}`);
                console.log(`Status: ${lastError.response?.status}`);
                
                // 如果是认证错误，不重试
                if (lastError.response?.status === 401 || lastError.response?.status === 403) {
                    throw error;
                }

                // 如果是限流错误（429），等待更长时间
                if (lastError.response?.status === 429) {
                    const retryAfter = lastError.response?.headers?.['retry-after'] || 60;
                    console.log(`Rate limited, waiting ${retryAfter} seconds`);
                    await this.sleep(retryAfter * 1000);
                    continue;
                }

                // 指数退避重试：1s, 2s, 4s, 8s, 16s
                if (i < retryCount - 1) {
                    const waitTime = Math.pow(2, i) * 1000;
                    console.log(`Retrying in ${waitTime}ms...`);
                    await this.sleep(waitTime);
                }
            }
        }

        throw lastError;
    }

    /**
     * 等待请求槽位（避免 API 限流）
     */
    private async waitForRequestSlot(): Promise<void> {
        const now = Date.now();
        const elapsed = now - this.lastRequestTime;
        
        if (elapsed < this.minRequestInterval) {
            const waitTime = this.minRequestInterval - elapsed;
            await this.sleep(waitTime);
        }
        
        this.lastRequestTime = Date.now();
    }

    /**
     * 清除缓存
     */
    clearCache(): void {
        this.cache.clear();
        console.log('Cache cleared');
    }

    /**
     * 提取页面标题
     */
    private extractTitle(pageData: any): string {
        // 尝试从不同类型的标题属性中提取
        const properties = pageData.properties || {};
        
        // 标准标题属性
        if (properties.title?.title?.[0]?.text?.content) {
            return properties.title.title[0].text.content;
        }
        
        // 其他可能的标题属性名
        for (const key of ['Title', '名称', '任务名称', 'name']) {
            if (properties[key]?.title?.[0]?.text?.content) {
                return properties[key].title[0].text.content;
            }
        }
        
        return 'Untitled';
    }

    /**
     * 提取内容块
     */
    private extractContent(blocks: any[]): string {
        const contentLines: string[] = [];

        for (const block of blocks) {
            const type = block.type;
            
            if (block[type]?.rich_text) {
                const text = block[type].rich_text
                    .map((rt: any) => rt.text?.content || '')
                    .join('');
                contentLines.push(text);
            }
        }

        return contentLines.join('\n');
    }

    /**
     * 将文本内容转换为 Notion 块
     */
    private parseContentToBlocks(content: string): any[] {
        const lines = content.split('\n');
        const blocks: any[] = [];

        for (const line of lines) {
            if (line.trim() === '') continue;

            // 检测标题级别
            if (line.startsWith('# ')) {
                blocks.push({
                    type: 'heading_1',
                    heading_1: {
                        rich_text: [{ type: 'text', text: { content: line.substring(2) } }]
                    }
                });
            } else if (line.startsWith('## ')) {
                blocks.push({
                    type: 'heading_2',
                    heading_2: {
                        rich_text: [{ type: 'text', text: { content: line.substring(3) } }]
                    }
                });
            } else if (line.startsWith('### ')) {
                blocks.push({
                    type: 'heading_3',
                    heading_3: {
                        rich_text: [{ type: 'text', text: { content: line.substring(4) } }]
                    }
                });
            } else if (line.startsWith('- ')) {
                blocks.push({
                    type: 'bulleted_list_item',
                    bulleted_list_item: {
                        rich_text: [{ type: 'text', text: { content: line.substring(2) } }]
                    }
                });
            } else if (line.startsWith('1. ')) {
                blocks.push({
                    type: 'numbered_list_item',
                    numbered_list_item: {
                        rich_text: [{ type: 'text', text: { content: line.substring(3) } }]
                    }
                });
            } else {
                blocks.push({
                    type: 'paragraph',
                    paragraph: {
                        rich_text: [{ type: 'text', text: { content: line } }]
                    }
                });
            }
        }

        return blocks;
    }

    /**
     * 等待函数
     */
    private sleep(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}