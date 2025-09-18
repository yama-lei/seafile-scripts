#!/usr/bin/env python3
"""
Script to fetch all repositories from Seafile, decompress archive files,
and upload the extracted contents back to Seafile.

This script handles:
- Getting all repositories accessible to the user
- Finding compressed files (zip, tar, etc.)
- Downloading compressed files locally
- Extracting them (avoiding duplicate extraction)
- Uploading extracted contents back to Seafile
"""

import os
import sys
import zipfile
import tarfile
import tempfile
import re

# Add the current directory to the path so we can import seafileapi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from seafileapi import SeafileAPI

# Configuration - Modify these values according to your setup
SERVER_URL = ""  # Replace with your Seafile server URL
LOGIN_NAME = ""  # Replace with your login name
PASSWORD = ""  # Replace with your password

# Supported archive file extensions
ARCHIVE_EXTENSIONS = {'.zip', '.tar', '.tar.gz', '.tar.bz2', '.tgz', '.tbz2'}

def is_archive_file(filename):
    """Check if a file is an archive based on its extension."""
    for ext in ARCHIVE_EXTENSIONS:
        if filename.lower().endswith(ext):
            return True
    return False

def get_archive_folder_name(filename):
    """Get the folder name for an extracted archive."""
    for ext in sorted(ARCHIVE_EXTENSIONS, key=len, reverse=True):
        if filename.lower().endswith(ext):
            return filename[:-len(ext)]
    return filename + "_extracted"

def extract_archive(file_path, extract_to):
    """Extract an archive file to the specified directory."""
    try:
        if file_path.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
        elif file_path.endswith(('.tar', '.tar.gz', '.tar.bz2', '.tgz', '.tbz2')):
            with tarfile.open(file_path, 'r:*') as tar_ref:
                tar_ref.extractall(extract_to)
        return True
    except Exception as e:
        print(f"Error extracting {file_path}: {e}")
        return False

# ----------------- 新增/修改的代码 -----------------

def interactive_select_path(seafile_api):
    """
    交互式地引导用户选择一个 Seafile 路径进行处理。
    Returns a tuple of (repo_id, path)
    """
    current_repo = None
    current_repo_name = None
    current_path = '/'
    
    while True:
        try:
            if not current_repo:
                # 第一次进入，只显示仓库列表
                print("\n--- 请选择一个仓库 ---")
                repos = seafile_api.list_repos()
                repos_map = {str(i+1): repo for i, repo in enumerate(repos)}
                for i, repo in enumerate(repos):
                    print(f"  {i+1}: {repo['name']}")
                
                user_input = input("请输入数字选择仓库 (或'q'退出): ").strip()
                if user_input.lower() == 'q':
                    print("已退出。")
                    sys.exit(0)
                
                if user_input in repos_map:
                    selected_repo_info = repos_map[user_input]
                    current_repo = seafile_api.get_repo(selected_repo_info['id'])
                    current_repo_name = selected_repo_info['name']
                    current_path = '/'
                    print(f"已选择仓库：{current_repo_name}")
                else:
                    print("无效的选择，请重新输入。")
                    continue
            
            # 显示当前路径下的目录和文件
            print(f"\n--- 当前路径：{current_repo_name}{current_path} ---")
            items = current_repo.list_dir(current_path)
            
            dirs_map = {}
            files_map = {}
            for item in items:
                if item['type'] == 'dir':
                    dirs_map[item['name']] = item
                else:
                    files_map[item['name']] = item

            # 打印目录列表
            dir_choices = list(dirs_map.keys())
            if dir_choices:
                print("--- 子目录 ---")
                for i, dir_name in enumerate(dir_choices):
                    print(f"  {i+1}: {dir_name}/")
            
            # 打印文件列表（仅供参考）
            if files_map:
                print("--- 文件 ---")
                for file_name in files_map:
                    print(f"  {file_name}")

            # 导航和操作选项
            print("\n--- 操作选项 ---")
            print("  [.] 返回上一级目录")
            print("  [0] 在此目录（及子目录）中解压所有压缩包")
            user_input = input("请输入数字进入子目录，或选择操作: ").strip()

            if user_input == '0':
                return current_repo.repo_id, current_path
            
            if user_input == '.':
                if current_path == '/':
                    print("已返回仓库根目录，将回到仓库选择界面。")
                    current_repo = None
                    current_repo_name = None
                else:
                    # 确保路径是'/'开头的，使用 os.path.dirname
                    current_path = os.path.dirname(current_path.rstrip('/'))
                    if not current_path:
                        current_path = '/'
                continue
                
            try:
                choice_index = int(user_input) - 1
                if 0 <= choice_index < len(dir_choices):
                    selected_dir_name = dir_choices[choice_index]
                    current_path = os.path.join(current_path, selected_dir_name).replace('\\', '/')
                else:
                    print("无效的选择，请重新输入。")
            except ValueError:
                print("无效的输入，请重新输入。")

        except Exception as e:
            print(f"操作失败: {e}")
            print("将返回上一级或重新开始。")
            current_repo = None
            current_repo_name = None
            current_path = '/'
            
def handle_archive_file(repo, seafile_dir, archive_item, temp_dir):
    """
    处理单个压缩文件：下载、解压、上传
    """
    archive_name = archive_item['name']
    archive_full_path = os.path.join(seafile_dir, archive_name).replace('\\', '/')

    folder_name = get_archive_folder_name(archive_name)

    # 检查解压文件夹是否已存在
    try:
        items_in_seafile_dir = repo.list_dir(seafile_dir)
        existing_items = {item['name'] for item in items_in_seafile_dir}
        if folder_name in existing_items:
            print(f"  跳过 {archive_name}，因为解压目录 {folder_name} 已存在。")
            return
    except Exception as e:
        print(f"  警告：无法检查目录存在性，继续处理。错误: {e}")

    print(f"  正在处理 {archive_full_path}...")

    # 下载压缩文件
    archive_local_path = os.path.join(temp_dir, archive_name)
    try:
        repo.download_file(archive_full_path, archive_local_path)
        print(f"    已下载 {archive_name}")
    except Exception as e:
        print(f"    下载 {archive_full_path} 失败: {e}")
        return

    # 解压文件
    extract_dir = os.path.join(temp_dir, folder_name)
    os.makedirs(extract_dir, exist_ok=True)

    if extract_archive(archive_local_path, extract_dir):
        print(f"    已解压至 {extract_dir}")

        # 上传解压后的内容
        try:
            # 目标上传目录是原始文件所在的目录加上解压文件夹名
            target_seafile_dir = os.path.join(seafile_dir, folder_name).replace('\\', '/')
            # 修复：在创建目录时，如果失败则直接返回，防止后续上传失败
            try:
                repo.create_dir(target_seafile_dir)
                print(f"    已创建 Seafile 目录 {target_seafile_dir}")
            except Exception as e:
                print(f"    创建 Seafile 目录 {target_seafile_dir} 失败: {e}")
                print(f"    跳过 {archive_name} 的内容上传。")
                return

            for root, dirs, files in os.walk(extract_dir):
                rel_path = os.path.relpath(root, extract_dir)
                
                # --- 代码修改开始 ---
                # 当 rel_path 为 '.', 代表是解压目录的根。
                # 此时上传路径就是目标目录本身, 而不是在其后拼接 '/.'。
                if rel_path == '.':
                    upload_seafile_dir = target_seafile_dir
                else:
                    upload_seafile_dir = os.path.join(target_seafile_dir, rel_path).replace('\\', '/')
                # --- 代码修改结束 ---

                for dir_name in dirs:
                    dir_path = os.path.join(upload_seafile_dir, dir_name).replace('\\', '/')
                    try:
                        repo.create_dir(dir_path)
                        print(f"      创建目录: {dir_path}")
                    except Exception as e:
                        print(f"      创建目录 {dir_path} 失败: {e}")

                for file_name in files:
                    local_file_path = os.path.join(root, file_name)
                    try:
                        repo.upload_file(upload_seafile_dir, local_file_path)
                        uploaded_path = os.path.join(upload_seafile_dir, file_name).replace('\\', '/')
                        print(f"      上传文件: {uploaded_path}")
                    except Exception as e:
                        error_path = os.path.join(upload_seafile_dir, file_name).replace('\\', '/')
                        print(f"      上传 {error_path} 失败: {e}")
            print(f"    成功上传 {archive_name} 的解压内容")
        except Exception as e:
            print(f"    上传解压内容失败: {e}")
    else:
        print(f"    解压 {archive_name} 失败")

def process_path_recursively(seafile_api, repo_id, path, temp_dir):
    """
    递归处理指定路径及其所有子目录中的压缩文件。
    """
    repo = seafile_api.get_repo(repo_id)
    repo_details = repo.get_repo_details()
    print(f"\n开始递归处理仓库: {repo_details['repo_name']}，路径: {path}")

    queue = [path]
    processed_paths = set()

    while queue:
        current_path = queue.pop(0)

        if current_path in processed_paths:
            continue
        processed_paths.add(current_path)

        try:
            items = repo.list_dir(current_path)
        except Exception as e:
            print(f"  无法列出目录 {current_path}，跳过。错误: {e}")
            continue
        
        archives_in_dir = []
        dirs_in_dir = []
        for item in items:
            if item['type'] == 'file' and is_archive_file(item['name']):
                archives_in_dir.append(item)
            elif item['type'] == 'dir':
                dirs_in_dir.append(item)

        if not archives_in_dir:
            print(f"  在目录 {current_path} 中未找到压缩文件。")
        else:
            print(f"  在目录 {current_path} 中找到 {len(archives_in_dir)} 个压缩文件。")
            for archive_item in archives_in_dir:
                handle_archive_file(repo, current_path, archive_item, temp_dir)

        for dir_item in dirs_in_dir:
            dir_full_path = os.path.join(current_path, dir_item['name']).replace('\\', '/')
            queue.append(dir_full_path)


def main():
    """Main function to handle user input and process the specified path."""
    try:
        seafile_api = SeafileAPI(LOGIN_NAME, PASSWORD, SERVER_URL)
        seafile_api.auth()
        print("已成功验证 Seafile 账户。")
    except Exception as e:
        print(f"账户验证失败: {e}")
        sys.exit(1)

    # 调用新的交互式选择函数
    repo_id, path = interactive_select_path(seafile_api)
    
    # 使用临时目录来处理文件
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"\n正在使用临时目录: {temp_dir}")
        process_path_recursively(seafile_api, repo_id, path, temp_dir)

if __name__ == "__main__":
    main()
