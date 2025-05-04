import requests
from bs4 import BeautifulSoup
import os
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 创建保存文档的目录
output_dir = "huawei_docs"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# 华为开发者文档URL
base_url = "https://developer.huawei.com/consumer/cn/doc/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://developer.huawei.com/",
}

# 初始化Selenium WebDriver
def init_driver():
    """初始化Chrome WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 无头模式
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent={headers['User-Agent']}")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_page_content(url, driver):
    """使用Selenium获取网页内容"""
    try:
        print(f"正在加载页面: {url}")
        driver.get(url)
        
        # 等待页面加载完成（等待body元素完全加载）
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # 额外等待，确保JavaScript完全执行
        time.sleep(3)
        
        # 获取渲染后的HTML
        html_content = driver.page_source
        return html_content
    except Exception as e:
        print(f"获取页面失败: {url}，错误: {e}")
        return None

def save_page(content, filename):
    """保存页面内容到文件"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"已保存: {filename}")

def process_page(url, driver, visited=None, level=0, max_level=2):
    """处理页面内容并递归处理子页面"""
    if visited is None:
        visited = set()
        
    if url in visited or level > max_level:
        return
    
    visited.add(url)
    
    print(f"抓取页面: {url}")
    html_content = get_page_content(url, driver)
    if not html_content:
        return
    
    # 解析HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 生成文件名
    url_parts = url.split('/')
    page_name = url_parts[-1] if url_parts[-1] else "index"
    if "?" in page_name:
        page_name = page_name.split('?')[0]
    if not page_name.endswith(".html"):
        page_name = f"{page_name}.html"
    
    # 保存当前页面
    file_path = os.path.join(output_dir, page_name)
    save_page(html_content, file_path)
    
    # 随机延迟，避免被封IP
    time.sleep(random.uniform(2, 5))
    
    # 查找并处理子页面链接
    links = soup.find_all('a', href=True)
    for link in links:
        href = link['href']
        # 只处理相对URL或者同域名的URL
        if href.startswith('/') or href.startswith(base_url):
            if href.startswith('/'):
                next_url = f"https://developer.huawei.com{href}"
            else:
                next_url = href
            
            # 确保URL是文档链接
            if "/doc/" in next_url and next_url != url:
                process_page(next_url, driver, visited, level + 1, max_level)

def main():
    print(f"开始抓取华为开发者文档，内容将保存到 {output_dir} 目录")
    driver = init_driver()
    try:
        process_page(base_url, driver)
    finally:
        driver.quit()
    print("抓取完成!")

if __name__ == "__main__":
    main() 