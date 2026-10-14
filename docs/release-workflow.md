# 发布、反馈和更新

公开发布页：<https://laomo-han.github.io/wildfire-downloads/>。
公开仓库 `LaoMo-Han/wildfire-downloads` 只放网页、版本清单和 Release 成品。
游戏源码仓库 `wildfire-huitailang` 保持私有。

## 给朋友的文件

首次安装：在发布页下载全部本体分卷，放到同一个目录，用 7-Zip 解压 `.001`，
再双击 `开始游戏.exe`。本体已经有更新器；首次启动如提示新版本，确认下载即可。

已有完整 1.0.192 客户端：退出游戏，下载最新 `wildfire-patch-版本.zip`，
解压到客户端根目录、合并并替换。补丁没有人物、地图、声音素材，不能单独运行。
早期单机版本需要手动覆盖一次此补丁，之后使用游戏内更新。

补丁不会带入或覆盖 `game/conf.xml`、`personal.xml`、`offline_profile.json`。
请勿发送开发用 `offline_client` 的档案、日志、截图和调试命令。
发布工具按名单组装成品，清空本体中的原账号界面偏好，排除开发残留。

## 日常发布

需要 Python 3、Windows .NET Framework 编译器、已有 GitHub Git 凭据。
首次本体发布另需安装 7-Zip。先退出构建目录中的游戏；正在玩的客户端请使用另一份构建副本。
联网命令需要允许网络访问，凭据只在发布进程内存中使用。

```powershell
python tools/publish_release.py --client "C:\offline-build" --version 2026.10.15.1 --build 3 --notes docs/releases/2026.10.15.1.txt
```

构建号必须递增；版本号和更新说明由维护者明确填写。
初次发布或重新制作本体时加 `--include-base`，每卷为 1500 MiB。
日常不加这个参数，本体分卷链接继续复用；只上传变化的完整组件和完整手动补丁。
可以用 `--previous site/latest.json` 明确指定上次清单。

断网准备或发布前检查：加 `--prepare-only`。
生成物位于 `artifacts/releases/版本/`。校验、解压和启动检查通过后上传：

```powershell
python tools/publish_release.py --resume artifacts/releases/2026.10.15.1
```

上传中断后再次执行同一 `--resume` 命令。工具保留草稿 Release，核对附件大小和
GitHub 返回的 SHA-256；草稿中不完整或不匹配的附件会重新上传。
所有附件验证后才公开 Release，最后在同一个网页提交中更新 `latest.json`。
不要重新生成已公开版本；修复使用新版本和新构建号。

## 客户端行为

C# 启动器启动时后台检查，之后每五分钟检查，也接收游戏内手动请求。
游戏 Python 2 只写 `game/update_request.json`、读 `update_status.json`。
更新器负责 HTTPS、SHA-256、ZIP 文件名单、空间检查和安装。
基础二进制、运行脚本、启动器三个组件都是完整最新版本；允许跳过多个版本。

玩家点确认后才下载。运行中的游戏文件不会被覆盖，下载存入 `.updates`。
下载后选择“退出并更新”，正常退出后独立程序安装并重启。
若下载好后自行正常退出，安装器也会安装，下次启动使用新版。
安装前备份受管理文件、记录日志；每个文件使用原子替换，最后提交版本号。
失败恢复备份，断电后由下次启动读取 journal 恢复。最新一次备份保留在 `.updates`。
独立原子替换会断开目标硬链接，不直接改写原客户端共享素材。

## 反馈服务与管理

服务：`https://wildfire-feedback.568122642.workers.dev`，管理页路径 `/admin`。
管理口令只保存在本机 `.local-secrets/feedback-admin.txt`；该目录被 Git 忽略，
也不在发布包中。请单独保存此文件，不要发给朋友。
Turnstile 后台密钥、管理口令哈希和会话签名密钥仅保存在 Worker 绑定中。

匿名反馈提交后公开；版本选填，最多三张截图。浏览器去除截图元数据并压缩到
每张 512 KiB，服务端核验格式、大小和 Turnstile，并限制每 IP 每分钟三次提交。
图片总量达到 400 MiB 时事务中止图片提交；文字反馈仍可提交，不启用付费服务。
隐藏反馈的文字和图片都不再对公众返回，管理员可以查看隐藏内容、修改状态和修复版本。

Worker 源码、D1 初始化脚本和绑定配置在 `services/feedback/`。
部署更新时保留 `secret_text` 绑定，不把密钥写入配置文件。
网页修改可执行 `python tools/publish_site.py`，不会覆盖线上版本清单。

## 验证

`tools/UpdateTests.cs`：安装、跨版本文件替换、设置保留、破损包、越界 ZIP、
中途失败、断电 journal、空间不足和文件占用。
`services/feedback/tests/worker.test.mjs`：真实 SQLite 事务，隔离的 Siteverify 测试响应，
检查匿名图文、校验、限流、额度回滚、管理会话、来源限制和隐藏。
此测试不改变线上 Turnstile，不等同于真实浏览器完成验证并提交。

发布前还应实际从分卷解压启动，检查大厅和练习场入口，并用一份旧客户端完成
“公开修复版本 → 检查 → 下载 → 正常退出 → 安装 → 重启”的实测。
