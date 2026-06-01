# 会议室预定系统离线部署说明

本离线包用于在无法访问公网的内网 Linux 或 Docker 环境中部署会议室预定系统。

包内包含：

- Flask Web 服务源码
- SQLite 数据库 `meeting.db`
- 会议室配置 `rooms.json`
- Linux 离线 Python wheelhouse
- Docker 镜像文件 `meeting-system-docker.tar`
- Linux 安装/启动/停止脚本
- Docker 启动/停止脚本

## 方式一：Linux 本机离线运行

目标 Linux 服务器需要已安装 Python 3.10+。本包包含 Python 模块离线安装文件，但不包含 Python 解释器。

```bash
chmod +x scripts/*.sh
./scripts/install_linux.sh
./scripts/run_linux.sh
```

默认访问：

```text
http://服务器IP:5000/
```

停止服务：

```bash
./scripts/stop_linux.sh
```

可选环境变量：

```bash
export PORT=5000
export HOST=0.0.0.0
export SECRET_KEY='change-this-secret-key'
export MEETING_DB_PATH=/path/to/meeting.db
export ROOMS_CONFIG_PATH=/path/to/rooms.json
```

## 方式二：Docker 离线运行

目标服务器需要已有 Docker 环境。无需联网下载 Python 模块或数据库软件。

```bash
chmod +x scripts/*.sh
./scripts/docker_start.sh
```

脚本会自动：

- 从 `meeting-system-docker.tar` 加载镜像
- 创建或重建容器 `meeting-system`
- 将数据持久化到 `docker-data`
- 映射端口 `5000:5000`

默认访问：

```text
http://服务器IP:5000/
```

停止 Docker 服务：

```bash
./scripts/docker_stop.sh
```

自定义端口：

```bash
PORT=8080 ./scripts/docker_start.sh
```

如果包内存在 `DOCKER_IMAGE_NOT_BUILT.txt`，说明打包时 Docker Engine 不可用，尚未生成 `meeting-system-docker.tar`。请在能运行 Docker 的开发机上重新执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_offline.ps1
```

或在 Linux Docker 环境中执行：

```bash
./scripts/docker_build_save.sh
```

## 默认账号

首次使用保留本地兜底账号：

```text
管理员：admin / admin123
普通用户：user / user123
```

配置 AD 域控成功后，可使用 AD 域账号登录。建议上线后修改默认账号密码，或限制本地账号使用。

## AD 域控配置

管理员登录后进入：

```text
/admin/users
```

在“AD 域控配置”中填写：

- 域控地址，例如 `ldap://dc.example.local:389`
- 是否启用 LDAPS
- 登录域，例如 `example.local`
- Base DN，例如 `DC=example,DC=local`
- 查询账号 DN 或 UPN
- 查询账号密码
- 用户过滤器，默认 `(&(objectClass=user)(sAMAccountName={username}))`
- 管理员组 DN

保存后点击“测试 AD 连接”。

## 重新打包

在 Windows 开发机项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_offline.ps1
```

输出：

```text
dist\meeting-system-offline
dist\meeting-system-offline.zip
```
