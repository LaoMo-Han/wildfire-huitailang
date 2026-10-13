# 2026-10-13：原版大厅已验证

验证证据：真实窗口截图显示原版大厅、人物模型、地面与场景碰撞区域；用户确认已进入。`offline_bootstrap.log` 记录：

```text
Local EditorConf loaded; scheduling offline entry.
Requesting the existing local ST_OFFLINE state.
Request completed; resulting state: 2
```

核心补丁是三个资源模块的局部修改：`logic/fsmgame.o`、`guis/logon/logonpanel.o`、`debug/debugmanager.o`。包索引格式为 `2gab`，每个原始脚本条目前有 24 字节头，前 16 字节为 payload MD5 的四个 uint32 与 `(entryOffset XOR 0x00AE457C)` 异或后的结果。

原始 SHA256：

- wf.exe：`c36805386844015d12dec81354c663c8fb3339855160f8b654a79a86cd479a5c`
- entities.bag：`7f6040318de4f34a28e99882638eb8279035af83d38d72a39a236231e91383bd`

已验证补丁 SHA256：

- wf.exe：`5f1fb1615de274fb4e9bf4d82dd695038aa244ccb225dff34f01f892d0706332`
- entities.bag：`49c5fc357af086d9aa0cd626d6968a131732943490834bcb48ea6206b8a991d0`

旧客户端使用自定义 Python opcode。分析器只读取对象结构；补丁依靠已验证的原始 opcode 模式，不使用标准 Python 2 反汇编结果直接重写整个游戏。

当前限制：使用本地 Hero 和离线管理器，未初始化在线 CityManager 的账号、NPC、队伍与房间。截图中的大地图是客户端原 UI 的显示状态，下一阶段将整理显示和菜单。

后续验证发现原 `EditorConf.save()` 会在正常退出时把 `EditorConf.py` 改写为只有 `data` 的设置文件。生成器现在将完整模板另外保存在 `bootstrap/EditorConf.py`，由 `start_offline.cmd` 每次启动先恢复模板。英雄选择保存在独立 `game/offline_profile.json`，避免与该改写冲突。必须从生成的 CMD 入口启动。
