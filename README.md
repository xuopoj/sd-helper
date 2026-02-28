# sd-helper

华为云服务交付工程师的命令行工具，用于简化日常运维操作。

## 安装

**在线安装：**

```bash
pip install sd-helper-cli
```

**离线安装（服务器无外网）：**

在有网络的机器上下载依赖包：

```bash
# 默认 ARM64 / Python 3.9，可通过参数调整
bash scripts/download_wheels.sh
bash scripts/download_wheels.sh --platform manylinux2014_x86_64 --python-version 3.10

# 将生成的 sd-helper-offline.tar.gz 传输到服务器
scp sd-helper-offline.tar.gz user@server:/tmp/
```

在服务器上安装到 virtualenv：

```bash
bash install.sh --archive /tmp/sd-helper-offline.tar.gz
source ~/.venv/sd-helper/bin/activate
sd-helper --version
```

## 功能模块

### IAM 认证

```bash
# 配置凭据
sd-helper iam configure

# 获取 token
sd-helper iam token

# 查看已配置的 profile
sd-helper iam list-profiles

# 设置默认 profile
sd-helper iam set-default <profile>
```

### LLM 对话

与 ModelArts / 盘古大模型进行对话。

```bash
# 添加模型配置
sd-helper llm add <model-name> --endpoint <url> --type modelarts

# 查看已配置的模型
sd-helper llm list

# 单次对话
sd-helper llm chat "你好"

# 携带文件上下文
sd-helper llm chat -f code.py "解释这段代码"

# 视觉模型（图片输入）
sd-helper llm chat -i image.jpg "描述这张图片"

# 交互式对话（进入 TUI 界面）
sd-helper llm chat
```

### Docker 镜像管理

批量加载并推送镜像到 SWR，支持断点续传。

**前提条件：** 环境已安装 docker，并完成 SWR 登录。

```bash
# 校验资产清单中的文件是否完整
sd-helper docker upload-images --config config.yaml --dir /path/to/files --validate

# 试运行（只打印命令，不执行）
sd-helper docker upload-images --config config.yaml --dir /path/to/files --dry-run

# 正式上传
sd-helper docker upload-images --config config.yaml --dir /path/to/files

# 重置所有进度（重新上传）
sd-helper docker upload-images --reset-all

# 重置指定镜像的进度
sd-helper docker upload-images --reset "name:tag"
```

配置文件示例（`config.yaml`）：

```yaml
assets_file: 资产清单.txt        # 资产清单文件，只处理其中的 镜像 分区

swr:
  endpoint: swr.cn-north-4.myhuaweicloud.com
  org: com-huaweicloud-dataengineering

cleanup_after_push: false        # 设为 true 可在推送后删除本地镜像
```

后台运行：

```bash
nohup sd-helper docker upload-images --config config.yaml --dir /path/to/files > upload.log 2>&1 &
echo $!                  # 记录 PID
tail -f upload.log        # 查看实时日志
cat .progress.json        # 查看每个镜像的上传状态
```

### 数据管理

离线收集和同步数据。

```bash
# 采集数据
sd-helper data collect --name <name>

# 查看已采集的数据
sd-helper data list

# 使用模板批量执行请求
sd-helper data run <template.yaml>
```

## 独立脚本

`scripts/upload_images.py` 是一个独立版本的镜像上传脚本，仅依赖 `pyyaml`，可直接复制到目标节点使用：

```bash
python upload_images.py --config config.yaml --dir /path/to/files
```

后台运行：

```bash
nohup python upload_images.py --config config.yaml --dir /path/to/files > upload.log 2>&1 &
echo $!                  # 记录 PID
tail -f upload.log        # 查看实时日志
cat .progress.json        # 查看每个镜像的上传状态
```