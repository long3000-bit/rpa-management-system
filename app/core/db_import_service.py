import subprocess
import os
import logging
import re
import tempfile
from dataclasses import dataclass
from typing import Optional, Callable


@dataclass
class DbImportResult:
    success: bool
    message: str
    tables_count: int = 0
    error_detail: str = ""


class DbImportService:
    
    def __init__(self, host: str = "localhost", port: int = 3306, 
                 username: str = "root", password: str = "",
                 charset: str = "utf8mb4", import_timeout: int = 3600):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.charset = charset
        self.import_timeout = import_timeout
        self.mysql_path = self._find_mysql_path()
    
    def _find_mysql_path(self) -> str:
        common_paths = [
            r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
            r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
            r"C:\xampp\mysql\bin\mysql.exe",
            r"C:\wamp64\bin\mysql\mysql8.0.31\bin\mysql.exe",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        return "mysql"
    
    def test_connection(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.mysql_path, '-u', self.username, f'-p{self.password}', 
                 '-h', self.host, '-P', str(self.port), '-e', 'SELECT 1;'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return True, "连接成功"
            else:
                error = result.stderr.replace(f"mysql: [Warning] Using a password on the command line interface can be insecure.\n", "")
                return False, error.strip() or "连接失败"
        except FileNotFoundError:
            return False, f"未找到mysql程序，请检查MySQL是否安装"
        except subprocess.TimeoutExpired:
            return False, "连接超时"
        except Exception as e:
            return False, str(e)
    
    def get_databases(self) -> tuple[list[str], str]:
        try:
            result = subprocess.run(
                [self.mysql_path, '-u', self.username, f'-p{self.password}',
                 '-h', self.host, '-P', str(self.port),
                 '-N', '-e', 'SHOW DATABASES;'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                dbs = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                system_dbs = {'information_schema', 'mysql', 'performance_schema', 'sys'}
                dbs = [db for db in dbs if db not in system_dbs]
                return dbs, ""
            else:
                return [], result.stderr.strip()
        except Exception as e:
            return [], str(e)
    
    def create_database(self, db_name: str, charset: str = "utf8mb4") -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.mysql_path, '-u', self.username, f'-p{self.password}',
                 '-h', self.host, '-P', str(self.port),
                 '-e', f"CREATE DATABASE IF NOT EXISTS `{db_name}` DEFAULT CHARACTER SET {charset} COLLATE {charset}_general_ci;"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return True, f"数据库 {db_name} 创建成功"
            else:
                return False, result.stderr.strip()
        except Exception as e:
            return False, str(e)
    
    def drop_database(self, db_name: str) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.mysql_path, '-u', self.username, f'-p{self.password}',
                 '-h', self.host, '-P', str(self.port),
                 '-e', f"DROP DATABASE IF EXISTS `{db_name}`;"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return True, f"数据库 {db_name} 删除成功"
            else:
                return False, result.stderr.strip()
        except Exception as e:
            return False, str(e)
    
    def import_sql(self, sql_file: str, db_name: str, 
                   progress_callback: Optional[Callable[[int, str], None]] = None) -> DbImportResult:
        
        if not os.path.exists(sql_file):
            return DbImportResult(False, f"SQL文件不存在: {sql_file}")
        
        file_size_mb = os.path.getsize(sql_file) / (1024 * 1024)
        logging.info(f"开始导入SQL文件: {sql_file}, 大小: {file_size_mb:.2f}MB")
        
        encoding = self._detect_file_encoding(sql_file)
        logging.info(f"SQL文件编码: {encoding}")
        
        if progress_callback:
            progress_callback(10, "开始导入SQL文件...")
        
        try:
            with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(mode="w+b") as stderr_file:
                process = subprocess.Popen(
                [self.mysql_path, '-u', self.username, f'-p{self.password}',
                 '-h', self.host, '-P', str(self.port),
                     f'--default-character-set={self.charset}', '--force', db_name],
                stdin=subprocess.PIPE,
                    stdout=stdout_file,
                    stderr=stderr_file
                )
                
                try:
                    self._stream_sql_to_process(
                        process,
                        sql_file,
                        encoding,
                        file_size_mb,
                        progress_callback
                    )
                    return_code = process.wait(timeout=self.import_timeout)
                except Exception:
                    if process.poll() is None:
                        process.kill()
                    raise
                
                stderr_file.seek(0)
                stderr = stderr_file.read()
            
            if return_code != 0:
                error_msg = stderr.decode('utf-8', errors='replace')
                error_msg = error_msg.replace("mysql: [Warning] Using a password on the command line interface can be insecure.\n", "")
                logging.error(f"导入失败: {error_msg}")
                
                if "ERROR" in error_msg:
                    return DbImportResult(False, "导入过程中有错误", 0, error_msg)
            
            if progress_callback:
                progress_callback(90, "验证导入结果...")
            
            tables_count = self._get_tables_count(db_name)
            
            if progress_callback:
                progress_callback(100, "导入完成")
            
            logging.info(f"SQL导入完成，共 {tables_count} 个表")
            return DbImportResult(True, f"导入成功，共 {tables_count} 个表", tables_count)
            
        except subprocess.TimeoutExpired:
            return DbImportResult(False, "导入超时，文件可能过大")
        except BrokenPipeError:
            return DbImportResult(False, "导入失败：mysql进程提前退出，请检查SQL文件或数据库连接")
        except Exception as e:
            logging.error(f"导入异常: {str(e)}")
            return DbImportResult(False, f"导入失败: {str(e)}")
    
    def _detect_file_encoding(self, sql_file: str) -> str:
        for encoding in ("utf-8", "gbk"):
            try:
                with open(sql_file, "r", encoding=encoding) as f:
                    f.read(1024 * 1024)
                return encoding
            except UnicodeDecodeError:
                continue
        return "utf-8"
    
    def _stream_sql_to_process(
        self,
        process: subprocess.Popen,
        sql_file: str,
        encoding: str,
        file_size_mb: float,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ):
        bytes_read = 0
        last_progress = 10
        
        with open(sql_file, "r", encoding=encoding, errors="replace") as f:
            for line in f:
                sanitized = self._sanitize_database_references(line)
                encoded = sanitized.encode("utf-8")
                process.stdin.write(encoded)
                bytes_read += len(line.encode(encoding, errors="replace"))
                
                if progress_callback and file_size_mb > 0:
                    progress = 10 + int(min(bytes_read / (file_size_mb * 1024 * 1024), 1) * 75)
                    if progress >= last_progress + 2:
                        last_progress = progress
                        progress_callback(progress, f"导入中... {progress}%")
        
        process.stdin.close()
    
    def _sanitize_database_references(self, line: str) -> str:
        system_dbs = {'information_schema', 'mysql', 'performance_schema', 'sys'}
        
        def replace_quoted(match):
            db_name = match.group(1)
            if db_name in system_dbs:
                return match.group(0)
            return ""
        
        return re.sub(r'`([^`]+)`\.', replace_quoted, line)
    
    def _get_tables_count(self, db_name: str) -> int:
        try:
            result = subprocess.run(
                [self.mysql_path, '-u', self.username, f'-p{self.password}',
                 '-h', self.host, '-P', str(self.port),
                 '-N', '-e', f"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='{db_name}';"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                for line in output.split('\n'):
                    line = line.strip()
                    if line and line.isdigit():
                        return int(line)
            return 0
        except:
            return 0
    
    def get_tables(self, db_name: str) -> tuple[list[str], str]:
        try:
            result = subprocess.run(
                [self.mysql_path, '-u', self.username, f'-p{self.password}',
                 '-h', self.host, '-P', str(self.port),
                 '-N', '-e', f"USE `{db_name}`; SHOW TABLES;"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                tables = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                return tables, ""
            else:
                return [], result.stderr.strip()
        except Exception as e:
            return [], str(e)
