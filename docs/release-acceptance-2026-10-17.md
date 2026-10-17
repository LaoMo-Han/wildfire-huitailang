# 2026.10.17.1 发布验收

构建号 6，基础客户端仍为 1.0.192，复用已发布的本体分卷与 core 组件。

## 首版覆盖升级

以 `artifacts/wildfire-huitailang-patch-20261014.zip` 为首版补丁；确认其没有
`update.exe`。在 `analysis/release_20261017/legacy-overlay-client` 创建独立客户端，
覆盖首版补丁，再覆盖本次完整 `wildfire-patch-2026.10.17.1.zip`。

- ZIP 完整性、文件清单、SHA-256 与新版本清单一致。
- 新包包含新版入口、启动器、更新器、bootstrap、完整运行脚本及已验证的核心文件。
- 不含个人档案、画面设置、账号偏好、调试命令、诊断入口或密钥。
- 模拟好友的 `game/conf.xml`、`game/personal.xml` 与离线档案字节保持不变。
- 使用覆盖后的“开始游戏.exe”启动原生游戏，等待实际命令回执；进入 `zc_new01`，
  大厅输入模式为 2，未报告运行时错误。检查器可正常读取版本状态。

覆盖包大小 40,265,716 字节；SHA-256：
`b50be9fbc5b28c2b259d97a92abc82c04b05d7e35434adbebfb5c1b478ea5b15`。
自动更新仅需新的 runtime 与 launcher 完整组件，分别为 50,200 和 32,807 字节。

## 检查

- `python -m unittest discover -s tools -p 'test_*.py'`：47 项通过。
- `tools/UpdateTests.cs`：12 项安装、回滚、跨版本、损坏包及设置保留检查通过。
- `tools/LauncherBackgroundTests.cs`：3 项网络失败、并发请求和状态写入失败检查通过。
- 大厅鼠标与设置关闭后的实际界面验收见 `hall-controls-2026-10-17.md`。

本轮未逐一验收所有英雄与地图，也未重新打包未变化的本体素材。
