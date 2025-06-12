#!/usr/bin/env python3

import os
import re
import json
import time
import subprocess
from datetime import datetime

import requests

# Configuration - Replace with your actual values
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
API_KEY = os.getenv("API_KEY", "your_api_key_here")  # SiliconFlow API Key
# MODEL_NAME = "Qwen/Qwen3-30B-A3B"
# MODEL_NAME = "Qwen/Qwen3-32B"
# MODEL_NAME = "Qwen/Qwen2.5-72B-Instruct"
MODEL_NAME = "deepseek-ai/DeepSeek-R1"
# MODEL_NAME = "Pro/deepseek-ai/DeepSeek-V3"
# MODEL_NAME = "Pro/deepseek-ai/DeepSeek-R1"


# Fix for Function Calling compatibility
# Suppress hallucinations
my_tool_calls = [
    {
    "index": 0,
    "id": "019754ff27a5486c229494494256c77f",
    "type": "function",
    "function": {
        "name": "check_hostnamectl_info",
        "arguments": " {}"
    }
    },
    {
    "index": 1,
    "id": "019754ff2926f98aa40602a84183ee00",
    "type": "function",
    "function": {
        "name": "check_cpu_info",
        "arguments": " {}"
    }
    },
    {
    "index": 2,
    "id": "019754ff2a9eda9628939e9a0fe7bddd",
    "type": "function",
    "function": {
        "name": "check_cpu_usage",
        "arguments": " {\"duration\": 10}"
    }
    },
    {
    "index": 3,
    "id": "019754ff2c9a23f12d58393793f8ade9",
    "type": "function",
    "function": {
        "name": "check_memory_usage",
        "arguments": " {}"
    }
    },
    {
    "index": 4,
    "id": "019754ff2e33e60d62569e55fd9edeba",
    "type": "function",
    "function": {
        "name": "check_disk_io",
        "arguments": " {\"device\": \"all\"}"
    }
    },
    {
    "index": 5,
    "id": "019754ff302e079b556b9b8db9b10c04",
    "type": "function",
    "function": {
        "name": "check_running_processes",
        "arguments": " {\"top_n\": 5}"
    }
    },
    {
    "index": 6,
    "id": "019754ff2926f98aa40602a84183ee01",
    "type": "function",
    "function": {
        "name": "check_network_info",
        "arguments": " {}"
    }
    },

]


def parse_ss_s(ss_output: str):
    """
    分析 'ss -s' 命令的输出字符串。

    Args:
        ss_output: 'ss -s' 命令产生的字符串输出。

    Returns:
        一个字典，表示分析结果。
        - 成功: {"status": "success", "data": {...}}
        - 失败: {"status": "error", "message": "..."}
    """
    try:
        ss_data = {
            "Total": 0,
            "TCP_summary": {
                "total": 0,
                "states": {}
            },
            "Transport": {}
        }
        lines = ss_output.strip().split('\n')
        
        parsing_transport_table = False
        transport_headers = []

        for line in lines:
            if not line.strip():
                continue

            if line.startswith("Total:"):
                ss_data["Total"] = int(line.split(':')[1].strip())
                continue

            if line.startswith("TCP:"):
                match = re.match(r"TCP:\s+(\d+)\s+\((.*)\)", line)
                if match:
                    ss_data["TCP_summary"]["total"] = int(match.group(1))
                    states_str = match.group(2)
                    state_pairs = states_str.split(',')
                    for pair in state_pairs:
                        key, value = pair.strip().split()
                        ss_data["TCP_summary"]["states"][key] = int(value)
                else:
                    ss_data["TCP_summary"]["total"] = int(line.split(':')[1].split('(')[0].strip())
                continue
            
            if line.startswith("Transport"):
                parsing_transport_table = True
                transport_headers = line.split()[1:] 
                continue

            if parsing_transport_table:
                parts = line.strip().split()
                if not parts: continue # 再次跳过空行
                protocol_name = parts[0]
                values = [int(v) for v in parts[1:]]
                ss_data["Transport"][protocol_name] = dict(zip(transport_headers, values))

        # 校验是否解析到了关键数据，防止输入为空或完全不相关的内容
        if not ss_data["Total"] and not ss_data["Transport"]:
            raise ValueError("Input does not contain valid 'ss -s' data.")

        return {"status": "success", "data": ss_data}

    except Exception as e:
        return {"status": "error", "message": str(e)}

def check_network_info():
    """
    执行 'ss -s' 命令并调用分析函数。
    
    Returns:
        一个字典，包含从 'ss -s' 命令分析得出的网络信息，或在执行失败时返回错误信息。
    """
    try:
        # 定义要执行的命令
        command = ["ss", "-s"]
        
        # 执行命令。
        # - capture_output=True: 捕获标准输出和标准错误。
        # - text=True: 将输出解码为文本。
        # - check=True: 如果命令返回非零退出码（即失败），则引发 CalledProcessError。
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        # 将命令的标准输出传递给分析函数
        return parse_ss_s(result.stdout)

    except FileNotFoundError:
        # 如果系统中没有'ss'命令，会触发此异常
        return {
            "status": "error", 
            "message": "Command 'ss' not found. Please ensure it is installed and in the system's PATH."
        }
    except subprocess.CalledProcessError as e:
        # 如果 'ss -s' 命令执行失败（例如，权限不足），会触发此异常
        return {
            "status": "error", 
            "message": f"Command 'ss -s' failed with error: {e.stderr.strip()}"
        }
    except Exception as e:
        # 捕获其他任何意外错误
        return {"status": "error", "message": f"An unexpected error occurred: {str(e)}"}


# Check CPU hardware information
def check_cpu_info():
    """
    Executes the lscpu -J command and parses the result into a JSON structure.
    
    Returns:
        dict: Contains the status and the parsed data.
    """
    try:
        # Execute lscpu command
        result = subprocess.run(
            ['lscpu', '-J'],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse JSON output
        lscpu_data = json.loads(result.stdout)
        return {"status": "success", "data": lscpu_data}
    
    except subprocess.CalledProcessError as e:
        # Handle command execution failure
        return {"status": "error", "message": f"Command execution failed: {e.stderr.strip()}"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    

# System information
def check_hostnamectl_info():
    """
    Executes the hostnamectl command and parses the result into a JSON structure.
    
    Returns:
        dict: Contains the status and the parsed data.
    """
    try:
        # Execute hostnamectl command
        result = subprocess.run(
            ['hostnamectl', '--json=pretty'],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse JSON output
        hostnamectl_data = json.loads(result.stdout)
        return {"status": "success", "data": hostnamectl_data}
    
    except subprocess.CalledProcessError as e:
        # Handle command execution failure
        return {"status": "error", "message": f"Command execution failed: {e.stderr.strip()}"}
    
    except json.JSONDecodeError:
        # Fallback to text parsing if the system does not support JSON output
        return parse_text_hostnamectl()

def parse_text_hostnamectl():
    """
    Text parsing method for when hostnamectl does not support JSON output.
    """
    try:
        # Execute hostnamectl command
        result = subprocess.run(
            ['hostnamectl'],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse text output
        data = {}
        for line in result.stdout.splitlines():
            # Skip empty lines and icon lines
            if not line.strip() or "Icon name" in line or "Chassis" in line and ":" not in line:
                continue
            
            # Split key-value pairs
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().replace(" ", "_").lower()
                value = value.strip()
                
                # Special handling for the Firmware Age line
                if "firmware_age" in data and key == "firmware_age":
                    continue
                
                data[key] = value
        
        # Unified handling for special fields
        if "icon_name" in data and "chassis" in data:
            data["chassis"] = f"{data['chassis']} {data.get('icon_name', '')}"
            del data["icon_name"]
        
        return {"status": "success", "data": data}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Performance monitoring function implementations
def check_cpu_usage(duration=5):
    """Check CPU usage and load."""
    try:
        # Use mpstat to collect data
        result = subprocess.run(
            ["mpstat", "-P", "ALL", str(duration), "1"],
            capture_output=True, text=True, timeout=duration+5
        )
        # Simplified parsing - more complete parsing is needed in a real application
        lines = result.stdout.split('\n')
        cpu_data = {}
        for line in lines:
            if line.startswith("Average:") and "all" in line:
                parts = line.split()
                cpu_data = {
                    "user": float(parts[2]),
                    "system": float(parts[4]),
                    "idle": float(parts[11]),
                    "load_1min": os.getloadavg()[0]
                }
        return {"status": "success", "data": cpu_data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def check_memory_usage():
    """Check memory usage."""
    try:
        result = subprocess.run(
            ["free", "-m"], capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.split('\n')
        mem_line = lines[1].split()
        swap_line = lines[2].split()
        return {
            "status": "success",
            "data": {
                "total_mb": int(mem_line[1]),
                "used_mb": int(mem_line[2]),
                "free_mb": int(mem_line[3]),
                "swap_used_mb": int(swap_line[2])
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def check_disk_io(device="all"):
    """Check disk I/O performance and return structured data."""
    try:
        # Increase sampling count for better reliability
        cmd = ["iostat", "-d", "-x", "-y", "1", "3"]  # Change to 3 samples
        
        # Execute command
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=20  # Increase timeout
        )
        
        # Check if the command executed successfully
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Command failed to execute"
            return {"status": "error", "message": error_msg}
            
        # Parse output
        return parse_iostat_output(result.stdout, device)
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Command timed out"}
    except Exception as e:
        return {"status": "error", "message": f"Execution error: {str(e)}"}

def parse_iostat_output(output, tarcheck_device):
    """Parse iostat output - enhanced version."""
    # Split the output into lines
    lines = output.strip().split('\n')
    
    # If there is no output content
    if not lines or len(lines) < 3:
        return {"status": "error", "message": "iostat output is empty or has an abnormal format"}
    
    # Find all data blocks
    data_blocks = []
    current_block = []
    in_block = False
    
    for line in lines:
        # Detect header line
        if line.startswith("Device"):
            # If already in a data block, end the current one
            if in_block:
                data_blocks.append(current_block)
                current_block = []
            in_block = True
            headers = [h.lower() for h in line.split()]
            current_block.append(headers)
            continue
            
        # If it is a data line
        if in_block and line.strip():
            parts = line.split()
            # Ensure there are enough data columns
            if len(parts) >= len(headers):
                current_block.append(parts)
    
    # Add the last block
    if in_block and current_block:
        data_blocks.append(current_block)
    
    # If no data blocks were found
    if not data_blocks:
        return {"status": "error", "message": "No valid data blocks found"}
    
    # Select the most suitable data block (prefer the last one)
    selected_block = None
    
    # Try to use the last data block
    if data_blocks:
        selected_block = data_blocks[-1]
    
    # If the last block only has a header and no data, try the previous one
    if selected_block and len(selected_block) == 1:
        for block in reversed(data_blocks):
            if len(block) > 1:
                selected_block = block
                break
    
    # If a valid block is still not found
    if not selected_block or len(selected_block) < 2:
        return {"status": "error", "message": "Not enough data rows found"}
    
    # Parse the selected data block
    headers = selected_block[0]
    data_lines = selected_block[1:]
    
    # Parse data
    devices = []
    for parts in data_lines:
        # Device name is the first column
        device_name = parts[0]
        
        # If a specific device is specified, skip others
        if tarcheck_device != "all" and device_name != tarcheck_device:
            continue
            
        # Create a data dictionary for the device
        device_data = {"device": device_name}
        
        # Parse various metrics
        for i in range(1, min(len(headers), len(parts))):
            header = headers[i]
            value_str = parts[i]
            
            # Handle special values
            if value_str == "0.00" or value_str == "0.0":
                value = 0.0
            else:
                try:
                    value = float(value_str)
                except ValueError:
                    value = value_str  # Keep the original string
            
            device_data[header] = value
        
        devices.append(device_data)
    
    # If a specific device was specified but not found
    if tarcheck_device != "all" and not devices:
        return {
            "status": "error", 
            "message": f"Device not found: {tarcheck_device}",
            "available_devices": [block[0] for block in data_lines]
        }
    
    # Calculate key metrics
    key_metrics = {
        "total_iops": 0.0,
        "total_throughput": 0.0,
        "max_utilization": 0.0,
        "device_count": len(devices)
    }
    
    if devices:
        # Calculate total throughput and IOPS
        for d in devices:
            # Compatible with different iostat version column names
            rps = d.get("r/s", d.get("rsec/s", 0)) / 2.0  # Conversion needed if using rsec/s
            wps = d.get("w/s", d.get("wsec/s", 0)) / 2.0
            
            key_metrics["total_iops"] += rps + wps
            key_metrics["total_throughput"] += d.get("rkb/s", d.get("rkB/s", 0)) + d.get("wkb/s", d.get("wkB/s", 0))
            
            # Check maximum utilization
            util = d.get("%util", 0.0)
            if util > key_metrics["max_utilization"]:
                key_metrics["max_utilization"] = util
    
    # Keep original output for debugging
    debug_info = {
        "output_lines": len(lines),
        "blocks_found": len(data_blocks),
        "selected_block_size": len(selected_block),
        "devices_found": len(devices)
    }
    
    return {
        "status": "success",
        "data": {
            "devices": devices,
            "summary": key_metrics,
            "timestamp": datetime.now().isoformat(),
            "debug": debug_info  # Debug information
        }
    }

def check_running_processes(top_n=5):
    """Check processes with the highest resource consumption."""
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,user,%cpu,%mem,comm", "--sort=-%cpu"],
            capture_output=True, text=True, timeout=5
        )
        processes = []
        for line in result.stdout.split('\n')[1:top_n+1]:
            if line.strip():
                parts = line.split(maxsplit=4)
                processes.append({
                    "pid": parts[0],
                    "user": parts[1],
                    "cpu": float(parts[2]),
                    "mem": float(parts[3]),
                    "command": parts[4] if len(parts) > 4 else ""
                })
        return {"status": "success", "data": processes}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Function mapping dictionary
FUNCTION_MAP = {
    "check_cpu_usage": check_cpu_usage,
    "check_memory_usage": check_memory_usage,
    "check_disk_io": check_disk_io,
    "check_running_processes": check_running_processes,
    "check_hostnamectl_info": check_hostnamectl_info,
    "check_cpu_info": check_cpu_info,
    "check_network_info": check_network_info,
}

# Function definitions - for API calls
TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "check_cpu_usage",
            "description": "Check CPU usage and load status",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {
                        "type": "integer",
                        "description": "Monitoring duration (seconds)",
                        "default": 5
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_memory_usage",
            "description": "Check memory and Swap usage",
            "parameters": {}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_disk_io",
            "description": "Check disk IO performance",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {
                        "type": "string",
                        "description": "Disk device name (e.g., sda)",
                        "default": "all"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_running_processes",
            "description": "Check processes with the highest resource consumption",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Number of processes to display",
                        "default": 5
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_hostnamectl_info",
            "description": "Check basic system information",
            "parameters": {
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_cpu_info",
            "description": "Check CPU configuration information",
            "parameters": {
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_network_info",
            "description": "Check socket usage summary",
            "parameters": {
            }
        }
    },

]

def call_siliconflow_api(messages, tools=None, tool_choice="auto"):
    """Call the SiliconFlow API"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "tool_choice": tool_choice,
        "tools": tools if tools else TOOLS_DEFINITION
    }
    
    try:
        response = requests.post(
            API_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=600
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"API call failed: {str(e)}"}

def execute_tool_calls(tool_calls):
    """Execute tool calls and return results."""
    tool_responses = []
    
    for call in tool_calls:
        func_name = call["function"]["name"]
        
        # Safely parse arguments
        try:
            args_str = call["function"].get("arguments")
            if args_str and isinstance(args_str, str):
                # Attempt to parse, handling potential malformed JSON from the model
                arguments = json.loads(args_str)
            else:
                arguments = {} # Default to empty dictionary if no arguments or not a string
        except json.JSONDecodeError as e:
            print(f"⚠️ Warning: Could not decode arguments for {func_name}. Received: '{args_str}'. Error: {e}")
            arguments = {} # Default to empty dictionary
        except TypeError as e:
            print(f"⚠️ Warning: Arguments for {func_name} is not a string or unexpected type. Received: '{args_str}'. Error: {e}")
            arguments = {} # Default to empty dictionary


        if func_name in FUNCTION_MAP:
            # Execute the function
            result = FUNCTION_MAP[func_name](**arguments)
            tool_responses.append({
                "role": "tool",
                "content": json.dumps(result),
                "tool_call_id": call["id"]
            })
        else:
            tool_responses.append({
                "role": "tool",
                "content": json.dumps({"error": f"Unknown function: {func_name}"}),
                "tool_call_id": call["id"]
            })
    
    return tool_responses

def analyze_performance():
    """Main analysis function."""
    # Initialize conversation
    messages = [
        {
            "role": "system",
            "content": "You are a Linux system performance expert. The user will describe a performance issue, and you need to call tool functions to check system metrics, then analyze the cause of the problem and provide solution recommendations."
        },
        {
            "role": "user",
            "content": "My Linux server is responding very slowly. Please help me analyze the performance issue. The report output format is Markdown."
        }
    ]
    
    print("🔍 Starting performance analysis...")
    print("📡 Contacting the large model for initial diagnosis...")
    
    # First API call - to request tool calls
    response = call_siliconflow_api(messages)
    
    if "error" in response:
        print(f"❌ Error: {response['error']}")
        return
    
    # Parse the response
    try:
        choice = response["choices"][0]
        message = choice["message"]
        messages.append(message)
        
        # Note: Manually inserting tool calls
        message["tool_calls"] = my_tool_calls
        if "tool_calls" in message:
            print("⚙️ The large model requested the following performance checks:")
            for call in message["tool_calls"]:
                func = call["function"]
                # Print arguments in a more readable way
                arg_str = func.get('arguments', 'no arguments')
                print(f"  - {func['name']}({arg_str})")
            
            # Execute tool calls
            print("🛠️ Executing system check commands...")
            tool_responses = execute_tool_calls(message["tool_calls"])
            messages.extend(tool_responses)
            
            # Second API call - to get analysis based on tool results
            print("📊 Analyzing check results...")
            analysis_response = call_siliconflow_api(messages)
            
            if "error" in analysis_response:
                print(f"❌ Analysis error: {analysis_response['error']}")
                return
            
            # Display final analysis results
            analysis_message = analysis_response["choices"][0]["message"]
            print("\n" + "="*50)
            print("💡 Performance Analysis Report:")
            print(analysis_message["content"])
            print("="*50)
            
            # Save the report to a file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"performance_report_{timestamp}.txt"
            with open(report_file, "w") as f:
                f.write("Linux Performance Analysis Report\n\n")
                f.write(f"Time: {datetime.now()}\n")
                f.write(f"Author: {MODEL_NAME}\n")
                f.write(analysis_message["content"])
            
            print(f"\n📝 Report saved to: {report_file}")
        else:
            print("\n" + "="*50)
            print("💬 Direct response from the large model:")
            print(message["content"])
            print("="*50)
            
    except KeyError as e:
        print(f"❌ Failed to parse API response: {str(e)}")
        print("Full response:", json.dumps(response, indent=2))

def main():
    """Main function."""
    print("="*50)
    print(f"🖥️ Linux System Performance Diagnostic Assistant ({MODEL_NAME})")
    print("="*50)
    
    if not API_KEY or API_KEY == "your_api_key_here":
        print("❌ Error: Please set a valid API_KEY in your environment variables.")
        return
    
    try:
        # Check if required commands exist
        required_commands = ["mpstat", "iostat", "free", "ps", "hostnamectl", "lscpu"]
        missing = [cmd for cmd in required_commands if not subprocess.run(["which", cmd], stdout=subprocess.DEVNULL).returncode == 0]
        
        if missing:
            print(f"❌ Missing required commands: {', '.join(missing)}")
            print("Please install the sysstat and procps packages:")
            print("  Ubuntu/Debian: sudo apt install sysstat procps")
            print("  RHEL/CentOS: sudo yum install sysstat procps-ng")
            return
        
        analyze_performance()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")

if __name__ == "__main__":
    main()
