import requests
from bs4 import BeautifulSoup
import os
import time
import random
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import traceback

# 创建保存文档的目录
output_dir = r"D:\00code\04hmdev\huawei_docs_arengine"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# 华为开发者文档URL - API参考入口
base_url = "https://developer.huawei.com/consumer/cn/doc/harmonyos-references/ar-engine-overview"
api_reference_base = "https://developer.huawei.com/consumer/cn/doc/harmonyos-references/ar-engine-"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://developer.huawei.com/consumer/cn/",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Not.A/Brand";v="8", "Chromium";v="114", "Google Chrome";v="114"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

# 用于记录已访问页面
visited_urls = set()
# 用于调试
debug_mode = True

# 初始化Selenium WebDriver
def init_driver():
    """初始化Chrome WebDriver"""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # 无头模式
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # 添加更多伪装参数
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument(f"user-agent={headers['User-Agent']}")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # 添加请求头
        for key, value in headers.items():
            if key.lower() != "user-agent":  # User-Agent已单独设置
                chrome_options.add_argument(f"--header={key}: {value}")
        
        # 设置不加载图片，加快速度
        chrome_prefs = {}
        chrome_prefs["profile.default_content_settings"] = {"images": 2}
        chrome_options.experimental_options["prefs"] = chrome_prefs
        
        # 禁用自动化控制特征，降低被检测风险
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # 进一步伪装WebDriver
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # 设置页面加载超时
        driver.set_page_load_timeout(30)
        
        return driver
    except Exception as e:
        print(f"初始化WebDriver失败: {e}")
        traceback.print_exc()
        return None

def get_page_content(url, driver, retry=2):
    """使用Selenium获取网页内容，带重试机制"""
    global visited_urls
    
    for attempt in range(retry + 1):
        try:
            print(f"正在加载页面 (尝试 {attempt+1}/{retry+1}): {url}")
            
            # 随机延迟，模拟人类行为
            time.sleep(random.uniform(1, 3))
            
            driver.get(url)
            
            # 等待页面加载完成（等待body元素完全加载）
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 尝试等待特定的内容加载完成
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".doc-content, .api-content, .markdown-body"))
                )
            except:
                if debug_mode:
                    print(f"警告: 在页面 {url} 上未找到预期的内容元素，使用整个页面")
            
            # 执行滚动以确保加载所有内容
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # 等待可能的动态内容加载
            
            # 获取渲染后的HTML
            html_content = driver.page_source
            
            # 只有在成功获取内容后才标记为已访问
            if html_content and len(html_content) > 1000:  # 确保获取到了有意义的内容
                visited_urls.add(url)
                
                # 更精确的404/错误页面检测
                is_error_page = False
                try:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    page_title = soup.title.string.lower() if soup.title else ""
                    # 检查标题是否包含常见的错误指示词
                    if "not found" in page_title or "404" in page_title or "错误" in page_title or "error" in page_title:
                        is_error_page = True
                        print(f"警告: 页面标题 '{page_title}' 暗示可能是错误页面")
                    
                    # 检查页面中是否有特定的错误提示元素（需要根据实际情况调整选择器）
                    error_element = soup.select_one('#error-page, .error-container, .page-not-found')
                    if error_element:
                        is_error_page = True
                        print(f"警告: 页面包含错误元素")
                        
                except Exception as e:
                    print(f"解析页面检查错误时发生异常: {e}")
                
                if is_error_page:
                    print(f"警告: 页面 {url} 被识别为错误页面，跳过")
                    return None
                    
                # 如果不是错误页面，正常返回内容
                if debug_mode:
                    print(f"成功获取页面内容, 大小: {len(html_content)} 字节")
                return html_content
            else:
                print(f"警告: 页面内容为空或太小 ({len(html_content) if html_content else 0} 字节)")
        except Exception as e:
            if attempt < retry:
                wait_time = (attempt + 1) * 5  # 递增的等待时间
                print(f"尝试 {attempt+1} 失败: {e}，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"获取页面失败: {url}，错误: {e}")
                traceback.print_exc()
    
    return None

def clean_filename(name):
    """清理文件名，移除非法字符"""
    # 移除换行符、制表符等空白字符
    name = re.sub(r'\s+', ' ', name).strip()
    
    # 移除Windows文件系统不允许的字符
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    
    # 确保文件名不过长
    if len(name) > 200:
        name = name[:197] + "..."
    
    return name

def is_api_reference_url(url):
    """判断URL是否属于Ability API参考栏目"""
    if not url:
        return False
    
    # 检查URL是否以Ability API参考基础路径开头
    if url.startswith(api_reference_base):
        return True
    
    # 检查URL路径中是否包含特定Ability API参考关键词
    api_keywords = [
        "/ability-", 
        "/harmonyos-references/ability",
        "/js-apis-ability", 
        "/apis-ability", 
        "/ability-api"
    ]
    
    for keyword in api_keywords:
        if keyword in url:
            return True
    
    return False

def extract_page_title(html_content):
    """从HTML内容中提取页面标题"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.text.strip()
            # 移除可能的网站名称后缀
            if " - " in title:
                title = title.split(" - ")[0].strip()
            return title
        
        # 如果没有title标签，尝试h1
        h1_tag = soup.find('h1')
        if h1_tag:
            return h1_tag.text.strip()
        
        return None
    except Exception as e:
        print(f"提取标题失败: {e}")
        return None

def save_page(content, filename, title=None):
    """保存页面内容到文件"""
    try:
        # 清理文件名
        clean_name = clean_filename(filename)
        
        # 创建必要的目录
        dir_path = os.path.dirname(clean_name)
        if dir_path and not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path)
            except Exception as e:
                print(f"创建目录失败 {dir_path}: {e}")
                # 如果目录创建失败，改为保存到根目录
                clean_name = os.path.basename(clean_name)
        
        # 如果有标题，添加到HTML内容开头
        if title:
            # 在<body>标签后添加标题
            content = content.replace('<body', f'<body>\n<h1>{title}</h1>\n')
        
        with open(clean_name, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"已保存: {clean_name}")
        return True
    except Exception as e:
        print(f"保存文件失败 ({filename}): {e}")
        # 尝试使用一个安全的替代文件名
        try:
            fallback_name = os.path.join(output_dir, f"page_{int(time.time())}.html")
            with open(fallback_name, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"已使用替代文件名保存: {fallback_name}")
            return True
        except Exception as e2:
            print(f"替代保存也失败: {e2}")
            return False

def get_relative_path(url):
    """从URL获取相对路径，用于创建目录结构"""
    try:
        # 移除基础URL部分
        rel_path = url.replace("https://developer.huawei.com/consumer/cn/doc/", "")
        # 移除查询参数
        if "?" in rel_path:
            rel_path = rel_path.split("?")[0]
        # 确保路径不为空
        if not rel_path:
            rel_path = "index"
        
        return rel_path
    except:
        # 如果处理失败，返回时间戳
        return f"page_{int(time.time())}"

def process_page(url, driver, level=0, max_level=3):
    """处理页面内容并递归处理子页面"""
    global visited_urls
    
    if url in visited_urls or level > max_level:
        print(f"已访问过或超出最大深度: {url}")
        return
    
    # 检查URL是否属于API参考栏目
    if not is_api_reference_url(url) and level > 0:
        print(f"跳过非Ability API参考页面: {url}")
        return
    
    try:
        print(f"\n--- 抓取页面 [{level}/{max_level}]: {url} ---")
        html_content = get_page_content(url, driver)
        
        # 仅当成功获取内容时才继续处理
        if not html_content:
            print(f"跳过页面 {url}: 无法获取内容")
            return
        
        # 到这里说明内容获取成功，URL已在get_page_content中被标记为已访问
        
        # 提取页面标题
        title = extract_page_title(html_content)
        if title:
            print(f"页面标题: {title}")
        
        # 生成文件名和路径
        try:
            # 获取相对路径
            rel_path = get_relative_path(url)
            
            # 确保有html扩展名
            if not rel_path.endswith(".html"):
                rel_path = f"{rel_path}.html"
            
            # 构建完整文件路径
            file_path = os.path.join(output_dir, rel_path)
            
            # 保存当前页面
            save_success = save_page(html_content, file_path, title)
            if not save_success:
                print(f"警告: 页面 {url} 保存失败，但继续处理")
        except Exception as e:
            print(f"处理文件名出错: {e}，使用时间戳作为文件名")
            # 使用时间戳作为备用文件名
            file_path = os.path.join(output_dir, f"page_{int(time.time())}.html")
            save_page(html_content, file_path, title)
        
        # 休息一下，避免被封IP
        time.sleep(random.uniform(2, 5))
        
        # 查找并处理子页面链接
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 尝试找出内容区域，以减少处理不相关的链接
            content_area = soup.select_one('.doc-content, .api-content, .markdown-body, article, main')
            if not content_area:
                content_area = soup.body
                
            links = content_area.find_all('a', href=True)
            
            # 优先处理可能是API参考的链接
            api_links = []
            other_links = []
            
            for link in links:
                try:
                    href = link['href']
                    # 过滤无效链接
                    if not href or href == '#' or href.startswith('javascript:'):
                        continue
                        
                    # 只处理相对URL或者同域名的URL
                    if href.startswith('/') or href.startswith("https://developer.huawei.com"):
                        if href.startswith('/'):
                            next_url = f"https://developer.huawei.com{href}"
                        else:
                            next_url = href
                        
                        # 确保URL是文档链接且未访问过
                        if "/doc/" in next_url and next_url != url and next_url not in visited_urls:
                            if is_api_reference_url(next_url):
                                api_links.append(next_url)
                            else:
                                other_links.append(next_url)
                except Exception as e:
                    if debug_mode:
                        print(f"处理链接时出错: {e}，继续下一个链接")
                    continue
            
            print(f"找到 {len(api_links)} 个API参考链接，{len(other_links)} 个其他链接")
            
            # 先处理API参考链接
            for i, next_url in enumerate(api_links):
                print(f"处理API链接 {i+1}/{len(api_links)}: {next_url}")
                process_page(next_url, driver, level + 1, max_level)
            
            # 如果是第一层，也处理其他链接（可能包含未检测到的API参考）
            if level == 0:
                other_limit = min(5, len(other_links))  # 限制数量，避免爬取过多
                print(f"作为首页，额外处理 {other_limit} 个非API链接")
                for i, next_url in enumerate(other_links[:other_limit]):
                    print(f"处理其他链接 {i+1}/{other_limit}: {next_url}")
                    process_page(next_url, driver, level + 1, max_level)
                    
        except Exception as e:
            print(f"查找链接时出错: {e}")
            traceback.print_exc()
    except Exception as e:
        print(f"处理页面 {url} 时出错: {e}")
        traceback.print_exc()

def main():
    print(f"\n=== 开始抓取华为开发者文档 AR Engine参考栏目 ===")
    print(f"内容将保存到目录: {output_dir}")
    
    driver = init_driver()
    if not driver:
        print("初始化WebDriver失败，退出程序")
        return
    
    try:
        # 先访问首页，可能需要接受cookies或其他设置
        print("访问华为开发者首页...")
        driver.get("https://developer.huawei.com/consumer/cn/")
        time.sleep(5)  # 等待加载完成
        
        # 开始处理目标页面
        process_page(base_url, driver)
        
        print(f"\n=== 抓取完成! 共抓取 {len(visited_urls)} 个页面 ===")
    except Exception as e:
        print(f"主程序执行出错: {e}")
        traceback.print_exc()
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    main()