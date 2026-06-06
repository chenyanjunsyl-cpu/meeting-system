# 会议室预定系统

一个面向内网环境的会议室预定系统，支持普通用户预约会议室、维护会议纪要，管理员维护用户、会议室基础数据和 AD 域控登录配置。项目已提供本地运行、Linux 离线部署和 Docker 离线镜像三种交付方式。

## 功能介绍

- 用户登录：支持本地账号登录，也支持配置 AD 域控后使用域账号登录。
- 会议室预约：按会议室、日期、时间段创建预约，自动校验时间冲突。
- 一周预约总览：首页展示一周内各会议室预约情况，方便提前规划。
- 当天预约明细：点击一周总览中的日期卡片查看当天详细预约。
- 我的会议：用户查看自己预约的会议、需要参加的会议，并在会议开始后填写或修改自己预约会议的纪要。
- 历史查询：按日期范围、会议室筛选历史会议。
- CSV 导出：导出历史会议数据，包含会议纪要列。
- 管理后台：新增、删除本地用户，分配普通用户或管理员权限。
- AD 域控配置：管理员可配置 LDAP/LDAPS、Base DN、用户过滤器、管理员组 DN，并从 AD 获取用户。
- 离线部署：提供 Linux 离线 wheelhouse、SQLite 数据库、Docker 镜像 tar 包和一键启动脚本。

## 默认账号

首次启动后可使用以下本地账号登录：

```text
管理员：admin / admin123
普通用户：user / user123
```

上线到正式内网后，建议尽快修改默认密码，或配置 AD 域控后限制本地账号使用。

## 项目结构

```text
.
├── app.py                         # Flask Web 应用
├── models.py                      # SQLite 数据访问与初始化
├── ad_service.py                  # AD/LDAP 登录与查询
├── templates/                     # 前端页面模板
├── rooms.json                     # 会议室配置
├── meeting.db                     # SQLite 数据库
├── requirements.txt               # Python 依赖
├── Dockerfile                     # Docker 镜像构建文件
├── scripts/                       # 安装、启动、打包脚本
├── README_OFFLINE.md              # 内网离线部署说明
└── dist/
    ├── meeting-system-offline.zip # 离线完整交付包
    └── meeting-system-offline/
        └── meeting-system-docker.tar # Docker 离线镜像
```

## 本地开发运行

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

访问：

```text
http://127.0.0.1:5000/
```

如果需要避免 Flask 调试重载产生多个进程，可以用：

```powershell
.\.venv\Scripts\python.exe -c "from app import app; app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)"
```

## Docker 使用

### 从源码构建并运行

```bash
docker build -t meeting-system:offline .
docker run -d --name meeting-system -p 5000:5000 -v "$(pwd)/docker-data:/data" meeting-system:offline
```

访问：

```text
http://服务器IP:5000/
```

### 使用离线镜像启动

进入离线包目录后执行：

```bash
chmod +x scripts/*.sh
./scripts/docker_start.sh
```

停止：

```bash
./scripts/docker_stop.sh
```

自定义端口：

```bash
PORT=8080 ./scripts/docker_start.sh
```

## Linux 离线部署

内网 Linux 服务器需要已安装 Python 3.10+。离线包内包含 Python 依赖 wheelhouse，不需要联网下载模块。

```bash
unzip meeting-system-offline.zip
cd meeting-system-offline
chmod +x scripts/*.sh
./scripts/install_linux.sh
./scripts/run_linux.sh
```

停止：

```bash
./scripts/stop_linux.sh
```

常用环境变量：

```bash
export HOST=0.0.0.0
export PORT=5000
export SECRET_KEY='change-this-secret-key'
export MEETING_DB_PATH=/path/to/meeting.db
export ROOMS_CONFIG_PATH=/path/to/rooms.json
```

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
- 显示名字段、邮箱字段

保存后可以在页面上测试 AD 连接，并按需给 AD 用户分配管理员权限。

## 重新生成离线包和 Docker 镜像

Windows 开发机：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_offline.ps1
```

输出物：

```text
dist\meeting-system-offline
dist\meeting-system-offline.zip
dist\meeting-system-offline\meeting-system-docker.tar
```

Linux Docker 环境：

```bash
./scripts/docker_build_save.sh
```

## GitHub 上传建议

本仓库包含离线交付包和 Docker 镜像 tar 文件。`meeting-system-docker.tar` 目前小于 GitHub 单文件 100 MB 限制，可以直接提交；如果后续镜像超过限制，建议改用 GitHub Release 附件或 Git LFS。
