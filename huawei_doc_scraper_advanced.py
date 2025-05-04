import requests
from bs4 import BeautifulSoup
import os
import time
import random
import re
import urllib.parse
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scraper.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("huawei_scraper")

# 创建保存文档的根目录
output_dir = "huawei_docs_full"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# 创建资源目录
resources_dir = os.path.join(output_dir, "resources")
if not os.path.exists(resources_dir):
    os.makedirs(resources_dir)

# 已处理的URL集合，避免重复处理
processed_urls = set()
failed_resources = set()  # 记录失败的资源，避免重复尝试

# 华为开发者文档URL
base_url = "https://developer.huawei.com/consumer/cn/doc/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://developer.huawei.com/",
}

# 创建带重试机制的会话
def create_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(headers)
    return session

# 初始化会话
session = create_session()

# 初始化Selenium WebDriver
def init_driver():
    """初始化Chrome WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 无头模式
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent={headers['User-Agent']}")
    chrome_options.add_argument(f"accept-language={headers['Accept-Language']}")
    
    # 添加更多的浏览器性能配置
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-popup-blocking")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # 设置页面加载超时
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    
    return driver

def clean_url(url):
    """清理URL中的动态参数"""
    # 移除时间戳等动态参数
    cleaned_url = url.split('?')[0]
    return cleaned_url

def get_page_content(url, driver):
    """使用Selenium获取网页内容"""
    try:
        logger.info(f"正在加载页面: {url}")
        
        # 尝试3次加载页面
        for attempt in range(3):
            try:
                driver.get(url)
                
                # 等待页面加载完成（等待body元素完全加载）
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # 检查页面是否包含有效内容
                if len(driver.page_source) < 1000 or "404" in driver.title:
                    logger.warning(f"页面内容可能无效，重试中... (尝试 {attempt+1}/3)")
                    time.sleep(2 * (attempt + 1))  # 增加延迟
                    continue
                
                # 额外等待，确保JavaScript完全执行
                time.sleep(3)
                
                # 尝试点击"接受cookies"类型的按钮（如果存在）
                try:
                    accept_buttons = driver.find_elements(By.XPATH, 
                        "//button[contains(text(), '接受') or contains(text(), '同意') or contains(text(), 'Accept') or contains(text(), 'Agree')]")
                    if accept_buttons:
                        for button in accept_buttons:
                            if button.is_displayed():
                                button.click()
                                time.sleep(1)
                                break
                except:
                    pass
                
                # 滚动页面以加载懒加载资源
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight/2);"
                )
                time.sleep(1)
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
                time.sleep(1)
                
                # 获取渲染后的HTML
                html_content = driver.page_source
                if html_content and len(html_content) > 1000:  # 确保有足够内容
                    return html_content
            except Exception as e:
                logger.warning(f"页面加载失败，尝试 {attempt+1}/3，错误: {e}")
                time.sleep(2 * (attempt + 1))  # 增加延迟
        
        logger.error(f"获取页面失败，已达到最大尝试次数: {url}")
        return None
    except Exception as e:
        logger.error(f"获取页面完全失败: {url}，错误: {e}")
        return None

def download_resource(url, resource_type, driver=None):
    """下载资源文件"""
    # 忽略已知失败的资源
    key = f"{url}_{resource_type}"
    if key in failed_resources:
        return None
    
    # 标准化URL
    if url.startswith('//'):
        url = 'https:' + url
    elif url.startswith('/'):
        url = 'https://developer.huawei.com' + url
    
    # 如果URL不是以http开头，跳过下载
    if not url.startswith('http'):
        return None
    
    # 清理URL中的动态参数用于检查是否已下载
    base_url_for_check = clean_url(url)
    
    # 生成资源保存路径
    parsed_url = urlparse(base_url_for_check)
    path_parts = parsed_url.path.strip('/').split('/')
    
    # 创建更好的文件名
    if len(path_parts) > 0 and path_parts[-1]:
        file_name = path_parts[-1]
        # 确保文件名有适当的扩展名
        if '.' not in file_name:
            file_name = f"{file_name}.{resource_type}"
    else:
        # 使用URL哈希作为文件名
        file_name = f"{abs(hash(base_url_for_check))}.{resource_type}"
    
    # 处理查询参数中的版本信息
    query = urllib.parse.parse_qs(parsed_url.query)
    if 'v' in query and query['v']:
        # 将版本信息添加到文件名中，但避免文件名过长
        version = query['v'][0][:8]  # 只使用版本号的前8个字符
        name_parts = file_name.rsplit('.', 1)
        file_name = f"{name_parts[0]}_v{version}.{name_parts[1]}"
    
    file_path = os.path.join(resources_dir, resource_type, file_name)
    
    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # 如果文件已存在，直接返回路径
    if os.path.exists(file_path):
        return file_path
    
    # 下载资源
    try:
        # 对于某些需要JavaScript渲染的资源，可以选择使用Selenium
        if resource_type in ['js', 'css'] and driver and (url.endswith('.js') or url.endswith('.css')):
            try:
                driver.get(url)
                time.sleep(1)
                content = driver.page_source
                
                # 对于CSS和JS，需要从页面源码中提取实际内容
                if resource_type == 'css':
                    content_match = re.search(r'<style[^>]*>(.*?)</style>', content, re.DOTALL)
                    if content_match:
                        content = content_match.group(1).strip()
                elif resource_type == 'js': 
                    content_match = re.search(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
                    if content_match:
                        content = content_match.group(1).strip()
                
                if content and len(content) > 10:  # 确保有内容
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.info(f"已通过Selenium下载资源: {file_path}")
                    return file_path
            except Exception as e:
                logger.warning(f"Selenium下载资源失败: {url}，尝试直接请求方式")
                # 失败后继续使用请求方式
        
        # 使用requests下载资源
        response = session.get(url, timeout=15)
        response.raise_for_status()
        
        # 检查内容类型
        content_type = response.headers.get('Content-Type', '')
        
        # 根据内容类型验证资源
        if resource_type == 'js' and 'javascript' not in content_type.lower() and 'text' not in content_type.lower():
            if len(response.content) < 50:  # 内容太小，可能不是有效资源
                logger.warning(f"资源内容无效 (内容类型: {content_type}): {url}")
                failed_resources.add(key)
                return None
                
        if resource_type == 'css' and 'css' not in content_type.lower() and 'text' not in content_type.lower():
            if len(response.content) < 50:  # 内容太小，可能不是有效资源
                logger.warning(f"资源内容无效 (内容类型: {content_type}): {url}")
                failed_resources.add(key)
                return None
                
        if resource_type == 'img' and 'image' not in content_type.lower():
            if len(response.content) < 100:  # 内容太小，可能不是有效图片
                logger.warning(f"资源内容无效 (内容类型: {content_type}): {url}")
                failed_resources.add(key)
                return None
        
        # 保存文件
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"已下载资源: {file_path}")
        time.sleep(random.uniform(0.3, 0.8))  # 短暂延迟
        return file_path
    except Exception as e:
        logger.warning(f"下载资源失败: {url}，错误: {e}")
        failed_resources.add(key)  # 记录失败的资源
        return None

def process_html_resources(html_content, page_url, driver=None):
    """处理HTML中的资源链接，下载资源并替换链接为本地路径"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 创建资源类型目录
    for res_type in ['css', 'js', 'img', 'fonts']:
        os.makedirs(os.path.join(resources_dir, res_type), exist_ok=True)
    
    # 处理CSS文件
    for css_tag in soup.find_all('link', rel='stylesheet'):
        if css_tag.get('href'):
            css_url = urljoin(page_url, css_tag['href'])
            local_path = download_resource(css_url, 'css', driver)
            if local_path:
                css_tag['href'] = os.path.relpath(local_path, output_dir)
    
    # 处理JS文件
    for js_tag in soup.find_all('script', src=True):
        js_url = urljoin(page_url, js_tag['src'])
        local_path = download_resource(js_url, 'js', driver)
        if local_path:
            js_tag['src'] = os.path.relpath(local_path, output_dir)
    
    # 处理图片
    for img_tag in soup.find_all('img', src=True):
        img_url = urljoin(page_url, img_tag['src'])
        local_path = download_resource(img_url, 'img', driver)
        if local_path:
            img_tag['src'] = os.path.relpath(local_path, output_dir)
    
    # 处理网页图标
    for link_tag in soup.find_all('link', rel=lambda r: r and ('icon' in r.lower())):
        if link_tag.get('href'):
            icon_url = urljoin(page_url, link_tag['href'])
            local_path = download_resource(icon_url, 'img', driver)
            if local_path:
                link_tag['href'] = os.path.relpath(local_path, output_dir)
    
    # 处理内联样式中的背景图片URLs
    style_tags = soup.find_all('style')
    for style_tag in style_tags:
        if style_tag.string:
            # 查找CSS中的url()引用
            urls = re.findall(r'url\([\'"]?([^\'")]+)[\'"]?\)', style_tag.string)
            for url in urls:
                if url and not url.startswith('data:'):  # 排除data URLs
                    img_url = urljoin(page_url, url)
                    local_path = download_resource(img_url, 'img', driver)
                    if local_path:
                        rel_path = os.path.relpath(local_path, output_dir).replace('\\', '/')
                        style_tag.string = style_tag.string.replace(f'url({url})', f'url({rel_path})')
                        style_tag.string = style_tag.string.replace(f"url('{url}')", f"url('{rel_path}')")
                        style_tag.string = style_tag.string.replace(f'url("{url}")', f'url("{rel_path}")')
    
    return str(soup)

def get_safe_filename(url):
    """从URL生成安全的文件名"""
    # 提取URL中的路径部分
    path = urlparse(url).path
    
    # 移除页面锚点和查询参数
    clean_path = path.split('#')[0].split('?')[0]
    
    # 如果路径为空或只有/，使用域名作为文件名
    if clean_path == '' or clean_path == '/':
        domain = urlparse(url).netloc
        return f"{domain.replace('.', '_')}.html"
    
    # 移除扩展名，稍后我们会添加.html
    basename = os.path.basename(clean_path)
    if '.' in basename:
        basename = basename.split('.')[0]
    
    # 替换非法字符
    safe_name = re.sub(r'[\\/*?:"<>|]', '_', basename)
    
    # 确保文件名不为空
    if not safe_name:
        safe_name = str(abs(hash(url)))
    
    # 文件名过长则截断并添加哈希值
    if len(safe_name) > 50:
        safe_name = safe_name[:40] + '_' + str(abs(hash(url)))[:8]
    
    return f"{safe_name}.html"

def get_directory_path(url):
    """从URL获取目录路径"""
    # 提取URL中关键部分创建层次结构
    parts = urlparse(url).path.strip('/').split('/')
    
    # 创建层次结构目录，但排除最后一个部分(文件名)
    if len(parts) > 1:
        # 限制目录深度，防止路径过长
        parts = parts[:3]
        dir_path = os.path.join(output_dir, *parts[:-1])
    else:
        dir_path = output_dir
    
    return dir_path

def save_page(content, url):
    """保存页面内容到文件，保持URL的目录结构"""
    # 获取目录路径
    dir_path = get_directory_path(url)
    
    # 确保目录存在
    os.makedirs(dir_path, exist_ok=True)
    
    # 创建文件名
    file_name = get_safe_filename(url)
    file_path = os.path.join(dir_path, file_name)
    
    # 保存文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"已保存: {file_path}")
    return file_path

def should_process_url(url):
    """判断URL是否应该被处理"""
    # 排除登录页面、注册页面等
    excluded_patterns = [
        '/login', '/register', '/sign', '/account', 
        '/download/', '/contact', '/support', 
        '.pdf', '.zip', '.exe', '.apk', '.jar'
    ]
    
    for pattern in excluded_patterns:
        if pattern in url:
            return False
    
    # 只处理文档相关URL
    return '/doc/' in url

def process_page(url, driver, level=0, max_level=2):
    """处理页面内容并递归处理子页面"""
    # 检查URL是否已处理过
    if url in processed_urls or level > max_level or not should_process_url(url):
        return
    
    # 标记URL为已处理
    processed_urls.add(url)
    
    logger.info(f"抓取页面: {url} (层级 {level}/{max_level})")
    html_content = get_page_content(url, driver)
    if not html_content:
        return
    
    # 处理并下载页面中的资源
    processed_html = process_html_resources(html_content, url, driver)
    
    # 保存处理后的页面
    save_page(processed_html, url)
    
    # 随机延迟，避免被封IP
    delay = random.uniform(2, 4) if level == 0 else random.uniform(1, 2.5)
    time.sleep(delay)
    
    # 解析HTML查找链接
    soup = BeautifulSoup(html_content, 'html.parser')
    links = soup.find_all('a', href=True)
    
    # 处理链接
    for link in links:
        href = link['href']
        
        # 跳过空链接、锚点和JavaScript链接
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue
        
        # 构建完整URL
        next_url = urljoin(url, href)
        
        # 只处理同域名下的文档链接
        if urlparse(next_url).netloc == urlparse(base_url).netloc and should_process_url(next_url):
            process_page(next_url, driver, level + 1, max_level)

def main():
    logger.info(f"开始抓取华为开发者文档，内容将保存到 {output_dir} 目录")
    logger.info(f"资源文件将保存在 {resources_dir} 目录")
    
    # 初始化WebDriver
    driver = init_driver()
    
    try:
        process_page(base_url, driver)
    except KeyboardInterrupt:
        logger.info("用户中断，停止抓取")
    except Exception as e:
        logger.error(f"抓取过程中发生错误: {e}")
    finally:
        # 确保关闭WebDriver
        driver.quit()
        
    logger.info(f"抓取完成! 共处理了 {len(processed_urls)} 个页面")
    logger.info(f"有 {len(failed_resources)} 个资源下载失败")
    
    # 保存已处理的URL列表
    with open(os.path.join(output_dir, 'processed_urls.txt'), 'w', encoding='utf-8') as f:
        for processed_url in processed_urls:
            f.write(f"{processed_url}\n")
    
    # 保存失败资源列表
    with open(os.path.join(output_dir, 'failed_resources.txt'), 'w', encoding='utf-8') as f:
        for failed_resource in failed_resources:
            f.write(f"{failed_resource}\n")

if __name__ == "__main__":
    main() 