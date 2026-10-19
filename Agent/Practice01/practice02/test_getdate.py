import subprocess
import platform

def getDate():
    """通过调用本地date命令获取当前日期和时间"""
    try:
        system = platform.system()
        print(f"当前操作系统: {system}")
        
        if system == "Windows":
            # Windows系统使用cmd命令获取日期和时间
            print("正在调用Windows date命令...")
            result_date = subprocess.run(
                ["cmd", "/c", "date", "/t"],
                capture_output=True,
                text=True,
                encoding="gbk",
                errors="replace"
            )
            print(f"date命令输出: {result_date.stdout}")
            
            print("正在调用Windows time命令...")
            result_time = subprocess.run(
                ["cmd", "/c", "time", "/t"],
                capture_output=True,
                text=True,
                encoding="gbk",
                errors="replace"
            )
            print(f"time命令输出: {result_time.stdout}")
            
            date_str = result_date.stdout.strip()
            time_str = result_time.stdout.strip()
            return f"当前日期：{date_str}，当前时间：{time_str}"
        else:
            # Linux/macOS系统使用date命令
            print("正在调用Unix date命令...")
            result = subprocess.run(
                ["date"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            print(f"date命令输出: {result.stdout}")
            return result.stdout.strip()
    except Exception as e:
        print(f"异常信息: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"获取日期时间失败：{str(e)}"

if __name__ == "__main__":
    print("=" * 50)
    print("测试getDate工具")
    print("=" * 50)
    result = getDate()
    print("\n最终结果:")
    print(result)
    print("=" * 50)