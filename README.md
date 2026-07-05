# frpc Android Root Module / frpc Android Root 模块
![Uploading 屏幕截图 2026-07-05 134737.png…]()

## English Introduction

1. This module does **not** include the `frpc` binary. During installation or update, it downloads `frpc` from the official open-source `frp` release for Android Root environments.
2. Supports Magisk, KernelSU, APatch, and similar Root module environments.
3. Includes a built-in web console.  
   **Default address:** `http://127.0.0.1:62930`
4. Supports starting and stopping `frpc` from the web console.
5. Supports low memory mode: after `frpc` starts, the web console is closed, and only `frpc` plus a lightweight guard remain resident.
6. Supports proxy management, including adding, editing through configuration, and deleting proxy entries.
7. Supports editing the `frpc.toml` configuration file.
8. Supports viewing and clearing `frpc`, service, update, and web logs.
9. Supports account settings. By default, no username or password is set, and first access skips login. After an account is configured, the login session is valid for 24 hours and can be logged out manually.
10. Supports Root manager status display, including web mode, `frpc` status, and web address.
11. Tapping the module action button refreshes the status. Start, stop, and mode switching update the module description immediately.
12. Supports boot auto-start and background guard. If `frpc` exits unexpectedly, it can be restarted automatically.
13. The web interface supports switching between English and Chinese, with English as the default language.

---

## 中文说明

1. 本模块**不内置** `frpc` 二进制文件；安装或更新时会从 `frp` 官方开源发布地址下载 `frpc`，用于在 Android Root 环境中运行。
2. 支持 Magisk、KernelSU、APatch 等 Root 模块环境。
3. 内置 Web 后台。  
   **默认地址：** `http://127.0.0.1:62930`
4. 支持通过 Web 后台启动、停止 `frpc`。
5. 支持最小内存运行模式：启动 `frpc` 后关闭 Web 后台，只保留 `frpc` 和轻量守护进程。
6. 支持代理管理，可添加、通过配置编辑、删除代理配置。
7. 支持编辑 `frpc.toml` 配置文件。
8. 支持查看、清除 `frpc`、service、update、web 等运行日志。
9. 支持账号设置：默认无用户名和密码，首次进入后台免登录；设置账号密码后，登录有效期为 24 小时，可主动退出登录。
10. 支持模块管理器状态显示，包括 Web 模式、`frpc` 运行状态、Web 地址。
11. 点击模块管理器操作按钮时会刷新状态；启动、停止、切换模式时会即时刷新模块说明。
12. 支持开机自启和后台守护，`frpc` 异常退出后可自动拉起。
13. Web 界面支持中英文切换，默认语言为英文。

---

## Module Directory / 模块目录

```sh
/data/adb/modules/frpc
```

---

## Data Directory / 数据目录

```sh
/data/adb/frpc
```

---

## Main Files / 主要文件说明

| File / 文件 | Description / 说明 |
|---|---|
| `frpc` | Downloaded `frpc` binary after installation or update. It is not included in the module package.<br>安装或更新后下载得到的 `frpc` 二进制文件，模块包内不自带。 |
| `frpc.toml` | `frpc` configuration file.<br>`frpc` 配置文件。 |
| `frpc.log` | `frpc` runtime log.<br>`frpc` 运行日志。 |
| `webui.sh` | Web console service script.<br>Web 后台服务脚本。 |
| `frpc.cgi` | Web console page script.<br>Web 后台页面脚本。 |
| `service.sh` | Boot startup and background guard script.<br>开机启动和后台守护脚本。 |
| `action.sh` | Root manager action button script.<br>Root 管理器操作按钮脚本。 |
| `webroot/index.html` | Root manager web button page, used to open the local `frpc` web console.<br>Root 管理器 Web 按钮页面，用于打开本机 `frpc` Web 控制台。 |
